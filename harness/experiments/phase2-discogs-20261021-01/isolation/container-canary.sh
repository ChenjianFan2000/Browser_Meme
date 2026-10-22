#!/bin/sh
set -eu
id
for path in /mnt/g/Browser_Meme /var/run/docker.sock /opt/browser-meme/secrets /proc/1/root/mnt/g/Browser_Meme; do
  if test -e "$path"; then printf 'UNEXPECTED_VISIBLE %s\n' "$path"; else printf 'ABSENT %s\n' "$path"; fi
done
printf 'PID_COUNT '
find /proc -maxdepth 1 -name '[0-9]*' | wc -l
printf 'DEFAULT_ROUTE '
cat /proc/net/route
