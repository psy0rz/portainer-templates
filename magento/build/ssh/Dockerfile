ARG CLI_VERSION

FROM magento/magento-cloud-docker-php:${CLI_VERSION}

EXPOSE 22

COPY ssh-run.sh /ssh-run.sh

RUN apt-get update && apt-get install -y openssh-server less mc rsync && \
    mkdir /run/sshd && \
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config && \
    sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config && \
    chmod +x /ssh-run.sh


COPY motd /etc/motd

#path
COPY env.sh /etc/profile.d/env.sh
RUN chmod +x /etc/profile.d/env.sh


# entrypoint will be that of php
# ENTRYPOINT [ "/entrypoint.sh" ]
CMD /ssh-run.sh
