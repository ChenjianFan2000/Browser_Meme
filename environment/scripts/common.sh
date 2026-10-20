#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
BM_ROOT=/opt/browser-meme
BM_DOWNLOADS="$PROJECT_ROOT/.runtime/downloads"
BM_LOGS="$PROJECT_ROOT/.runtime/logs"
export XDG_CACHE_HOME="$BM_ROOT/cache"
export TMPDIR="$BM_ROOT/tmp"
export PIP_CACHE_DIR="$XDG_CACHE_HOME/pip"
export UV_CACHE_DIR="$XDG_CACHE_HOME/uv"
export HF_HOME="$XDG_CACHE_HOME/huggingface"
export NLTK_DATA="$BM_ROOT/nltk_data"
export PLAYWRIGHT_BROWSERS_PATH="$BM_ROOT/browsers"
export PLAYWRIGHT_SKIP_BROWSER_GC=1
export npm_config_cache="$XDG_CACHE_HOME/npm"
export PYTHONNOUSERSITE=1
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_DEFAULT_TIMEOUT=30
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1
export PIP_PROGRESS_BAR=off
export PIP_RESUME_RETRIES="${PIP_RESUME_RETRIES:-10}"
export PATH="$BM_ROOT/bin:$PATH"
mkdir -p "$BM_DOWNLOADS" "$BM_LOGS" "$TMPDIR" "$XDG_CACHE_HOME"
MIRROR_MODE="${2:-cn}"
if [[ "$MIRROR_MODE" == cn ]]; then
    PYPI_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
else
    PYPI_INDEX=https://pypi.org/simple
fi
export PIP_INDEX_URL="$PYPI_INDEX"
export UV_DEFAULT_INDEX="$PYPI_INDEX"

download_file() {
    local target="$1" expected="$2"
    shift 2
    if [[ -f "$target" ]] && [[ "$(sha256sum "$target" | cut -d' ' -f1)" == "$expected" ]]; then
        printf 'Verified cached file: %s\n' "$target"
        return
    fi
    mkdir -p "$(dirname "$target")"
    local url
    for url in "$@"; do
        printf 'Downloading: %s\n' "$url"
        if curl --fail --location --retry 3 --retry-delay 2 --connect-timeout 10 \
            --speed-limit 1024 --speed-time 60 --continue-at - --output "$target.part" "$url"; then
            if [[ "$(sha256sum "$target.part" | cut -d' ' -f1)" != "$expected" ]]; then
                printf 'Checksum mismatch: %s; retained for inspection.\n' "$target.part" >&2
                return 1
            fi
            mv -- "$target.part" "$target"
            return
        fi
    done
    return 1
}
