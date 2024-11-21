#!/bin/bash

SOURCE=magento

TARGET=magento_dev
TARGET_URL=https://totalartist.projectlocatie.nl/
TARGET_COOKIE_DOMAIN=totalartist.projectlocatie.nl

set -e

echo "MIGRATE: Copying from $SOURCE to $TARGET stack:"

#Migrate data:
rsync --delete -avx /var/lib/docker/volumes/${SOURCE}_magento/ /var/lib/docker/volumes/${TARGET}_magento
docker exec -u www -i  ${SOURCE}-ssh-1 mysqldump magento | docker exec -i -u www ${TARGET}-ssh-1 mysql

#Apply config
docker exec -u www -it ${TARGET}-ssh-1 /app/magento/bin/magento config:set web/secure/base_url $TARGET_URL
docker exec -u www -it ${TARGET}-ssh-1 /app/magento/bin/magento config:set web/unsecure/base_url $TARGET_URL
docker exec -u www -it ${TARGET}-ssh-1 /app/magento/bin/magento config:set web/cookie/cookie_domain $TARGET_COOKIE_DOMAIN

#Deploy
docker stop ${TARGET}-cron-1
docker exec -u www -it ${TARGET}-ssh-1 /app/magento/bin/magento deploy:mode:set production
docker exec -u www -it ${TARGET}-ssh-1 /app/magento/bin/magento indexer:reindex
docker start ${TARGET}-cron-1
#docker exec -u www -it ${TARGET}-ssh-1 /app/magento/bin/magento cache:flush

echo "MIGRATE: complete"
