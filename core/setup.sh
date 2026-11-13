#!/bin/sh
# Sets up the core stack: Authelia (login for the admin interfaces), Portainer and CrowdSec.
#
# Run it the first time, and again to change the admin password or after you change DOMAIN in .env.
# It is safe to run it again: it keeps the existing secrets.
#
# Usage: ./setup.sh [admin password]
# Without the argument, the script asks for the admin password.
# CAUTION: A password in the argument goes into the shell history and shows in the process list.
#
# What it does:
#  1. Creates .env and certs.yml from the examples if they do not exist.
#  2. Gets the admin password (argument or question) and writes authelia/users_database.yml (overwrites the file).
#  3. Creates the secrets in authelia/secrets/ and crowdsec/secrets/ (only the ones that do not exist).
#     Writes the CrowdSec ban page crowdsec/ban.html (from portal/www/blocked_by_crowdsec.html).
#  4. Starts the stack (docker compose up -d --remove-orphans), and registers the CrowdSec web UI as a machine in CrowdSec.
#  5. Resets the Portainer admin password to a random password (portainer/helper-reset-password),
#     and uses it once to configure Portainer: login with OAuth through Authelia, and the app templates URL.
#  6. Waits until Authelia is ready.

set -eu

cd "$(dirname "$0")"

AUTHELIA_IMAGE=authelia/authelia:4
CURL_IMAGE=curlimages/curl:8.11.1
PORTAINER_RESET_PASSWORD_IMAGE=portainer/helper-reset-password:latest
TEMPLATES_URL=https://raw.githubusercontent.com/psy0rz/portainer-templates/main/templates.json
SECRETS_DIR=authelia/secrets
CROWDSEC_SECRETS_DIR=crowdsec/secrets

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

authelia_cli() {
    docker run --rm "$AUTHELIA_IMAGE" authelia "$@"
}

# Prints the value of a variable in .env, without the surrounding quotes.
read_env_value() {
    sed -n "s/^$1=//p" .env | tail -n 1 | sed "s/^'\(.*\)'\$/\1/; s/^\"\(.*\)\"\$/\1/"
}

# Writes 64 random letters and digits to authelia/secrets/<name> if the file does not exist.
create_random_secret() {
    create_random_secret_file "$SECRETS_DIR/$1"
}

# Writes 64 random letters and digits to the file <path> if the file does not exist.
create_random_secret_file() {
    [ -s "$1" ] && return 0
    LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 64 > "$1"
    echo "Created $1"
}

# Calls the Portainer API from inside the network namespace of the portainer container.
# Arguments: method, path, optional extra curl arguments. The request body comes from stdin.
# Fails on an HTTP error.
portainer_api() {
    portainer_api_method=$1
    portainer_api_path=$2
    shift 2
    docker run --rm -i --network "container:$portainer_container" "$CURL_IMAGE" \
        -sSf -X "$portainer_api_method" -H 'Content-Type: application/json' "$@" \
        --data-binary @- "http://localhost:9000$portainer_api_path"
}

# Waits until the command in the arguments succeeds. Fails after 120 seconds.
wait_until() {
    wait_seconds=0
    until "$@" > /dev/null 2>&1; do
        wait_seconds=$((wait_seconds + 2))
        [ "$wait_seconds" -le 120 ] || fail "Timeout after 120 seconds."
        sleep 2
    done
}

portainer_is_ready() {
    printf '' | portainer_api GET /api/system/status
}

crowdsec_lapi_is_ready() {
    docker compose exec -T crowdsec cscli lapi status
}

authelia_is_healthy() {
    [ "$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q authelia)")" = healthy ]
}


### 1. Configuration files

if [ ! -f .env ]; then
    cp .env-example .env
    echo "Created .env from .env-example."
    echo "Edit .env: set DOMAIN and the Let's Encrypt or ZeroSSL settings. Then run $0 again."
    exit 1
fi

if [ ! -f certs.yml ]; then
    cp certs.yml.example certs.yml
    echo "Created certs.yml from certs.yml.example."
fi

DOMAIN=$(read_env_value DOMAIN)
ADMIN_PREFIX=$(read_env_value ADMIN_PREFIX)
ADMIN_PREFIX=${ADMIN_PREFIX:-/server-manager}
case "$DOMAIN" in
    ''|docker1.example.com) fail "Set DOMAIN in .env." ;;
