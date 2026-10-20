#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/common.sh"
for script in "$PROJECT_ROOT"/environment/scripts/*.sh "$PROJECT_ROOT/environment/activate.sh"; do
    bash -n "$script"
done
python3 - "$PROJECT_ROOT" <<'PY'
import ast
from pathlib import Path
import sys
root = Path(sys.argv[1])
for script in (root / 'environment/scripts').glob('*.py'):
    ast.parse(script.read_text(), filename=str(script))
print('Bash and Python syntax: passed')
PY
docker compose -f "$PROJECT_ROOT/environment/compose/gitlab.yml" config --quiet
docker compose -f "$PROJECT_ROOT/environment/compose/webchore.yml" config --quiet
image=browser-meme/ubuntu-smoke:24.04.4
if ! docker image inspect "$image" >/dev/null 2>&1; then
    docker import "$BM_DOWNLOADS/ubuntu-base-24.04.4-base-amd64.tar.gz" "$image"
fi
docker run --rm --network none --read-only --user 65534:65534 "$image" /usr/bin/cat /etc/os-release
printf 'Docker offline container execution: passed\n'
