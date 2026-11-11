# Overview

These Portainer templates are meant to run on a Docker server, preferably with ZFS volume support so every Docker volume gets its own ZFS dataset. ZFS is optional: you can also use Docker's default `local` volume driver.

In contrast to the default Portainer templates, these run behind an automatic Traefik reverse proxy, so you can run many web application containers on one server. Traefik gets free SSL certificates from Let's Encrypt or ZeroSSL, and Portainer is the web GUI to manage Docker and create new stacks from these templates.

# Requirements

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

# Start the core stack

The core stack contains these components:

* **Traefik**: A reverse proxy. Traefik has these functions:
  * It supplies automatic SSL.
  * It sends http requests to https.
  * It has a global blocklist. Bots and exploit scanners try to find some paths (`xmlrpc.php`, `.git`, `.env`, `*.log`, and other paths). For these paths, Traefik sends the request to the portal, which shows a blocked page (403).
* **Portainer**: The Docker web GUI.
* **Authelia**: The login portal for the admin interfaces. It is also the OpenID Connect provider for the Portainer login.
* **Watchtower**: It updates the images each night at 04:00.
* **VictoriaLogs**: It stores the Traefik log and the Traefik access log. Traefik sends the logs with OTLP. The default retention period is 30 days. To change it, set `LOGS_RETENTION` in `core/.env`.
* **Portal**: An nginx server. It has these functions:
  * It shows the server manager overview page.
  * It shows a blocked page (403) for the paths in the global blocklist.
  * It shows a maintenance page (503) for hosts that have stopped containers. The maintenance page refreshes each 60 seconds. When the containers start again, the visitor sees the site again.

  The blocked page and the maintenance page are in Dutch and English. They show a "contact us" link to `PORTAL_CONTACT_EMAIL` (set it in `core/.env`). To change the pages, edit the files in `core/portal/www/`.

To start the core stack:

1. Go to the `core` directory.
2. Copy `.env-example` to `.env`.
3. Edit `.env`. Set `DOMAIN` and the Let's Encrypt or ZeroSSL settings. These settings are the minimum. `DOMAIN` must be a host name, not an IP address.
4. Run `./setup.sh`. Type the admin password when the script asks for it.

The setup script does these steps:

* It copies `certs.yml.example` to `certs.yml` if `certs.yml` does not exist. Traefik needs this file, also if you do not use custom certificates.
* It creates the Authelia secrets in `authelia/secrets/`.
* It writes the user `admin` to `authelia/users_database.yml`. It overwrites the file each time.
* It starts the stack with `docker compose up -d`.
* It resets the password of the Portainer internal admin to a random password with the `portainer/helper-reset-password` image. This stops Portainer for a few seconds. The script uses the password one time to configure Portainer, and does not store it.
* It configures Portainer: the login through Authelia (OAuth) and the app templates URL.

You can run `./setup.sh` again. It keeps the existing secrets. Run it again after you change `DOMAIN`.

To change the admin password, run `./setup.sh` and type the new password.

CAUTION: Do not edit `authelia/users_database.yml`. `setup.sh` overwrites it.

## Optional files

* `certs/`: This directory contains custom (non-ACME) certificates for Traefik. Add them to `certs.yml`.
* `docker-compose.override.yml`: You can use this file to set a separate IP address as a landing page for reserved domains. Refer to `docker-compose.override.yml.example`.
* `clean-expired-certs.sh`: This script removes expired certificates from the Traefik ACME storage.

# Server manager

All admin interfaces are under `ADMIN_PREFIX` on your `DOMAIN`. The default `ADMIN_PREFIX` is `/server-manager`. Examples:

* Overview: <https://docker1.example.com/server-manager/>
* Portainer: <https://docker1.example.com/server-manager/portainer/>
* Traefik dashboard: <https://docker1.example.com/server-manager/traefik/dashboard/>
* Logs (VictoriaLogs): <https://docker1.example.com/server-manager/victoria-logs/select/vmui/>

The generic `auth` middleware protects the overview, Portainer, the Traefik dashboard and the logs. Other templates can also use this middleware to protect web interfaces. The `auth` middleware sends you to the Authelia login page at `https://DOMAIN/authelia/`. The user is `admin`. `setup.sh` sets the password. After the login, Authelia keeps the session in a cookie. The session stays for 1 day without activity, and for a maximum of 7 days. Select "Remember me" to keep it for 1 month. Authelia keeps the sessions in memory. After a restart of Authelia (for example after an image update by Watchtower), you must log in again. To log out, click "Log out" on the overview page.

Authelia is not under `ADMIN_PREFIX`, because Authelia accepts only a path with one segment of letters and digits.

For two-factor authentication (a TOTP app), set `ADMIN_AUTH_POLICY=two_factor` in `.env` and run `./setup.sh` again. There is no mail server for Authelia, so Authelia writes the registration code to a file. To read the code, run `docker compose exec authelia cat /data/notification.txt`.

The overview page shows a list of all Traefik routers under the admin prefix. Thus, the admin interfaces of other stacks show on this page automatically.

Portainer uses Authelia for its login. In Portainer, click "Login with OAuth". If you are logged in to Authelia, you do not type the password again.

Nobody knows the password of the Portainer internal admin. If Authelia does not work and you must use the internal login, get a new password:

1. Run `docker compose stop portainer`.
2. Run `docker run --rm --volumes-from $(docker compose ps -aq portainer) portainer/helper-reset-password`. The command shows the new password.
3. Run `docker compose start portainer`.
4. Log in to Portainer as `admin` with the new password.

# Use the templates

`setup.sh` sets the App templates URL in Portainer. To set it manually:

1. In Portainer, go to Settings.
2. In the App templates field, enter this URL:

   <https://raw.githubusercontent.com/psy0rz/portainer-templates/main/templates.json>

To use the templates:

1. In Portainer, go to App templates.
2. Create a stack.

These templates are available:

* Wordpress
* Wordpress litespeed
* Grav
* Magento 2
* Symfony litespeed
* Nextcloud
* Shared MariaDB
* PHPMyAdmin
* MikoPBX
* Mailchannels relay

# Backups and migration

With ZFS volumes, you can make backups and snapshots with zfs-autobackup: <https://pypi.org/project/zfs-autobackup/>

To move a stack and its ZFS volumes to a different server, refer to [zmigrate](zmigrate/README.md).
