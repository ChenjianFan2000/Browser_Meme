#!/usr/bin/env bash
# The Windows WSL client stays connected while research site containers run.
set -Eeuo pipefail
source "$(dirname "$0")/common.sh"
exec 9>"$BM_ROOT/site-keepalive.lock"
flock -n 9 || exit 0
while true; do
    running="$(docker ps -q --filter label=com.docker.compose.project=browser-meme-gitlab)"
    running+="$(docker ps -q --filter label=com.docker.compose.project=browser-meme-webchore)"
    [[ -n "$running" ]] || break
    sleep 10
done
