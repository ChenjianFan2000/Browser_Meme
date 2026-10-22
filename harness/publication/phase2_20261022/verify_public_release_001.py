"""Verify a published release without authentication; write a new public receipt."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

import requests


class AnonymousAuth(requests.auth.AuthBase):
    def __call__(self, request):
        request.headers.pop('Authorization', None)
        return request


def sha(data):
    return hashlib.sha256(data).hexdigest()


def public_get(url, *, redirects=False):
    hosts = {'api.github.com', 'github.com', 'release-assets.githubusercontent.com',
             'objects.githubusercontent.com'}
    for _ in range(5):
        parts = urlsplit(url)
        if (parts.scheme != 'https' or parts.hostname not in hosts or
                parts.username is not None or parts.password is not None or
                parts.port not in (None, 443)):
            raise ValueError('public_url_host_guard')
        response = requests.get(url, auth=AnonymousAuth(), allow_redirects=False,
                                timeout=(15, 60), stream=True,
                                headers={'Accept': 'application/vnd.github+json',
                                         'X-GitHub-Api-Version': '2022-11-28'})
        try:
            if redirects and response.status_code in (301, 302, 303, 307, 308):
                url = response.headers.get('Location', '')
                continue
            if response.status_code != 200:
                raise ValueError('anonymous_http_status_' + str(response.status_code))
            blocks = []; total = 0
            for block in response.iter_content(64 * 1024):
                total += len(block)
                if total > 4 * 1024 * 1024:
                    raise ValueError('public_metadata_size_guard')
                blocks.append(block)
            return b''.join(blocks)
        finally:
            response.close()
    raise ValueError('public_redirect_limit')


def verify(plan_path, registration_path):
    plan_bytes = plan_path.read_bytes()
    plan = json.loads(plan_bytes)
    registration = json.loads(registration_path.read_bytes())
    repository = 'ChenjianFan2000/Browser_Meme'
    if plan['repository'] != repository or registration['repository'] != repository:
        raise ValueError('repository_guard')
    if sha(plan_bytes) != registration['plan_sha256']:
        raise ValueError('plan_binding_guard')
    api = 'https://api.github.com/repos/' + repository
    repo = json.loads(public_get(api))
    if (repo.get('full_name') != repository or repo.get('private') is not False or
            repo.get('visibility') != 'public'):
        raise ValueError('public_repository_guard')
    release = json.loads(public_get(api + '/releases/tags/' + plan['tag']))
    if (release.get('id') != registration['release_id'] or
            release.get('tag_name') != plan['tag'] or release.get('draft') is not False or
            release.get('target_commitish') != plan['target_commit'] or
            not release.get('published_at')):
        raise ValueError('published_release_identity_guard')
    if sha(release['body'].encode('utf-8')) != plan['body_sha256']:
        raise ValueError('public_release_body_hash_guard')
    commit = json.loads(public_get(api + '/commits/' + plan['tag']))
    if commit.get('sha') != plan['target_commit']:
        raise ValueError('public_tag_commit_guard')
    assets = []; page = 1
    while True:
        batch = json.loads(public_get(api + '/releases/' + str(release['id']) +
                                      '/assets?per_page=100&page=' + str(page)))
        assets.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    planned = {row['name']: row for row in plan['assets']}
    if len(assets) != len(planned) or {a['name'] for a in assets} != set(planned):
        raise ValueError('public_asset_inventory_guard')
    verified = []
    for asset in assets:
        expected = planned[asset['name']]
        download = ('https://github.com/' + repository + '/releases/download/' +
                    plan['tag'] + '/' + asset['name'])
        if (asset.get('state') != 'uploaded' or asset.get('size') != expected['size'] or
                asset.get('digest') != 'sha256:' + expected['sha256'] or
                asset.get('browser_download_url') != download):
            raise ValueError('public_asset_digest_size_url_guard')
        verified.append({'name': asset['name'], 'asset_id': asset['id'],
                         'size': expected['size'], 'sha256': expected['sha256'],
                         'download_url': download, 'api_url': asset['url'],
                         'verification': 'anonymous_github_sha256_digest'})
    check_name = 'RELEASE-SHA256SUMS.txt'
    check_url = next(a['download_url'] for a in verified if a['name'] == check_name)
    downloaded = public_get(check_url, redirects=True)
    if sha(downloaded) != planned[check_name]['sha256'] or len(downloaded) != planned[check_name]['size']:
        raise ValueError('anonymous_checksum_download_guard')
    return {'schema_version': 1, 'status': 'public_release_verified',
            'verified_at_utc': datetime.now(timezone.utc).isoformat(),
            'authentication_used': False, 'repository': repository,
            'release_id': release['id'], 'tag': plan['tag'],
            'target_commit': plan['target_commit'], 'html_url': release['html_url'],
            'published_at': release['published_at'], 'draft': False,
            'plan_sha256': sha(plan_bytes), 'release_body_sha256': plan['body_sha256'],
            'assets_count': len(verified), 'assets_bytes': sum(a['size'] for a in verified),
            'assets': sorted(verified, key=lambda a: a['name']),
            'anonymous_download': {'name': check_name, 'size': len(downloaded),
                                   'sha256': sha(downloaded)},
            'verification_scope': 'All asset digests and sizes from anonymous GitHub API; '
                                  'checksum attachment downloaded and hashed. Large ZIPs '
                                  'were not redundantly downloaded.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--registration', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('exclusive_output_required')
    try:
        result = verify(args.plan, args.registration)
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, indent=2, ensure_ascii=False)
            handle.write('\n')
        print(json.dumps({k: result[k] for k in ('status', 'html_url', 'assets_count', 'assets_bytes')}))
    except Exception as error:
        # Never emit redirect URLs, response bodies, request headers or credentials.
        message = str(error) if type(error) is ValueError else type(error).__name__
        print(json.dumps({'status': 'error', 'error_type': message}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
