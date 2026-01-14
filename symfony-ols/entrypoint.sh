#!/bin/bash
useradd -u 1000 www

if [ "$CRONTAB" != "" ] && [ "$CRONTAB" != " " ]; then

    echo "$CRONTAB" >/var/spool/cron/crontabs/www
    chown www:crontab /var/spool/cron/crontabs/www
    chmod 600 /var/spool/cron/crontabs/www
    /etc/init.d/cron start
fi

exec /usr/local/lsws/bin/openlitespeed -d
