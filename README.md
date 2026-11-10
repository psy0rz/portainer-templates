# Overview

These Portainer templates are meant to run on a Docker server, preferably with ZFS volume support so every Docker volume gets its own ZFS dataset. ZFS is optional: you can also use Docker's default `local` volume driver.

In contrast to the default Portainer templates, these run behind an automatic Traefik reverse proxy, so you can run many web application containers on one server. Traefik gets free SSL certificates from Let's Encrypt or ZeroSSL, and Portainer is the web GUI to manage Docker and create new stacks from these templates.

# Requirements

NOTE: [Alpinebox](https://github.com/psy0rz/alpinebox) has scripts that do all of this automatically.

* Install Docker and the Docker compose cli.

For ZFS volumes (optional, but needed for zfs-autobackup and zmigrate):

* Get ZFS support for your /var/lib/docker mountpoint.
* Install <https://github.com/csachs/docker-zfs-plugin.git> so that you have ZFS volume support.

Without ZFS, set `VOLUME_DRIVER=local` in `core/.env`, and choose `local` as the volume driver when you create a stack from a template. Both default to `zfs`.

# Start the core stack

The core stack contains:

* **Traefik**: reverse proxy with automatic SSL, http to https redirect, and a global blocklist that returns 403 for paths probed by bots and exploit scanners (`xmlrpc.php`, `.git`, `.env`, `*.log`, etc.).
* **Portainer**: Docker web GUI.
* **Watchtower**: updates images every night at 04:00.
* **Portal**: nginx serving the server manager overview page, and a maintenance page (503) for hosts whose containers are down.

To start it:

* Go to the `core` directory.
* Copy `.env-example` to `.env` and edit it. Set at least `DOMAIN` and the Let's Encrypt or ZeroSSL settings.
* `docker compose up -d`

## Optional files

* `htpasswd`: users for the generic `auth` middleware that other templates can use to protect web interfaces. Create entries with `htpasswd -nbB user 'password'`.
* `certs.yml` and `certs/`: custom (non-ACME) certificates for Traefik.
* `docker-compose.override.yml`: see `docker-compose.override.yml.example` for using a separate IP as a landing page for reserved domains.
* `clean-expired-certs.sh`: removes expired certificates from Traefik's ACME storage.

# Server manager

All admin interfaces live under `ADMIN_PREFIX` (default `/server-manager`) on your `DOMAIN`:

* Overview: <https://docker1.example.com/server-manager/>
* Portainer: <https://docker1.example.com/server-manager/portainer/>
* Traefik dashboard: <https://docker1.example.com/server-manager/traefik/dashboard/>

The overview page lists every Traefik router under the admin prefix, so admin interfaces of other stacks show up there automatically.

The default Portainer login is admin/admin (`PORTAINER_ADMIN_PASSWORD` in `.env`). Change it after the first login.

# Use the templates

In Portainer, go to Settings and enter this in the App templates field:

<https://raw.githubusercontent.com/psy0rz/portainer-templates/main/templates.json>

Now you can go to App templates and create a stack. Available templates include Wordpress, Wordpress litespeed, Grav, Magento 2, Symfony litespeed, Nextcloud, shared MariaDB, PHPMyAdmin, MikoPBX and a Mailchannels relay.

# Backups and migration

With ZFS volumes it's easy to make backups and snapshots with my other project: <https://pypi.org/project/zfs-autobackup/>

To move a stack including its ZFS volumes to another server, see [zmigrate](zmigrate/README.md).
