export PATH=/usr/local/bin:/usr/bin:/bin:/usr/local/games:/usr/games:/app/magento/bin

#from: https://github.com/magento/magento-cloud-docker/blob/develop/images/php/8.3-cli/Dockerfile

export COMPOSER_HOME=/composer
export MAGENTO_ROOT=/app
export COMPOSER_MEMORY_LIMIT=-1
export PHP_MEMORY_LIMIT=-1
export PHP_VALIDATE_TIMESTAMPS=1
export COMPOSER_CLEAR_CACHE=false
export PHP_VALIDATE_TIMESTAMPS=1
export DEBUG=false
export SENDMAIL_PATH=/dev/null
export PHPRC=${MAGENTO_ROOT}/php.ini
export PHP_EXTENSIONS="bcmath bz2 calendar exif gd gettext intl mysqli opcache pdo_mysql redis soap sockets sodium sysvmsg sysvsem sysvshm xsl zip pcntl"
