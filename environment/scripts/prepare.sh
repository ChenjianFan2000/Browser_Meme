#!/usr/bin/env bash
# Resolve dependencies and prepare small build tools, without downloading large wheels/images.
set -Eeuo pipefail
source "$(dirname "$0")/common.sh"
profile="${1:-core}"
case "$profile" in
    core|agentlab|webchore) profiles=("$profile") ;;
    all|runtimes) profiles=(core agentlab webchore) ;;
    images) profiles=() ;;
    *) printf 'Unknown profile: %s\n' "$profile" >&2; exit 2 ;;
esac
tools_env="$BM_ROOT/envs/tools"
[[ -x "$tools_env/bin/python" ]] || python3 -m venv "$tools_env"
if [[ ! -x "$tools_env/bin/uv" ]] || ! "$tools_env/bin/python" -c 'import build, hatchling, gdown, setuptools' >/dev/null 2>&1; then
    "$tools_env/bin/python" -m pip install --index-url "$PYPI_INDEX" \
        'pip==25.2' 'uv==0.13.1' build wheel setuptools hatchling hatch-requirements-txt gdown \
        || "$tools_env/bin/python" -m pip install --index-url https://pypi.org/simple \
        'pip==25.2' 'uv==0.13.1' build wheel setuptools hatchling hatch-requirements-txt gdown
fi
ln -sfn "$tools_env/bin/uv" "$BM_ROOT/bin/uv"
"$tools_env/bin/python" -m pip freeze > "$BM_LOGS/tooling-versions.txt"
mkdir -p "$BM_ROOT/secrets" "$BM_ROOT/homepage" "$HOME/.config/systemd/user"
if [[ ! -f "$BM_ROOT/secrets/research.env" ]]; then
    cp "$PROJECT_ROOT/environment/config.example.env" "$BM_ROOT/secrets/research.env"
    chmod 600 "$BM_ROOT/secrets/research.env"
fi
prepare_homepage() {
cp "$PROJECT_ROOT/environment/homepage/"*.html "$BM_ROOT/homepage/"
cat > "$HOME/.config/systemd/user/browser-meme-homepage.service" <<'EOF'
[Unit]
Description=WebArena benchmark homepage (local only)
[Service]
ExecStart=/usr/bin/python3 -m http.server 4399 --bind 127.0.0.1 --directory /opt/browser-meme/homepage
Restart=on-failure
EOF
}
prepare_webchore() {
source_commit=542abc538fd9558362119714989166904d82f5f4
source_archive="$BM_DOWNLOADS/webchorearena-$source_commit.tar.gz"
download_file "$source_archive" 8ee1cc2b64d0f094d70c9ce6ac9e37b857bd4c410ff028153aaca0ae841ac60a \
    "https://codeload.github.com/WebChoreArena/WebChoreArena/tar.gz/$source_commit"
source_root="$BM_ROOT/workspaces/WebChoreArena-$source_commit"
if [[ ! -d "$source_root" ]]; then tar -xzf "$source_archive" -C "$BM_ROOT/workspaces"; fi
wheel_dir="$BM_DOWNLOADS/wheels/webchore"
mkdir -p "$wheel_dir"
export SOURCE_DATE_EPOCH=1704067200
for package in core experiments webarena webchorearena; do
    # Reuse wheels referenced by an existing hash lock instead of rebuilding them.
    if ! compgen -G "$wheel_dir/browsergym_${package}-0.13.3-*.whl" >/dev/null; then
        "$tools_env/bin/python" -m build --wheel --no-isolation \
            --outdir "$wheel_dir" "$source_root/BrowserGym/browsergym/$package"
    fi
done
mkdir -p "$PROJECT_ROOT/.runtime/config"
generated_input="$PROJECT_ROOT/.runtime/config/webchore.in"
cat "$PROJECT_ROOT/environment/requirements/webchore.in" > "$generated_input"
for wheel in "$wheel_dir"/browsergym*0.13.3*.whl; do
    printf '%s\n' "$wheel" >> "$generated_input"
done
}
if [[ "$profile" == all || "$profile" == runtimes || "$profile" == webchore || "$profile" == images ]]; then
    prepare_homepage
fi
for profile in "${profiles[@]}"; do
    input="$PROJECT_ROOT/environment/requirements/$profile.in"
    if [[ "$profile" == webchore ]]; then
        prepare_webchore
        input="$generated_input"
    fi
    lock="$PROJECT_ROOT/environment/requirements/$profile.lock"
    if [[ ! -s "$lock" ]]; then
        printf 'Resolving %s dependencies...\n' "$profile"
        "$tools_env/bin/uv" pip compile "$input" --python-version 3.12 \
            --generate-hashes --no-annotate --default-index "$PYPI_INDEX" --output-file "$lock.pending" > "$BM_LOGS/resolve-$profile.log" \
            || "$tools_env/bin/uv" pip compile "$input" --python-version 3.12 \
            --generate-hashes --no-annotate --default-index https://pypi.org/simple --output-file "$lock.pending" > "$BM_LOGS/resolve-$profile.log"
        mv -- "$lock.pending" "$lock"
    fi
    [[ -x "$BM_ROOT/envs/$profile/bin/python" ]] || python3 -m venv "$BM_ROOT/envs/$profile"
    printf 'Prepared dependency lock and virtual environment: %s\n' "$profile"
done
printf 'Preparation complete. Application packages, browsers and images use the download/install actions.\n'
