#!/bin/bash

# Upload to the server each time a file changes.
#
# entr -d stops (exit code 2) when a file is added or removed in a watched directory.
# The loop then starts entr again with the new file list.
# Other exit codes (for example ctrl-c) stop the script.
while true; do
    find . -path ./.git -prune -o -type f -print | entr -d ./upload.sh "$@"
    entr_exit_code=$?
    if [ "$entr_exit_code" -ne 2 ]; then
        exit "$entr_exit_code"
    fi
done