esac


### 2. Admin password and Authelia users file

if [ $# -ge 1 ]; then
    admin_password=$1
else
    printf 'New admin password: '
    IFS= read -r admin_password
fi
[ -n "$admin_password" ] || fail "The password is empty."

admin_password_hash=$(authelia_cli crypto hash generate argon2 --password "$admin_password" | sed -n 's/^Digest: //p')
[ -n "$admin_password_hash" ] || fail "Could not create the password hash."

cat > authelia/users_database.yml <<EOF
# Authelia users. setup.sh overwrites this file each time it runs.
users:
  admin:
    displayname: 'Admin'
    password: '$admin_password_hash'
    email: 'admin@$DOMAIN'
    groups:
      - 'admins'
EOF
chmod 600 authelia/users_database.yml


### 3. Secrets

mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

create_random_secret jwt_secret
create_random_secret session_secret
create_random_secret storage_encryption_key
create_random_secret oidc_hmac_secret
# Portainer creates its first admin with this password. After that, Portainer does not use it.
create_random_secret portainer_initial_admin_password

if [ ! -s "$SECRETS_DIR/oidc_jwks_private_key.pem" ]; then
    docker run --rm -v "$(pwd)/$SECRETS_DIR:/secrets" "$AUTHELIA_IMAGE" \
        authelia crypto pair rsa generate --bits 2048 --directory /secrets \
        --file.private-key oidc_jwks_private_key.pem --file.public-key oidc_jwks_public_key.pem > /dev/null
    echo "Created $SECRETS_DIR/oidc_jwks_private_key.pem"
fi

# Portainer gets the plain client secret, Authelia gets the hash (digest).
if [ ! -s "$SECRETS_DIR/portainer_client_secret.digest" ]; then
    create_random_secret portainer_client_secret
    authelia_cli crypto hash generate pbkdf2 --variant sha512 --password "$(cat "$SECRETS_DIR/portainer_client_secret")" \
        | sed -n 's/^Digest: //p' > "$SECRETS_DIR/portainer_client_secret.digest"
    echo "Created $SECRETS_DIR/portainer_client_secret.digest"
fi

chmod 600 "$SECRETS_DIR"/*

# CrowdSec registers the bouncer "traefik" with this key. The traefik bouncer plugin uses the same key.
# CrowdSec registers the bouncer only if it does not exist. If you delete this file, also delete the
# bouncer: docker compose exec crowdsec cscli bouncers delete traefik
mkdir -p "$CROWDSEC_SECRETS_DIR"
chmod 700 "$CROWDSEC_SECRETS_DIR"
create_random_secret_file "$CROWDSEC_SECRETS_DIR/bouncer_key_traefik"
create_random_secret_file "$CROWDSEC_SECRETS_DIR/crowdsec_web_ui_password"
chmod 600 "$CROWDSEC_SECRETS_DIR"/*
# The CrowdSec web UI runs as the user "node" (not root), so it must be able to read its password file.
# The directory (mode 700) keeps other users on the host out.
chmod 644 "$CROWDSEC_SECRETS_DIR/crowdsec_web_ui_password"


### CrowdSec ban page
#
# The traefik bouncer plugin reads crowdsec/ban.html as a Go template. Go templates use the same braces as the
# contact email placeholder of the portal pages, so this script replaces the placeholder before traefik reads the file.
# Traefik reads the file only at startup. Thus the script restarts traefik (after the start of the stack) if the file changed.

ban_page_target=crowdsec/ban.html
portal_contact_email=$(read_env_value PORTAL_CONTACT_EMAIL)
# Escape the characters that have a special meaning in the sed replacement text.
portal_contact_email_for_sed=$(printf '%s' "$portal_contact_email" | sed 's/[\\&|]/\\&/g')
ban_page_rendered=$(sed "s|{{CONTACT_EMAIL}}|$portal_contact_email_for_sed|g" portal/www/blocked_by_crowdsec.html)
ban_page_changed=false
if [ ! -f "$ban_page_target" ] || [ "$(cat "$ban_page_target")" != "$ban_page_rendered" ]; then
    printf '%s\n' "$ban_page_rendered" > "$ban_page_target"
    ban_page_changed=true
    echo "Created $ban_page_target"
fi


### 4. Start the stack

docker compose run --rm --no-deps -T authelia authelia validate-config \
    || fail "The Authelia configuration is not valid. Refer to the messages above."

docker compose up -d --remove-orphans
# Authelia reads configuration.yml and the secrets only at startup. Authelia keeps the sessions in memory, so this logs out all users.
docker compose restart authelia
if [ "$ban_page_changed" = true ]; then
    docker compose restart traefik
fi

# Register the CrowdSec web UI as a machine in the CrowdSec local API. --force updates the password if the
# machine exists. -f /dev/null: do not overwrite the credentials file of the CrowdSec container.
echo "Waiting for CrowdSec..."
wait_until crowdsec_lapi_is_ready
docker compose exec -T crowdsec cscli machines add crowdsec-web-ui \
    --password "$(cat "$CROWDSEC_SECRETS_DIR/crowdsec_web_ui_password")" -f /dev/null --force > /dev/null
# The web UI reads the password only at startup.
docker compose restart crowdsec-web-ui


### 5. Configure Portainer
#
# The script needs a Portainer admin login. It resets the admin password to a random password, uses it
# once, and does not store it. Users log in with OAuth (Authelia).

portainer_container=$(docker compose ps -q portainer)

# On a new installation, Portainer must first create its database and the admin
# (from --admin-password-file). The reset helper fails without them.
echo "Waiting for Portainer..."
wait_until portainer_is_ready

echo "Resetting the Portainer admin password to a random password..."
docker compose stop portainer
portainer_admin_password=$(docker run --rm --volumes-from "$portainer_container" "$PORTAINER_RESET_PASSWORD_IMAGE" 2>&1 \
    | sed -n 's/.*Use the following password to login: //p')
docker compose start portainer
[ -n "$portainer_admin_password" ] || fail "Could not reset the Portainer admin password."

echo "Waiting for Portainer..."
wait_until portainer_is_ready

# The JSON escape (backslash and double quote) is necessary, because the random password can contain them.
portainer_jwt=$(printf '{"Username":"admin","Password":"%s"}' \
        "$(printf '%s' "$portainer_admin_password" | sed 's/\\/\\\\/g; s/"/\\"/g')" \
    | portainer_api POST /api/auth \
    | sed -n 's/.*"jwt":"\([^"]*\)".*/\1/p')
[ -n "$portainer_jwt" ] || fail "Could not log in to Portainer with the random admin password."

auth_url="https://$DOMAIN/authelia"

# AuthenticationMethod 3 is OAuth. AuthStyle 1 sends the client secret in the request body
# (token_endpoint_auth_method client_secret_post in Authelia).
portainer_api PUT /api/settings -H "Authorization: Bearer $portainer_jwt" > /dev/null <<EOF
{
  "AuthenticationMethod": 3,
  "TemplatesURL": "$TEMPLATES_URL",
  "OAuthSettings": {
    "ClientID": "portainer",
    "ClientSecret": "$(cat "$SECRETS_DIR/portainer_client_secret")",
    "AuthorizationURI": "$auth_url/api/oidc/authorization",
    "AccessTokenURI": "$auth_url/api/oidc/token",
    "ResourceURI": "$auth_url/api/oidc/userinfo",
    "RedirectURI": "https://$DOMAIN$ADMIN_PREFIX/portainer/",
    "LogoutURI": "$auth_url/logout",
    "UserIdentifier": "preferred_username",
    "Scopes": "openid profile groups email",
    "OAuthAutoCreateUsers": false,
    "SSO": true,
    "AuthStyle": 1
  }
}
EOF


### 6. Wait for Authelia
#
# Traefik routes to Authelia only when its health check is healthy. The first check after the start
# can take 30 seconds. Until then, the login page and all admin pages show the maintenance page.

echo "Waiting for Authelia..."
wait_until authelia_is_healthy

# After too many failed logins, Authelia bans the user for some minutes. Remove such a ban.
docker compose exec -T authelia authelia storage bans user revoke admin > /dev/null 2>&1 || true

echo
echo "Done."
echo "Admin login:  $auth_url/  (user: admin)"
echo "Overview:     https://$DOMAIN$ADMIN_PREFIX/"
echo "Portainer:    https://$DOMAIN$ADMIN_PREFIX/portainer/  (click \"Login with OAuth\")"
echo "The Portainer internal admin has a random password. If Authelia does not work, refer to the README."
