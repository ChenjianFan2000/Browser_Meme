"""Sandbox-local TCP bridge to the one filesystem-visible trusted Unix gateway."""
import contextlib
import select
import socket
import socketserver
import threading


@contextlib.contextmanager
def playwright_proxy(socket_path):
    class Bridge(socketserver.BaseRequestHandler):
        def handle(self):
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
                upstream.connect(str(socket_path))
                while True:
                    ready, _, _ = select.select([self.request, upstream], [], [], 30)
                    if not ready:
                        return
                    for source in ready:
                        data = source.recv(65536)
                        if not data:
                            return
                        destination = upstream if source is self.request else self.request
                        destination.sendall(data)

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True

    with Server(('127.0.0.1', 0), Bridge) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield {'server': f'http://127.0.0.1:{server.server_address[1]}', 'bypass': '<-loopback>'}
        finally:
            server.shutdown()
            worker.join(timeout=5)
