#!/bin/bash

docker run -it --rm -v /var/lib/docker/volumes/core_traefik/:/data ghcr.io/sersoft-gmbh/traefik-acme-storage-cleaner /data/letsencrypt.json /data/acme.json
docker restart core-traefik-1
docker logs -f core-traefik-1
