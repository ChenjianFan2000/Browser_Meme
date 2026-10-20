#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/common.sh"
profile="${1:-core}"
tools_python="$BM_ROOT/envs/tools/bin/python"
[[ -x "$tools_python" ]] || { printf 'Run prepare.sh first.\n' >&2; exit 1; }
exec 9>"$BM_ROOT/tmp/download.lock"
flock -n 9 || { printf 'Another download is already running.\n' >&2; exit 73; }
trap 'printf "Download interrupted; completed files and partial transfers retained.\\n"; exit 130' INT TERM
printf 'Download started: profile=%s mirror=%s; Ctrl+C stops safely.\n' "$profile" "$MIRROR_MODE"

retry_stage() {
    local label="$1"
    shift
    "$tools_python" -u "$PROJECT_ROOT/environment/scripts/recovery.py" \
        --label "$label" --attempts "${BM_STAGE_ATTEMPTS:-3}" \
        --timeout "${BM_STAGE_TIMEOUT:-7200}" --idle-timeout "${BM_STALL_TIMEOUT:-300}" \
        --watch "$BM_DOWNLOADS" --watch "$TMPDIR" --watch "$PIP_CACHE_DIR" \
        --watch "$PLAYWRIGHT_BROWSERS_PATH" -- "$@"
}

fallback_stage() {
    local result=0
    retry_stage "$@" || result=$?
    [[ "$result" != 75 && "$result" != 130 ]] || exit "$result"
    return "$result"
}

assets() {
    "$tools_python" -u "$PROJECT_ROOT/environment/scripts/recovery.py" \
        --label "assets-$1" --attempts 1 --timeout "${BM_IMAGE_TIMEOUT:-21600}" \
        --idle-timeout 300 --watch "$BM_DOWNLOADS" -- \
        "$tools_python" -u "$PROJECT_ROOT/environment/scripts/assets.py" "$1" --mirror "$MIRROR_MODE"
}
download_profile() {
    local selected="$1"
    local wheel_dir="$BM_DOWNLOADS/wheels/$selected"
    local lock="$PROJECT_ROOT/environment/requirements/$selected.lock"
    mkdir -p "$wheel_dir"
    [[ -s "$lock" ]] || { printf 'Missing lock file: %s\n' "$lock" >&2; return 1; }
    local download_lock="$lock"
    if [[ "$selected" != core ]]; then
        assets torch
        download_lock="$PROJECT_ROOT/.runtime/config/$selected-download.lock"
        "$tools_python" "$PROJECT_ROOT/environment/scripts/wheelhouse.py" local-torch "$lock" "$download_lock" "$BM_DOWNLOADS"
    fi
    if "$tools_python" "$PROJECT_ROOT/environment/scripts/wheelhouse.py" check "$wheel_dir" "$download_lock"; then
        printf 'Verified completed wheel stage: %s\n' "$selected"
    else
        local links="$BM_ROOT/tmp/verified-wheel-links/$selected"
        "$tools_python" "$PROJECT_ROOT/environment/scripts/wheelhouse.py" cache-links "$wheel_dir" "$download_lock" "$links"
        local cached_lock="$BM_ROOT/tmp/$selected-cached.lock"
        "$tools_python" "$PROJECT_ROOT/environment/scripts/wheelhouse.py" cache-lock "$download_lock" "$links" "$cached_lock"
        fallback_stage "wheels-$selected-$MIRROR_MODE" "$tools_python" -u -m pip wheel \
            --require-hashes --wheel-dir "$wheel_dir" --find-links "$links" --retries 5 \
            --timeout 30 --index-url "$PYPI_INDEX" -r "$cached_lock" \
            || retry_stage "wheels-$selected-official" "$tools_python" -u -m pip wheel \
            --require-hashes --wheel-dir "$wheel_dir" --find-links "$links" --retries 5 \
            --timeout 30 --index-url https://pypi.org/simple -r "$cached_lock"
        "$tools_python" "$PROJECT_ROOT/environment/scripts/wheelhouse.py" receipt "$wheel_dir" "$download_lock"
    fi
    # Install only the small Playwright downloader in a dedicated tool venv.
    # Application dependencies remain offline-installable in the wheelhouse.
    local pw_version=1.44.0
    [[ "$selected" == webchore ]] && pw_version=1.50.0
    local browser_env="$BM_ROOT/envs/playwright-$pw_version"
    [[ -x "$browser_env/bin/python" ]] || python3 -m venv "$browser_env"
    retry_stage "browser-tool-$selected" "$browser_env/bin/python" -u -m pip install \
        --no-index --find-links "$wheel_dir" "playwright==$pw_version"
    if [[ "$MIRROR_MODE" == cn ]]; then
        fallback_stage "chromium-$pw_version-cn" env PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright \
            PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=30000 "$browser_env/bin/python" -u -m playwright install chromium \
            || retry_stage "chromium-$pw_version-official" env -u PLAYWRIGHT_DOWNLOAD_HOST \
            PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=30000 "$browser_env/bin/python" -u -m playwright install chromium
    else
        retry_stage "chromium-$pw_version-official" env -u PLAYWRIGHT_DOWNLOAD_HOST \
            PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=30000 "$browser_env/bin/python" -u -m playwright install chromium
    fi
    # Both benchmarks use NLTK at import time. Cache public tokenizer resources now.
    if [[ "$selected" != core ]]; then
        assets nltk
    fi
    printf 'Download complete: %s\n' "$selected"
}
case "$profile" in
    core|agentlab|webchore) download_profile "$profile" ;;
    images) assets images ;;
    runtimes)
        for selected in core agentlab webchore; do download_profile "$selected"; done
        ;;
    all)
        for selected in core agentlab webchore; do download_profile "$selected"; done
        assets images
        ;;
    *) printf 'Unknown profile: %s\n' "$profile" >&2; exit 2 ;;
esac
