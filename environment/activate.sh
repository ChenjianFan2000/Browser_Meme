#!/usr/bin/env bash
# Source this file inside WSL: source /mnt/g/Browser_Meme/environment/activate.sh core
_bm_profile="${1:-core}"
case "$_bm_profile" in core|agentlab|webchore) ;; *) printf 'Choose core, agentlab or webchore.\n'; return 2 ;; esac
if [[ ! -f "/opt/browser-meme/envs/$_bm_profile/bin/activate" ]]; then
    printf 'Run the prepare action for %s first.\n' "$_bm_profile" >&2
    return 1
fi
export XDG_CACHE_HOME=/opt/browser-meme/cache
export TMPDIR=/opt/browser-meme/tmp
export HF_HOME=/opt/browser-meme/cache/huggingface
export NLTK_DATA=/opt/browser-meme/nltk_data
export PLAYWRIGHT_BROWSERS_PATH=/opt/browser-meme/browsers
export PLAYWRIGHT_SKIP_BROWSER_GC=1
export PYTHONNOUSERSITE=1
source "/opt/browser-meme/envs/$_bm_profile/bin/activate"
if [[ -f /opt/browser-meme/secrets/research.env ]]; then
    set -a
    source /opt/browser-meme/secrets/research.env
    set +a
fi
# An empty base URL overrides the SDK default with an invalid endpoint.
if [[ -z "${OPENAI_BASE_URL:-}" ]]; then unset OPENAI_BASE_URL; fi
if [[ "$_bm_profile" == webchore ]]; then
    cd /opt/browser-meme/workspaces/WebChoreArena-542abc538fd9558362119714989166904d82f5f4/BrowserGym || return
fi
unset _bm_profile
