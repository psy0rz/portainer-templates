ARG OLS_VERSION=1.7.11-lsphp73

FROM litespeedtech/openlitespeed:${OLS_VERSION}

ENV NODE_VER=10
ENV PHP_VERSION=7.3

RUN echo 'memory_limit=2G' > /usr/local/lsws/lsphp73/etc/php/$PHP_VERSION/mods-available/memory.ini

# php composer
RUN curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/bin --filename=composer --2.2

RUN chown www-data /var/www; touch /var/www/.bashrc; chmod +x /var/www/.bashrc; chown www-data /var/www/.bashrc


# nodejs/yarn stuff
USER www-data
RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash 
RUN bash -c 'source $HOME/.nvm/nvm.sh   && \
    nvm install $NODE_VER && \
    curl -o- -L https://yarnpkg.com/install.sh | bash'


ENTRYPOINT /bin/bash
WORKDIR /app

