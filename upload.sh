#!/bin/bash

rsync --exclude .env -avx . $1:portainer-templates 
