#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/common.sh"
action="${3:?Expected a site action}"
compose_dir="$PROJECT_ROOT/environment/compose"
compose() { docker compose -f "$compose_dir/$1.yml" "${@:2}"; }
wait_http() {
    local url="$1"
    for attempt in $(seq 1 90); do
        # Accept redirects before replacing the frozen images' original hostnames.
        if curl --fail --silent --max-time 10 "$url" -o /dev/null; then return; fi
        printf 'Waiting for %s (%s/90)...\n' "$url" "$attempt"
        sleep 10
    done
    printf 'Site not ready: %s; inspect Docker logs.\n' "$url" >&2
    return 1
}
case "$action" in
    gitlab-start)
        if [[ -n "$(compose webchore ps --status running -q)" ]]; then
            printf 'Stop WebChoreArena before starting the separate speed-test GitLab (memory budget).\n' >&2
            exit 1
        fi
        mkdir -p "$BM_ROOT/secrets"
        if [[ ! -f "$BM_ROOT/secrets/gitlab_root_password" ]]; then
            python3 -c 'import secrets; print(secrets.token_urlsafe(24))' > "$BM_ROOT/secrets/gitlab_root_password"
            chmod 600 "$BM_ROOT/secrets/gitlab_root_password"
        fi
        compose gitlab up -d
        wait_http http://127.0.0.1:8929/users/sign_in
        printf 'GitLab ready: http://localhost:8929 (root password in /opt/browser-meme/secrets/gitlab_root_password).\n'
        ;;
    gitlab-stop) compose gitlab stop ;;
    webchore-start)
        if [[ -n "$(compose gitlab ps --status running -q)" ]]; then
            printf 'Stop the speed-test GitLab before starting WebChoreArena (memory budget).\n' >&2
            exit 1
        fi
        compose webchore up -d
        wait_http http://127.0.0.1:7770
        wait_http http://127.0.0.1:7780
        for spec in 'shopping:7770' 'shopping-admin:7780'; do
            service="${spec%:*}"
            port="${spec#*:}"
            compose webchore exec -T "$service" /var/www/magento2/bin/magento setup:store-config:set --base-url="http://127.0.0.1:$port"
            compose webchore exec -T "$service" mysql -u magentouser -pMyPassword magentodb \
                -e "UPDATE core_config_data SET value='http://127.0.0.1:$port/' WHERE path='web/secure/base_url';"
            compose webchore exec -T "$service" /var/www/magento2/bin/magento cache:flush
        done
        compose webchore exec -T shopping-admin php /var/www/magento2/bin/magento config:set admin/security/password_is_forced 0
        compose webchore exec -T shopping-admin php /var/www/magento2/bin/magento config:set admin/security/password_lifetime 0
        compose webchore exec -T gitlab update-permissions
        compose webchore exec -T gitlab sed -i "s|^external_url.*|external_url 'http://127.0.0.1:8023'|" /etc/gitlab/gitlab.rb
        compose webchore exec -T gitlab gitlab-ctl reconfigure
        wait_http http://127.0.0.1:9999
        wait_http http://127.0.0.1:8023/users/sign_in
        systemctl --user daemon-reload
        systemctl --user start browser-meme-homepage.service
        wait_http http://127.0.0.1:4399
        printf 'Four WebChoreArena sites ready on ports 7770, 7780, 9999, 8023.\n'
        ;;
    webchore-stop)
        compose webchore stop
        systemctl --user stop browser-meme-homepage.service
        ;;
    *) printf 'Unknown action: %s\n' "$action" >&2; exit 2 ;;
esac
