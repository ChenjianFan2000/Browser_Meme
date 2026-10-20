"""Fault injection against loopback HTTP and isolated files; no public downloads."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import socket
import sys
import tarfile
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'environment/scripts'))
import assets
import recovery
import wheelhouse

DATA = bytes(range(256)) * 1024
HASH = hashlib.sha256(DATA).hexdigest()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        requested = self.headers.get('Range', '')
        self.server.requests.append((self.path, requested))
        if self.path == '/missing':
            self.send_error(404)
            return
        offset = int(requested.removeprefix('bytes=').split('-')[0]) if requested else 0
        payload = b'x' * len(DATA) if self.path == '/bad' else DATA
        if offset >= len(payload):
            self.send_response(416)
            self.send_header('Content-Range', f'bytes */{len(payload)}')
            self.end_headers()
            return
        if self.path == '/no-range':
            offset = 0
        self.send_response(206 if offset else 200)
        self.send_header('Content-Length', str(len(payload) - offset))
        if offset:
            self.send_header('Content-Range', f'bytes {offset}-{len(payload)-1}/{len(payload)}')
        self.end_headers()
        if self.path == '/drop' and not offset:
            self.wfile.write(payload[:65536])
            self.wfile.flush()
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
        else:
            try:
                self.wfile.write(payload[offset:])
            except (BrokenPipeError, ConnectionResetError):
                pass


def docker_archive(path, include_layer=True):
    with tarfile.open(path, 'w') as archive:
        entries = {'manifest.json': json.dumps([{'RepoTags': ['test:latest'],
                   'Config': 'config.json', 'Layers': ['layer.tar']}]).encode(), 'config.json': b'{}'}
        if include_layer:
            entries['layer.tar'] = b'a' * 8192
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.server.daemon_threads = True
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        parent = ROOT / '.runtime/tmp'
        parent.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='recovery-test-', dir=parent)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.target = self.folder / 'asset.bin'
        self.partial = self.folder / 'asset.bin.part'
        self.server.requests = []
        self.environment = patch.dict(os.environ, {'BM_RETRY_DELAY': '0',
            'BM_DOWNLOAD_STATE': str(self.folder / 'state.json')})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def fetch(self, *routes, attempts=3):
        recovery.fetch(self.target, [self.base + route for route in routes], HASH, attempts=attempts)

    def test_connection_drop_resumes_from_received_bytes(self):
        self.fetch('/drop')
        self.assertEqual(self.target.read_bytes(), DATA)
        self.assertIn(('/drop', 'bytes=65536-'), self.server.requests)

    def test_verified_file_skips_network(self):
        self.target.write_bytes(DATA)
        self.fetch('/bad')
        self.assertEqual(self.server.requests, [])

    def test_completed_partial_publishes_without_network(self):
        self.partial.write_bytes(DATA)
        self.fetch('/bad')
        self.assertEqual(self.target.read_bytes(), DATA)
        self.assertEqual(self.server.requests, [])

    def test_http_404_fallback_preserves_partial(self):
        self.partial.write_bytes(DATA[:8192])
        self.fetch('/missing', '/ok')
        self.assertEqual(self.target.read_bytes(), DATA)
        self.assertIn(('/ok', 'bytes=8192-'), self.server.requests)

    def test_unsupported_range_restarts_and_keeps_rejected_data(self):
        self.partial.write_bytes(DATA[:8192])
        self.fetch('/no-range')
        self.assertEqual(self.target.read_bytes(), DATA)
        self.assertEqual(len(list(self.folder.glob('*.rejected-*'))), 1)

    def test_range_416_recovers_from_invalid_partial(self):
        self.partial.write_bytes(b'bad' * len(DATA))
        self.fetch('/ok')
        self.assertEqual(self.target.read_bytes(), DATA)

    def test_bad_checksum_never_publishes_and_retries_are_bounded(self):
        with self.assertRaises(RuntimeError):
            self.fetch('/bad', attempts=2)
        self.assertFalse(self.target.exists())
        self.assertEqual(len(self.server.requests), 2)

    def test_stalled_process_is_stopped(self):
        started = time.monotonic()
        result = recovery.run([sys.executable, '-c', 'import time; time.sleep(20)'],
                              'stall', idle_timeout=1, timeout=3)
        self.assertEqual(result, 124)
        self.assertLess(time.monotonic() - started, 5)

    def test_failed_process_retries_then_succeeds(self):
        marker = self.folder / 'attempt'
        program = 'from pathlib import Path; import sys; p=Path(sys.argv[1]); exists=p.exists(); p.touch(); sys.exit(0 if exists else 7)'
        result = recovery.run([sys.executable, '-c', program, str(marker)], 'retry', attempts=2)
        self.assertEqual(result, 0)

    def test_silent_transfer_with_growing_file_is_not_stalled(self):
        program = ('from pathlib import Path; import sys,time; p=Path(sys.argv[1]); '
                   '[(p.write_bytes(bytes(i+1)), time.sleep(1)) for i in range(7)]')
        result = recovery.run([sys.executable, '-c', program, str(self.partial)],
                              'file-progress', watch=[self.folder], idle_timeout=6, timeout=10)
        self.assertEqual(result, 0)

    def test_storage_failure_is_not_retried_as_network(self):
        result = recovery.run([sys.executable, '-c', 'raise SystemExit(75)'], 'storage', attempts=3)
        self.assertEqual(result, 75)
        self.assertEqual(json.loads((self.folder / 'state.json').read_text())['attempt'], 1)

    def test_wheel_receipt_detects_corruption_and_lock_change(self):
        wheel = self.folder / 'example-1.0-py3-none-any.whl'
        wheel.write_bytes(DATA)
        lock = self.folder / 'input.lock'
        lock.write_text('pinned requirements')
        recovery.atomic_json(self.folder / 'download-receipt.json', {
            'input_sha256': recovery.digest(lock), 'wheels': {wheel.name: HASH}})
        self.assertTrue(wheelhouse.verified_receipt(self.folder, lock))
        lock.write_text('changed requirements')
        self.assertFalse(wheelhouse.verified_receipt(self.folder, lock))
        lock.write_text('pinned requirements')
        wheel.write_bytes(b'corrupted')
        self.assertFalse(wheelhouse.verified_receipt(self.folder, lock))

    def test_cached_wheel_reuse_preserves_hash_requirements(self):
        source = self.folder / 'wheels/first'
        destination = self.folder / 'wheels/second'
        source.mkdir(parents=True)
        destination.mkdir()
        wheel = source / 'example-1.0-py3-none-any.whl'
        wheel.write_bytes(DATA)
        lock = self.folder / 'input.lock'
        lock.write_text(f'example==1.0 --hash=sha256:{HASH}\nmissing==2.0 --hash=sha256:abc\n')
        links = self.folder / 'links'
        wheelhouse.cache_links(destination, lock, links)
        output = self.folder / 'cached.lock'
        wheelhouse.cache_lock(lock, links, output)
        contents = output.read_text()
        self.assertIn(f'example @ {wheel.as_uri()} --hash=sha256:{HASH}', contents)
        self.assertIn('missing==2.0 --hash=sha256:abc', contents)

    def test_docker_archive_missing_layer_is_rejected(self):
        docker_archive(self.target, include_layer=False)
        with self.assertRaises(RuntimeError):
            assets.record_archive(self.target, 'test', 'test:latest')

    def test_docker_archive_truncated_layer_is_rejected(self):
        docker_archive(self.target)
        self.target.write_bytes(self.target.read_bytes()[:4096])
        with self.assertRaises((RuntimeError, tarfile.TarError)):
            assets.record_archive(self.target, 'test', 'test:latest')

    def test_missing_image_stops_before_any_docker_import(self):
        image_dir = self.folder / 'images'
        image_dir.mkdir()
        archive = image_dir / 'ready.tar'
        docker_archive(archive)
        assets.record_archive(archive, 'test', 'test:latest')
        catalog = {'gitlab': {'archive': 'ready.tar'},
                   'webarena_images': [{'filename': 'missing.tar'}]}
        with patch.object(assets, 'DOWNLOADS', self.folder), patch.dict(assets.CATALOG, catalog), \
                patch.object(assets.subprocess, 'run') as docker:
            with self.assertRaises(SystemExit) as stopped:
                assets.load_images()
        self.assertIn('missing.tar', str(stopped.exception))
        self.assertIn('Download-Images-CN.cmd', str(stopped.exception))
        docker.assert_not_called()

    def test_verified_images_can_be_imported(self):
        image_dir = self.folder / 'images'
        image_dir.mkdir()
        for name in ('first.tar', 'second.tar'):
            archive = image_dir / name
            docker_archive(archive)
            assets.record_archive(archive, 'test', 'test:latest')
        catalog = {'gitlab': {'archive': 'first.tar'},
                   'webarena_images': [{'filename': 'second.tar'}]}
        with patch.object(assets, 'DOWNLOADS', self.folder), patch.dict(assets.CATALOG, catalog), \
                patch.object(assets.subprocess, 'run') as docker:
            assets.load_images()
        self.assertEqual([call.args[0] for call in docker.call_args_list], [
            ['docker', 'load', '--input', str(image_dir / name)]
            for name in ('first.tar', 'second.tar')])

    def test_legacy_incomplete_final_is_resumed_and_validated(self):
        asset = {'filename': 'test.tar', 'image': 'test:latest', 'google_drive_id': 'test'}
        archive = self.folder / 'images/test.tar'
        archive.parent.mkdir()
        archive.write_bytes(b'old incomplete transfer')
        def complete(command, *args, **kwargs):
            target = Path(command[command.index('--target') + 1])
            self.assertEqual(target.read_bytes(), b'old incomplete transfer')
            docker_archive(target)
            return 0
        with patch.object(assets, 'DOWNLOADS', self.folder), patch.dict(assets.CATALOG,
                {'webarena_images': [asset]}), patch.object(assets, 'run', side_effect=complete):
            assets.download_webarena()
        self.assertTrue(assets.verified_archive(archive))

    def test_real_gdown_resumes_existing_incomplete_output(self):
        self.target.write_bytes(DATA[:8192])
        assets.download_gdrive(self.base + '/ok', self.target)
        self.assertEqual(self.target.read_bytes(), DATA)
        self.assertIn(('/ok', 'bytes=8192-'), self.server.requests)


if __name__ == '__main__':
    unittest.main(verbosity=2)
