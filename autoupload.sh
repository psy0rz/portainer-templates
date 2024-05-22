#!/bin/bash

find . | entr  ./upload.sh $@

