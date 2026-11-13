# ![Hostbox](./logo/hostbox-logo.svg)

**Hosting, out of the box.**

Hostbox turns one Docker server into a hosting platform for many websites and web applications. You create the sites in Portainer from a set of app templates. Each site runs in its own stack, preferably with ZFS volumes, so every Docker volume gets its own ZFS dataset that you can snapshot, back up and move to a different server.

The core stack does the work around the sites. Traefik routes all sites through one reverse proxy and gets free SSL certificates from Let's Encrypt or ZeroSSL. CrowdSec and a global blocklist keep out bots and attackers. Authelia protects all admin interfaces with one login, VictoriaLogs keeps the logs, and Watchtower keeps the images up to date.

## Requirements

We recommend [Alpinebox](https://github.com/psy0rz/alpinebox) as the operating system for the Docker server. Alpinebox installs Alpine Linux with ZFS as the root file system. It also has scripts that install Docker and the ZFS volume plugin.

To prepare an Alpinebox server:

1. Install Alpinebox. Refer to the [Alpinebox README](https://github.com/psy0rz/alpinebox#installing).
2. Go to `/root/alpinebox`.
3. Run `./install-docker`.
4. Do the instructions that the script shows.

If you use a different operating system, do these steps manually:

* Install Docker.
* Install the Docker compose CLI.

ZFS volumes are optional. You must have ZFS volumes if you use zfs-autobackup or zmigrate. To use ZFS volumes:

* Make sure that the `/var/lib/docker` mount point has ZFS support.
* Install <https://github.com/csachs/docker-zfs-plugin.git>. This plugin gives ZFS volume support.

The default volume driver is `zfs`. To operate without ZFS:

* In `core/.env`, set `VOLUME_DRIVER=local`.
* When you create a stack from a template, select `local` as the volume driver.

## Start the core stack

1. Go to the `core` directory.
2. Run `./setup.sh`. The script copies `.env-example` to `.env` and stops.
3. Edit `.env`. Set `DOMAIN` and the Let's Encrypt or ZeroSSL settings. These settings are the minimum. `DOMAIN` must be a host name, not an IP address.
4. Run `./setup.sh` again. Type the admin password when the script asks for it.

You can also give the password as an argument: `./setup.sh 'password'`. CAUTION: Then the password goes into the shell history and shows in the process list.

The setup script does these steps:

* It copies `certs.yml.example` to `certs.yml` if `certs.yml` does not exist. Traefik needs this file, also if you do not use custom certificates.
* It writes the user `admin` to `authelia/users_database.yml`. It overwrites the file each time.
* It creates the Authelia secrets in `authelia/secrets/`.
* It creates the CrowdSec bouncer key and the password of the CrowdSec web UI in `crowdsec/secrets/`.
* It writes the CrowdSec ban page to `crowdsec/ban.html`. Refer to [Blocked requests and maintenance pages](#blocked-requests-and-maintenance-pages).
* It starts the stack with `docker compose up -d --remove-orphans`, and registers the CrowdSec web UI as a machine in CrowdSec.
* It resets the password of the Portainer internal admin to a random password with the `portainer/helper-reset-password` image. This stops Portainer for a few seconds. The script uses the password one time to configure Portainer, and does not store it.
* It configures Portainer: the login through Authelia (OAuth) and the app templates URL.
* It waits until Authelia is ready.

You can run `./setup.sh` again. It keeps the existing secrets. Run it again after you change `DOMAIN` or `PORTAL_CONTACT_EMAIL`.

To change the admin password, run `./setup.sh` and type the new password.

CAUTION: Do not edit `authelia/users_database.yml`. `setup.sh` overwrites it.

### Optional files

* `certs/`: This directory contains custom (non-ACME) certificates for Traefik. Add them to `certs.yml`.
* `docker-compose.override.yml`: You can use this file to set a separate IP address as a landing page for reserved domains. Refer to `docker-compose.override.yml.example`.
* `clean-expired-certs.sh`: This script removes expired certificates from the Traefik ACME storage.

## Core stack components

* **Traefik**: The reverse proxy. It supplies automatic SSL, sends http requests to https, and has a global blocklist for paths that scanners look for.
* **Portainer**: The Docker web GUI. You use it to create stacks from the templates.
* **Authelia**: The login portal for the admin interfaces. It is also the OpenID Connect provider for the Portainer login.
* **CrowdSec** (community edition): It reads the logs of Traefik and Authelia and finds attacks (for example scans, exploits and brute force logins). It bans the IP addresses of the attackers. It also uses the community blocklist from CrowdSec. The CrowdSec bouncer plugin in Traefik blocks the banned IP addresses on all https sites.
* **CrowdSec web UI** ([crowdsec-web-ui](https://github.com/TheDuffman85/crowdsec-web-ui)): It shows the CrowdSec alerts, decisions (bans) and metrics. You can also add and remove bans. Its own login is off, because the `auth` middleware protects it.
* **VictoriaLogs**: It stores the Traefik log and the Traefik access log. Traefik sends the logs with OTLP. The default retention period is 30 days. To change it, set `LOGS_RETENTION` in `core/.env`.
* **Watchtower**: It updates the images each night at 04:00.
* **Portal**: An nginx server. It shows the server manager overview page, the blocked page and the maintenance page.

### CrowdSec

* The log sources are in `core/crowdsec/acquis.yaml`. CrowdSec reads the Traefik access log from VictoriaLogs, because Traefik does not write it to stdout. CrowdSec also reads the Docker logs of all containers with the label `crowdsec.enable=true` (Authelia). The label `crowdsec.labels.type` selects the parser.
* Private IP addresses are never banned.
* If CrowdSec stops, Traefik lets all requests through.
* Traefik downloads the bouncer plugin when it starts. If the download fails, the https sites do not work.
* To see the bans, run `docker compose exec crowdsec cscli decisions list`.
* To remove a ban, run `docker compose exec crowdsec cscli decisions delete --ip <ip address>`.
* To connect CrowdSec to the CrowdSec console, set `CROWDSEC_ENROLL_KEY` in `core/.env`.

### Blocked requests and maintenance pages

| Situation | Status | Page |
| --- | --- | --- |
| The path is in the global blocklist (`xmlrpc.php`, `.git`, `.env`, `*.log` and other paths that bots and exploit scanners look for). | 403 | `core/portal/www/blocked.html` |
| CrowdSec banned the IP address. | 403 | `core/crowdsec/ban.html` |
| The containers of the host are stopped. | 503 | `core/portal/www/maintenance.html` |

* Traefik writes the blocked paths to the access log. Thus CrowdSec can ban the scanners.
* The ban page shows the IP address and a code that starts with `crowdsec-`. Thus you can see the difference from the blocked page in complaints.
* The maintenance page refreshes each 60 seconds. When the containers start again, the visitor sees the site again.
* The pages are in Dutch and English. They show a "contact us" link to `PORTAL_CONTACT_EMAIL`. Set it in `core/.env`.
* To change the blocked page or the maintenance page, edit the files in `core/portal/www/`.
* The source of the ban page is `core/portal/www/blocked_by_crowdsec.html`. `setup.sh` adds `PORTAL_CONTACT_EMAIL` to it and writes the result to `core/crowdsec/ban.html`. After you change the page or `PORTAL_CONTACT_EMAIL`, run `./setup.sh` again.

## Server manager

All admin interfaces are under `ADMIN_PREFIX` on your `DOMAIN`. The default `ADMIN_PREFIX` is `/server-manager`. Examples:

* Overview: <https://docker1.example.com/server-manager/>
* Portainer: <https://docker1.example.com/server-manager/portainer/>
* Traefik dashboard: <https://docker1.example.com/server-manager/traefik/dashboard/>
* Logs (VictoriaLogs): <https://docker1.example.com/server-manager/victoria-logs/select/vmui/>
* CrowdSec web UI: <https://docker1.example.com/server-manager/crowdsec/>

The overview page shows a list of all Traefik routers under the admin prefix. Thus, the admin interfaces of other stacks show on this page automatically.

### Login

The generic `auth` middleware protects the overview, Portainer, the Traefik dashboard, the logs and the CrowdSec web UI. Other templates can also use this middleware to protect web interfaces.

* The `auth` middleware sends you to the Authelia login page at `https://DOMAIN/authelia/`. Authelia is not under `ADMIN_PREFIX`, because Authelia accepts only a path with one segment of letters and digits.
* The user is `admin`. `setup.sh` sets the password.
* After the login, Authelia keeps the session in a cookie. The session stays for 1 day without activity, and for a maximum of 7 days. Select "Remember me" to keep it for 1 month.
* Authelia keeps the sessions in memory. After a restart of Authelia (for example after an image update by Watchtower), you must log in again.
* To log out, click "Log out" on the overview page.

For two-factor authentication (a TOTP app), set `ADMIN_AUTH_POLICY=two_factor` in `.env` and run `./setup.sh` again. There is no mail server for Authelia, so Authelia writes the registration code to a file. To read the code, run `docker compose exec authelia cat /data/notification.txt`.

### Portainer login

Portainer uses Authelia for its login. In Portainer, click "Login with OAuth". If you are logged in to Authelia, you do not type the password again.

Nobody knows the password of the Portainer internal admin. If Authelia does not work and you must use the internal login, get a new password:

1. Run `docker compose stop portainer`.
2. Run `docker run --rm --volumes-from $(docker compose ps -aq portainer) portainer/helper-reset-password`. The command shows the new password.
3. Run `docker compose start portainer`.
4. Log in to Portainer as `admin` with the new password.

## Use the templates

`setup.sh` sets the App templates URL in Portainer. To set it manually:

1. In Portainer, go to Settings.
2. In the App templates field, enter this URL:

   <https://raw.githubusercontent.com/psy0rz/portainer-templates/main/templates.json>

To use the templates:

1. In Portainer, go to App templates.
2. Create a stack.

These templates are available:

* Wordpress vanilla
* Wordpress litespeed
* Grav CMS vanilla
* Magento 2
* Symfony litespeed
* Nextcloud
* Shared MariaDB
* PHPMyAdmin
* MikoPBX
* Mailchannels relay

## Backups and migration

With ZFS volumes, you can make backups and snapshots with zfs-autobackup: <https://pypi.org/project/zfs-autobackup/>

To move a stack and its ZFS volumes to a different server, refer to [zmigrate](zmigrate/README.md).
