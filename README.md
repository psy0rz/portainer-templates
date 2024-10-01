# Overview
These portainer templates are ment to run on a Docker server with ZFS volume support. 

In contrast with the default portainer templates, these will run behind a automatic reverse proxy via Traefik. This way you can run many web application containers on one server.

Traefik is configured to use ZeroSSL to get free SSL certificates. It uses portainer as web GUI for docker and to create new software stacks.

# Requirements

1. Get ZFS support for your /var/lib/docker mountpoint. Try https://github.com/psy0rz/alpinebox for a nice installer for Alpine Linux with ZFS rootfs.
2. Install Docker and Docker compose cli.
3. Install https://github.com/csachs/docker-zfs-plugin.git so that you have ZFS volume support.

#  Start the core stack

* Go to the core directory
* Edit the .env file (You need a ZeroSSL account)
* docker compose up -d

# Open portainer

* Go to https://portainer.yourdomain.com and login.
* Go to settings and enter this in the App templates field: https://raw.githubusercontent.com/psy0rz/portainer-templates/main/templates.json

Now you be able to go to App templates and create a stack.

Your Traefik dashboard is on `/traefik/dashboard#/`

# Backups

Since its all running on ZFS, its easy to make backups and snapshots with my other project: https://pypi.org/project/zfs-autobackup/


