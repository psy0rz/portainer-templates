#!/bin/bash

SOURCE=magento

TARGET=magento_dev
TARGET_URL=https://server.com/
TARGET_COOKIE_DOMAIN=server.com

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
docker exec -u www -it ${TARGET}-ssh-1 /app/magento/bin/magento cache:flush
#niet nodig? (duurt 5 minuten)
#docker exec -u www -it ${TARGET}-ssh-1 /app/magento/bin/magento deploy:mode:set production

echo "MIGRATE: complete"
