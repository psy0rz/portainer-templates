ARG MAGENTO_VERSION

FROM docker.io/bitnami/magento:${MAGENTO_VERSION}

RUN apt-get update && apt-get install -y openssh-server


EXPOSE 22

COPY entrypoint.sh /entrypoint.sh

RUN usermod -s /bin/bash -d /bitnami daemon && \
    mkdir /run/sshd && \
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config && \
    sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config && \
    chmod +x /entrypoint.sh

USER daemon
ENV PATH=/opt/bitnami/common/bin:/opt/bitnami/php/bin:/opt/bitnami/php/sbin:/opt/bitnami/apache/bin:/opt/bitnami/mysql/bin:/opt/bitnami/magento/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
USER root

ENTRYPOINT [ "/entrypoint.sh" ]


