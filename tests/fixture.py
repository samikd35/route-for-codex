"""Isolated deterministic Responses provider; never accepts commands from requests."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import threading


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


@contextmanager
def provider(callback):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers['Content-Length']))
            callback(self, raw)

        def start(self):
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()

        def event(self, kind, **payload):
            event = json.dumps(dict(type=kind, **payload))
            self.wfile.write(f'event: {kind}\ndata: {event}\n\n'.encode())
            self.wfile.flush()

    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield server.server_port
        finally:
            server.shutdown()
            worker.join()
