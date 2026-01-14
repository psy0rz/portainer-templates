#!/bin/bash
HOME=/app
USER=www

#ssh stuff
mkdir $HOME/.ssh 2>/dev/null
if ! grep -x "$SSH_KEY" $HOME/.ssh/authorized_keys; then
    echo "$SSH_KEY" >>$HOME/.ssh/authorized_keys
fi

# preserve hostkeys
cp $HOME/.ssh/ssh_host_* /etc/ssh/ 2>/dev/null
ssh-keygen -A
cp /etc/ssh/ssh_host_* $HOME/.ssh

#sql stuff
echo -e '[client]\nuser=magento\npassword=magento\nhost=db\n≈skip-ssl\n[mysql]database=magento\n' >$HOME/.my.cnf

chown $USER $HOME
chown -R $USER $HOME/.ssh

exec /usr/sbin/sshd -D -e
