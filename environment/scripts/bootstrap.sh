#!/usr/bin/env bash
set -Eeuo pipefail
[[ "$(id -u)" == 0 ]] || { printf 'Run bootstrap through research.ps1.\n' >&2; exit 1; }
source "$(dirname "$0")/common.sh"
. /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 ]] || { printf 'Ubuntu 24.04 is required.\n' >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive
mkdir -p /etc/apt/apt.conf.d /etc/apt/sources.list.d /etc/apt/keyrings
cat > /etc/apt/apt.conf.d/80browser-meme <<'EOF'
Acquire::Retries "2";
Acquire::http::Timeout "20";
Acquire::https::Timeout "20";
APT::Install-Recommends "false";
EOF
configure_ubuntu() {
    cat > /etc/apt/sources.list.d/ubuntu.sources <<EOF
Types: deb
URIs: $1
Suites: noble noble-updates noble-security
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
EOF
}
ubuntu_mirror=http://mirrors.ustc.edu.cn/ubuntu
[[ "$MIRROR_MODE" == official ]] && ubuntu_mirror=http://archive.ubuntu.com/ubuntu
configure_ubuntu "$ubuntu_mirror"
if ! apt-get -o APT::Update::Error-Mode=any update; then
    configure_ubuntu http://archive.ubuntu.com/ubuntu
    apt-get -o APT::Update::Error-Mode=any update
fi
apt-get install -y ca-certificates curl gnupg systemd systemd-sysv dbus libpam-systemd dbus-user-session \
    sudo locales git git-lfs unzip xz-utils zip rsync jq aria2 wget \
    build-essential pkg-config python3 python3-venv python3-dev python3-pip \
    libffi-dev libssl-dev libxml2-dev libxslt1-dev zlib1g-dev \
    iproute2 iptables procps util-linux openssh-client fonts-noto-cjk \
    fonts-liberation libnss3 libatk1.0-0t64 libatk-bridge2.0-0t64 \
    libcups2t64 libdrm2 libxkbcommon0 libatspi2.0-0t64 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2t64 libpango-1.0-0 libcairo2

sed -i 's/^# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen
locale-gen en_US.UTF-8
update-locale LANG=en_US.UTF-8
# Switch transport to HTTPS after installing the base CA certificate store.
sed -i 's|http://|https://|g' /etc/apt/sources.list.d/ubuntu.sources

docker_base=https://mirrors.ustc.edu.cn/docker-ce/linux/ubuntu
[[ "$MIRROR_MODE" == official ]] && docker_base=https://download.docker.com/linux/ubuntu
if ! curl -fsSL --connect-timeout 8 --max-time 20 "$docker_base/gpg" -o /etc/apt/keyrings/docker.asc; then
    docker_base=https://download.docker.com/linux/ubuntu
    curl -fsSL --retry 3 --connect-timeout 10 "$docker_base/gpg" -o /etc/apt/keyrings/docker.asc
fi
gpg --batch --show-keys --with-colons /etc/apt/keyrings/docker.asc | grep -q '9DC858229FC7DD38854AE2D88D81803C0EBFCD88'
chmod 644 /etc/apt/keyrings/docker.asc
printf 'deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] %s noble stable\n' "$docker_base" > /etc/apt/sources.list.d/docker.list
if ! apt-get -o APT::Update::Error-Mode=any update; then
    printf 'deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable\n' > /etc/apt/sources.list.d/docker.list
    apt-get -o APT::Update::Error-Mode=any update
fi
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
mkdir -p /etc/docker
if [[ ! -f /etc/docker/daemon.json ]]; then
    cat > /etc/docker/daemon.json <<'EOF'
{
  "data-root": "/var/lib/docker",
  "log-driver": "local",
  "log-opts": {"max-size": "10m", "max-file": "3"}
}
EOF
fi
if ! id research >/dev/null 2>&1; then useradd --create-home --shell /bin/bash research; fi
usermod -aG docker research
mkdir -p "$BM_ROOT"/{envs,bin,cache,tmp,browsers,nltk_data,workspaces}
chown research:research "$BM_ROOT" "$BM_ROOT"/{envs,bin,cache,tmp,browsers,nltk_data,workspaces}
chmod 1777 "$BM_ROOT/tmp"
cat > /etc/wsl.conf <<'EOF'
[boot]
systemd=true
[user]
default=research
[interop]
appendWindowsPath=false
[automount]
enabled=false
mountFsTab=false
EOF
research_uid="$(id -u research)"
research_gid="$(id -g research)"
mkdir -p /mnt/g
if ! grep -q '^G: /mnt/g ' /etc/fstab; then
    printf 'G: /mnt/g drvfs noauto,metadata,uid=%s,gid=%s,umask=022 0 0\n' "$research_uid" "$research_gid" >> /etc/fstab
fi
cat > /etc/profile.d/browser-meme.sh <<'EOF'
export XDG_CACHE_HOME=/opt/browser-meme/cache
export TMPDIR=/opt/browser-meme/tmp
export PIP_CACHE_DIR=/opt/browser-meme/cache/pip
export HF_HOME=/opt/browser-meme/cache/huggingface
export PLAYWRIGHT_BROWSERS_PATH=/opt/browser-meme/browsers
export PLAYWRIGHT_SKIP_BROWSER_GC=1
export NLTK_DATA=/opt/browser-meme/nltk_data
export PYTHONNOUSERSITE=1
export PATH=/opt/browser-meme/bin:$PATH
EOF
dpkg-query -W -f='${Package}\t${Version}\n' > "$BM_LOGS/apt-installed.tsv"
printf 'Bootstrap complete. The launcher will restart this distro to enable systemd and Docker.\n'
