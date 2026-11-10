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
3. Edit `.env`. Set `DOMAIN` and the Let's Encrypt or ZeroSSL settings. These settings are the minimum.
4. Create the `htpasswd` file. This file contains the users for the generic `auth` middleware. The `auth` middleware protects the admin interfaces. Other templates can also use this middleware to protect web interfaces. To create an entry, run `htpasswd -nbB admin 'password' >> htpasswd`.

   If the `htpasswd` file does not exist, `docker compose up` stops with an error.
5. Run `docker compose up -d`.

## Optional files

* `certs.yml` and `certs/`: These files contain custom (non-ACME) certificates for Traefik.
* `docker-compose.override.yml`: You can use this file to set a separate IP address as a landing page for reserved domains. Refer to `docker-compose.override.yml.example`.
* `clean-expired-certs.sh`: This script removes expired certificates from the Traefik ACME storage.

# Server manager

All admin interfaces are under `ADMIN_PREFIX` on your `DOMAIN`. The default `ADMIN_PREFIX` is `/server-manager`. Examples:

* Overview: <https://docker1.example.com/server-manager/>
* Portainer: <https://docker1.example.com/server-manager/portainer/>
* Traefik dashboard: <https://docker1.example.com/server-manager/traefik/dashboard/>
* Logs (VictoriaLogs): <https://docker1.example.com/server-manager/victoria-logs/select/vmui/>

The `auth` middleware protects the overview, Portainer, the Traefik dashboard and the logs. The users are in the `htpasswd` file.

The overview page shows a list of all Traefik routers under the admin prefix. Thus, the admin interfaces of other stacks show on this page automatically.

The default Portainer login is admin/admin. `PORTAINER_ADMIN_PASSWORD` in `.env` sets the password.

CAUTION: Change the password after the first login.

# Use the templates

1. In Portainer, go to Settings.
2. In the App templates field, enter this URL:

   <https://raw.githubusercontent.com/psy0rz/portainer-templates/main/templates.json>

3. Go to App templates.
4. Create a stack.

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
