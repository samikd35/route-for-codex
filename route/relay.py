import http.client
import json
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time


CADDY = Path(__file__).parent / ('bin/caddy.exe' if sys.platform == 'win32' else 'bin/caddy')
ORIGIN = 'api.openai.com:443'
API_PATHS = ['/v1/responses', '/v1/responses/compact', '/v1/images/generations', '/v1/images/edits']
MATCH_PATH = '/config/apps/http/servers/route/routes/0/match/0/path'


def configuration(port, token, key, origin=ORIGIN, admin=None):
    if not key or any(not 33 <= ord(c) <= 126 or c in '{}' for c in key):
        raise ValueError('Invalid credential format')
    transport = {'protocol': 'http', 'versions': ['1.1', '2']}
    if origin == ORIGIN:
        transport['tls'] = {}
    elif not origin.startswith('127.0.0.1:'):
        raise ValueError('Only loopback fixture origins are supported')
    proxy = {'handler': 'reverse_proxy', 'upstreams': [{'dial': origin}],
             'transport': transport, 'headers': {'request': {'set': {
                 'Host': [origin], 'Authorization': ['Bearer ' + key]}}}}
    routes = [{'match': [{'method': ['POST'], 'path': API_PATHS,
                          'header': {'Authorization': ['Bearer ' + token]}}],
               'handle': [proxy], 'terminal': True},
              {'handle': [{'handler': 'static_response', 'status_code': 401}]}]
    return {'admin': ({'listen': 'unix/' + str(admin), 'config': {'persist': False}}
                      if admin else {'disabled': True, 'config': {'persist': False}}),
            'logging': {'logs': {'default': {'writer': {'output': 'discard'}}}},
            'apps': {'http': {'servers': {'route': {'listen': [f'127.0.0.1:{port}'],
                                                    'routes': routes}}}}}


class Relay:
    def __init__(self, port, key, *, origin=ORIGIN, admin=None, detached=False):
        self.token = secrets.token_urlsafe(32)
        self.port, self.origin, self.admin = port, origin, admin
        config = configuration(port, self.token, key, origin, admin)
        self.process = subprocess.Popen([CADDY, 'run', '--config', '-'], stdin=subprocess.PIPE,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        start_new_session=detached and sys.platform != 'win32',
                                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        try:
            self.process.stdin.write(json.dumps(config).encode())
            self.process.stdin.close()
            for _ in range(200):
                if self.process.poll() is not None:
                    raise RuntimeError('Caddy could not start')
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=.1):
                        if admin is None or admin.exists():
                            return
                except OSError:
                    pass
                time.sleep(.01)
            raise RuntimeError('Caddy did not become ready')
        except BaseException:
            self.close()
            raise

    def replace(self, key):
        config = configuration(self.port, self.token, key, self.origin, self.admin)
        control(self.admin, '/load', config)

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()


def admin_socket(admin):
    """Open the private filesystem socket, including on CPython for Windows."""
    if sys.platform != 'win32':
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(10)
            sock.connect(str(admin))
            return sock
        except BaseException:
            sock.close()
            raise

    # Winsock supports AF_UNIX even on Python builds without its address converter.
    import ctypes
    import struct
    path = str(admin).encode('utf-8')
    if len(path) >= 108:
        raise OSError('Route home path exceeds the Windows socket path limit')
    address = struct.pack('=H108s', 1, path)
    ws = ctypes.WinDLL('ws2_32')
    ws.connect.argtypes = [ctypes.c_size_t, ctypes.c_char_p, ctypes.c_int]
    sock = socket.socket(1, socket.SOCK_STREAM)
    try:
        if ws.connect(sock.fileno(), address, len(address)):
            raise ctypes.WinError(ws.WSAGetLastError())
        sock.settimeout(10)
        return sock
    except BaseException:
        sock.close()
        raise


def control(admin, path, config=None):
    if sys.platform == 'win32' and CADDY.with_name('control.exe').is_file():
        subprocess.run([CADDY.with_name('control.exe'), str(admin), path],
                       input=json.dumps(config).encode() if config else b'', check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return
    conn = http.client.HTTPConnection('localhost', timeout=10)
    try:
        conn.sock = admin_socket(admin)
        conn.request('PATCH' if path == MATCH_PATH else 'POST', path, json.dumps(config) if config else b'', {'Content-Type': 'application/json'})
        if conn.getresponse().status != 200:
            raise RuntimeError('Caddy rejected the control request')
    finally:
        conn.close()


def combined_configuration(port, dispatcher_socket):
    """Stateless Caddy entry point for the combined-provider proof."""
    proxy = {'handler': 'reverse_proxy', 'upstreams': [{'dial': 'unix/' + str(dispatcher_socket)}],
             'transport': {'protocol': 'http', 'versions': ['1.1']}}
    return {'admin': {'disabled': True, 'config': {'persist': False}},
            'logging': {'logs': {'default': {'writer': {'output': 'discard'}}}},
            'apps': {'http': {'servers': {'combined': {'listen': [f'127.0.0.1:{port}'],
                                                       'routes': [{'handle': [proxy]}]}}}}}
