"""Create an offline, hash-checked wheel lock after the online build/download stage."""
import hashlib
from pathlib import Path
import re
import sys
import json
from packaging.utils import canonicalize_name, parse_wheel_filename
from recovery import atomic_json, digest


def verified_receipt(directory, lock):
    try:
        receipt = json.loads((directory / 'download-receipt.json').read_text())
        return (receipt['input_sha256'] == digest(lock) and bool(receipt['wheels'])
                and all((directory / name).is_file() and digest(directory / name) == expected
                        for name, expected in receipt['wheels'].items()))
    except (FileNotFoundError, ValueError, KeyError):
        return False


def cache_links(directory, lock, links):
    """Only expose wheels whose bytes match the original pinned requirements."""
    hashes = set(re.findall(r'--hash=sha256:([0-9a-f]{64})', lock.read_text()))
    links.mkdir(parents=True, exist_ok=True)
    for entry in links.glob('*.whl'):
        if entry.is_symlink():
            entry.unlink()
    count = 0
    candidates = sorted(set(directory.glob('*.whl')) | set(directory.parent.glob('*/*.whl')))
    for wheel in candidates:
        if digest(wheel) in hashes:
            link = links / wheel.name
            if not link.exists():
                link.symlink_to(wheel.resolve())
                count += 1
    print(f'Reusable hash-verified wheels: {count}', flush=True)


def cache_lock(lock, links, output):
    """Pin verified local bytes directly, avoiding needless index requests on resume."""
    available = {}
    for wheel in links.glob('*.whl'):
        name, version, _, _ = parse_wheel_filename(wheel.name)
        available[(name, str(version))] = wheel
    def replace(match):
        name, version = match.groups()
        wheel = available.get((canonicalize_name(name), version))
        return f'{name} @ {wheel.resolve().as_uri()}' if wheel else match[0]
    output.write_text(re.sub(r'(?m)^([\w.-]+)==([^\s\\]+)', replace, lock.read_text()))


def create_lock(directory: Path) -> None:
    packages = {}
    sums = []
    for wheel in sorted(directory.glob('*.whl')):
        name, version, _, _ = parse_wheel_filename(wheel.name)
        with wheel.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        previous = packages.get(name)
        if previous and previous[0] != str(version):
            raise RuntimeError(f'Multiple versions of {name} in {directory}; use a fresh wheelhouse.')
        packages.setdefault(name, (str(version), []))[1].append(digest)
        sums.append(f'{digest}  {wheel.name}')
    if not packages:
        raise RuntimeError('No wheels were downloaded.')
    lines = ['# Generated from locally built/downloaded wheels; no network URLs.']
    for name, (version, hashes) in sorted(packages.items()):
        lines.append(f'{name}=={version} ' + ' '.join(f'--hash=sha256:{h}' for h in hashes))
    for filename, content in [('requirements.offline.txt', lines), ('SHA256SUMS', sums)]:
        pending = directory / (filename + '.pending')
        pending.write_text('\n'.join(content) + '\n')
        pending.replace(directory / filename)
    print(f'Offline lock: {len(packages)} packages in {directory}')


if __name__ == '__main__':
    if sys.argv[1] == 'lock':
        create_lock(Path(sys.argv[2]))
    elif sys.argv[1] == 'check':
        raise SystemExit(0 if verified_receipt(Path(sys.argv[2]), Path(sys.argv[3])) else 1)
    elif sys.argv[1] == 'receipt':
        directory, lock = map(Path, sys.argv[2:4])
        create_lock(directory)
        atomic_json(directory / 'download-receipt.json', {
            'input_sha256': digest(lock),
            'wheels': {p.name: digest(p) for p in sorted(directory.glob('*.whl'))}})
    elif sys.argv[1] == 'cache-links':
        cache_links(*map(Path, sys.argv[2:5]))
    elif sys.argv[1] == 'cache-lock':
        cache_lock(*map(Path, sys.argv[2:5]))
    elif sys.argv[1] == 'local-torch':
        text = Path(sys.argv[2]).read_text()
        wheel = Path(sys.argv[4]) / 'torch-2.8.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl'
        text = re.sub(r'(?m)^torch @ \S+', 'torch @ ' + wheel.as_uri(), text)
        Path(sys.argv[3]).write_text(text)
    else:
        raise SystemExit('Expected lock, check, receipt, cache-links, or local-torch.')
