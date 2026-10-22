"""Trusted fixed-origin HTTP gateway. Run outside the learner's namespace.

The gateway never accepts CONNECT or chooses an upstream from a request. It
exposes HTTP browser requests to one configured origin, without business actions.
"""
import http.client
import os
import pathlib
import socketserver
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


HOP_HEADERS = {'connection', 'proxy-connection', 'proxy-authorization', 'proxy-authenticate', 'keep-alive', 'te', 'trailer', 'transfer-encoding', 'upgrade'}


def make_gateway(socket_path, public_origin, upstream_host, upstream_port, max_body=16 * 1024 * 1024):
    expected = urlsplit(public_origin)
    if expected.scheme != 'http' or not expected.hostname or expected.username or expected.password or expected.path not in ('', '/') or expected.query or expected.fragment:
        raise ValueError('public_origin must be one plain HTTP origin')
    expected_port = expected.port or 80
    authority = expected.netloc.lower()

    class Handler(BaseHTTPRequestHandler):
        def do_CONNECT(self):
            self.send_error(403, 'CONNECT denied')

        def forward(self):
            try:
                if any(ord(char) < 32 for char in self.path):
                    raise ValueError('control character')
                target = urlsplit(self.path)
                if target.scheme != 'http' or target.hostname != expected.hostname or (target.port or 80) != expected_port or target.username or target.password or target.fragment:
                    raise ValueError('destination denied')
                hosts = self.headers.get_all('Host', [])
                if len(hosts) != 1 or hosts[0].lower() != authority:
                    raise ValueError('Host mismatch')
                if self.headers.get('Transfer-Encoding') or self.headers.get('Upgrade'):
                    raise ValueError('unsupported framing')
                lengths = self.headers.get_all('Content-Length', [])
                if len(lengths) > 1:
                    raise ValueError('duplicate length')
                length = int(lengths[0]) if lengths else 0
                if length < 0 or length > max_body:
                    raise ValueError('body limit')
            except (ValueError, TypeError):
                self.send_error(403, 'Destination or framing denied')
                return
            body = self.rfile.read(length) if length else None
            if body is not None and len(body) != length:
                self.send_error(400, 'Incomplete request')
                return
            headers = {key: value for key, value in self.headers.items() if key.lower() not in HOP_HEADERS}
            # Preserve the public origin as Host for ordinary frontend routing.
            headers['Host'] = expected.netloc
            path = target.path or '/'
            if target.query:
                path += '?' + target.query
            upstream = http.client.HTTPConnection(upstream_host, int(upstream_port), timeout=30)
            try:
                upstream.request(self.command, path, body=body, headers=headers)
                response = upstream.getresponse()
                self.send_response(response.status, response.reason)
                for key, value in response.getheaders():
                    if key.lower() not in HOP_HEADERS:
                        self.send_header(key, value)
                self.end_headers()
                if self.command != 'HEAD':
                    while chunk := response.read(65536):
                        self.wfile.write(chunk)
            except (OSError, http.client.HTTPException):
                self.close_connection = True
            finally:
                upstream.close()

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = forward

        def log_message(self, *args):
            pass

    class Gateway(socketserver.ThreadingUnixStreamServer):
        daemon_threads = True

    socket_path = pathlib.Path(socket_path)
    if socket_path.exists():
        raise FileExistsError(socket_path)
    server = Gateway(str(socket_path), Handler)
    os.chmod(socket_path, 0o600)
    return server
