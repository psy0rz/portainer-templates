#!/bin/bash
HOME=/bitnami
USER=daemon

mkdir $HOME/.ssh 2>/dev/null
if ! grep -x "$SSH_KEY" $HOME/.ssh/authorized_keys; then
    echo "$SSH_KEY" >> $HOME/.ssh/authorized_keys
fi

chown $USER $HOME
chown -R $USER $HOME/.ssh

exec /usr/sbin/sshd -D -e 
