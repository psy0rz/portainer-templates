#!/bin/bash

rsync --exclude .env --exclude .git -avx . $1:portainer-templates 
