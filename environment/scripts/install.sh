#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/common.sh"
profile="${1:-core}"
install_profile() {
    local selected="$1"
    local wheel_dir="$BM_DOWNLOADS/wheels/$selected"
    local python="$BM_ROOT/envs/$selected/bin/python"
    local lock="$wheel_dir/requirements.offline.txt"
    [[ -x "$python" ]] || python3 -m venv "$BM_ROOT/envs/$selected"
    [[ -s "$lock" ]] || { printf 'Finish the download profile first: %s\n' "$selected" >&2; return 1; }
    # The offline lock contains no remote URLs, including for the CPU-only torch wheel.
    "$python" -m pip install --no-index --find-links "$wheel_dir" --require-hashes -r "$lock"
    "$python" -m pip check
    "$python" -m pip freeze > "$BM_LOGS/$selected-installed.txt"
    "$python" "$PROJECT_ROOT/environment/scripts/smoke.py" "$selected"
}
case "$profile" in
    core|agentlab|webchore) install_profile "$profile" ;;
    images) "$BM_ROOT/envs/tools/bin/python" "$PROJECT_ROOT/environment/scripts/assets.py" load ;;
    runtimes)
        for selected in core agentlab webchore; do install_profile "$selected"; done
        ;;
    all)
        for selected in core agentlab webchore; do install_profile "$selected"; done
        "$BM_ROOT/envs/tools/bin/python" "$PROJECT_ROOT/environment/scripts/assets.py" load
        ;;
    *) printf 'Unknown profile: %s\n' "$profile" >&2; exit 2 ;;
esac
