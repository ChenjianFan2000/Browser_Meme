#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/common.sh"
printf 'Python: '
python3 --version
printf 'Docker: '
docker version --format '{{.Server.Version}}'
docker compose version
docker buildx version
printf 'Docker storage: '
docker info --format '{{.DockerRootDir}}'
printf 'Root filesystem and swap (both inside G:-backed WSL storage):\n'
findmnt -no SOURCE,FSTYPE,TARGET /
swapon --show
if mountpoint -q /mnt/c; then
    printf 'Unexpected C: mount in this dedicated research distro.\n' >&2
    exit 1
fi
for profile in core agentlab webchore; do
    python="$BM_ROOT/envs/$profile/bin/python"
    if [[ ! -x "$python" ]]; then
        printf '%s: prepare has not completed; run prepare on the faster network first.\n' "$profile"
    elif "$python" -c 'import importlib.metadata; importlib.metadata.version("browsergym-core")' >/dev/null 2>&1; then
        "$python" -m pip check
        "$python" "$PROJECT_ROOT/environment/scripts/smoke.py" "$profile"
    else
        printf '%s: virtual environment prepared; dependency/browser download and install pending.\n' "$profile"
    fi
done
printf 'WorkArena instance access: requires Hugging Face approval and a locally configured token.\n'
printf 'Container site status:\n'
docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'
docker compose -f "$PROJECT_ROOT/environment/compose/gitlab.yml" config --quiet
docker compose -f "$PROJECT_ROOT/environment/compose/webchore.yml" config --quiet
printf 'Base environment checks passed. Pending resources above are not counted as installed.\n'
