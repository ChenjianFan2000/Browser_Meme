"""Download public assets, preserving partial files and recording their provenance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import zipfile
from recovery import atomic_json, digest, fetch, quarantine, run, StorageError, STORAGE_ERRORS, install_signal_handlers

ROOT = Path(__file__).resolve().parents[2]
DOWNLOADS = ROOT / '.runtime/downloads'
CATALOG = json.loads((ROOT / 'environment/assets.lock.json').read_text())


def sha256(path):
    return digest(path)


def download_torch(mirror):
    asset = CATALOG['torch']
    urls = [asset['official']]
    if mirror == 'cn':
        urls.insert(0, asset['cn'])
    fetch(DOWNLOADS / asset['filename'], urls, asset['sha256'])


def download_nltk(mirror='cn'):
    destination = Path(os.environ.get('NLTK_DATA', '/opt/browser-meme/nltk_data')) / 'tokenizers'
    destination.mkdir(parents=True, exist_ok=True)
    for asset in CATALOG['nltk']:
        name = asset['name']
        archive = DOWNLOADS / 'nltk' / f'{name}.zip'
        url = f'https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/tokenizers/{name}.zip'
        urls = [url]
        if mirror == 'cn':
            urls.insert(0, f'https://cdn.jsdelivr.net/gh/nltk/nltk_data@gh-pages/packages/tokenizers/{name}.zip')
        fetch(archive, urls, asset['sha256'])
        with zipfile.ZipFile(archive) as zipped:
            for item in zipped.infolist():
                resolved = (destination / item.filename).resolve()
                if not resolved.is_relative_to(destination.resolve()):
                    raise RuntimeError('Unsafe path in NLTK archive.')
            zipped.extractall(destination)


def record_archive(path, source, image):
    size = path.stat().st_size
    with tarfile.open(path) as archive:
        try:
            manifest = json.load(archive.extractfile('manifest.json'))
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise RuntimeError(f'Not a valid Docker archive: {path}') from error
        tags = [tag for entry in manifest for tag in entry.get('RepoTags', [])]
        if image not in tags:
            raise RuntimeError(f'{path.name}: expected image tag {image}, found {tags}')
        members = {item.name: item for item in archive}
        for entry in manifest:
            for name in [entry['Config'], *entry['Layers']]:
                item = members.get(name)
                if item is None or not item.isfile() or item.offset_data + item.size > size:
                    raise RuntimeError(f'Incomplete Docker archive member: {name}')
    receipt = {'filename': path.name, 'bytes': path.stat().st_size,
               'sha256': sha256(path), 'source': source, 'image': image}
    atomic_json(path.with_suffix(path.suffix + '.json'), receipt)
    return receipt


def verified_archive(path):
    receipt = path.with_suffix(path.suffix + '.json')
    if path.exists() and receipt.exists():
        try:
            return sha256(path) == json.loads(receipt.read_text())['sha256']
        except (ValueError, KeyError):
            return False
    return False


def download_gitlab(mirror):
    asset = CATALOG['gitlab']
    target = DOWNLOADS / 'images' / asset['archive']
    target.parent.mkdir(parents=True, exist_ok=True)
    if verified_archive(target):
        print(f'Cached GitLab archive: {target}', flush=True)
        return
    reference = f"{asset['image']}@{asset['digest']}"
    references = [reference]
    if mirror == 'cn':
        references.insert(0, 'm.daocloud.io/' + reference)
    for pull_reference in references:
        code = run(['docker', 'pull', pull_reference], 'GitLab image layers', attempts=3)
        if code == 75:
            raise StorageError('Storage unavailable while pulling GitLab layers.')
        if code == 0:
            tag = f"gitlab/gitlab-ce:{asset['tag']}"
            subprocess.run(['docker', 'tag', pull_reference, tag], check=True)
            partial = Path(str(target) + '.part')
            code = run(['docker', 'save', '-o', str(partial), tag], 'GitLab archive',
                       watch=[partial], idle_timeout=300)
            if code == 75:
                raise StorageError('Storage unavailable while saving GitLab archive.')
            if code != 0:
                raise RuntimeError('GitLab archive save failed; downloaded image layers retained.')
            record_archive(partial, reference, tag)
            partial.replace(target)
            receipt = partial.with_suffix(partial.suffix + '.json')
            data = json.loads(receipt.read_text())
            data['filename'] = target.name
            atomic_json(target.with_suffix(target.suffix + '.json'), data)
            receipt.unlink()
            return
    raise RuntimeError('GitLab pull failed for both the domestic mirror and the official registry.')


def download_webarena():
    failures = []
    for asset in CATALOG['webarena_images']:
        target = DOWNLOADS / 'images' / asset['filename']
        target.parent.mkdir(parents=True, exist_ok=True)
        if verified_archive(target):
            print(f'Cached: {target.name}', flush=True)
            continue
        try:
            # Use the Google Drive links listed by upstream; availability/quota may vary.
            # No guessed/public Docker Hub mirror is substituted for benchmark data.
            source = 'https://drive.google.com/uc?id=' + asset['google_drive_id']
            partial = Path(str(target) + '.part')
            if target.exists():
                # Older versions wrote unfinished archives under the final filename.
                if partial.exists():
                    quarantine(target)
                else:
                    target.replace(partial)
            # A completed archive may have survived a crash before receipt publication.
            ready = False
            if partial.exists():
                try:
                    record_archive(partial, source, asset['image'])
                    ready = True
                except (tarfile.TarError, RuntimeError, EOFError):
                    pass
            if not ready:
                code = run([os.sys.executable, '-u', __file__, 'gdrive-worker',
                            '--source', source, '--target', str(partial)], target.name,
                           attempts=3, timeout=int(os.environ.get('BM_IMAGE_TIMEOUT', '21600')),
                           idle_timeout=300, watch=[partial.parent])
                if code == 75:
                    raise StorageError('Storage unavailable during Google Drive transfer.')
                if code:
                    raise RuntimeError('Google Drive transfer failed; partial data retained for resume.')
                record_archive(partial, source, asset['image'])
            partial.replace(target)
            receipt = partial.with_suffix(partial.suffix + '.json')
            data = json.loads(receipt.read_text())
            data['filename'] = target.name
            atomic_json(target.with_suffix(target.suffix + '.json'), data)
            receipt.unlink()
        except Exception as error:
            if isinstance(error, StorageError) or isinstance(error, OSError) and error.errno in STORAGE_ERRORS:
                raise SystemExit(75) from error
            failures.append(f"{asset['filename']}: {error}")
    if failures:
        raise RuntimeError('\n'.join(failures))


def load_images():
    filenames = [CATALOG['gitlab']['archive']] + [a['filename'] for a in CATALOG['webarena_images']]
    missing = []
    for name in filenames:
        path = DOWNLOADS / 'images' / name
        if not verified_archive(path):
            missing.append(name)
    if missing:
        raise SystemExit(
            'Image import cannot start. Missing or unverified image archives:\n  '
            + '\n  '.join(missing)
            + '\n\nComplete-Runtimes-CN.cmd installs Python environments and browsers only.'
            + '\nRun Download-Images-CN.cmd first (about 210 GB).'
            + '\nAfter it finishes successfully, rerun Install-Images.cmd.'
        )
    for name in filenames:
        subprocess.run(['docker', 'load', '--input', str(DOWNLOADS / 'images' / name)], check=True)


def download_gdrive(source, target):
    import gdown
    target = Path(target)
    if target.exists():
        # gdown skips any existing output, even an incomplete legacy file.
        # Move it into gdown's resumable temporary-file namespace first.
        temporary = list(target.parent.glob(target.name + '*.part'))
        temporary = [path for path in temporary if path != target]
        if temporary:
            raise RuntimeError(f'Ambiguous partial files for {target}; retained for inspection.')
        target.replace(target.with_name(target.name + '.resume.part'))
    return gdown.download(source, str(target), quiet=False, resume=True, use_cookies=False,
                          timeout=(10, 60), retries=5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['torch', 'nltk', 'images', 'load', 'gdrive-worker'])
    parser.add_argument('--mirror', choices=['cn', 'official'], default='cn')
    parser.add_argument('--source')
    parser.add_argument('--target')
    args = parser.parse_args()
    if args.action == 'torch':
        download_torch(args.mirror)
    elif args.action == 'nltk':
        download_nltk(args.mirror)
    elif args.action == 'images':
        errors = []
        for action in (lambda: download_gitlab(args.mirror), download_webarena):
            try:
                action()
            except Exception as error:
                if isinstance(error, StorageError) or isinstance(error, OSError) and error.errno in STORAGE_ERRORS:
                    raise SystemExit(75) from error
                errors.append(str(error))
        if errors:
            raise SystemExit('\n'.join(errors))
    elif args.action == 'load':
        load_images()
    elif args.action == 'gdrive-worker':
        if not args.source or not args.target:
            parser.error('gdrive-worker requires --source and --target')
        if download_gdrive(args.source, args.target) is None:
            raise SystemExit('Google Drive quota/access/network error; retry later.')


if __name__ == '__main__':
    install_signal_handlers()
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
    except (OSError, StorageError) as error:
        print(str(error), flush=True)
        raise SystemExit(75 if isinstance(error, StorageError) or error.errno in STORAGE_ERRORS else 1)
