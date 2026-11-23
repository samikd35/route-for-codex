import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from route.relay import Relay
from tests.fixture import free_port, provider


class RelayTest(unittest.TestCase):
    def test_stream_auth_rotation_and_status(self):
        calls = []
        release = threading.Event()
        received = threading.Event()

        def upstream(h, raw):
            calls.append((h.headers['Authorization'], raw))
            if raw == b'stream':
                h.start()
                h.event('first')
                received.set()
                release.wait(5)
                h.event('last')
            else:
                h.send_error(429)

        with tempfile.TemporaryDirectory(dir='/tmp') as d, provider(upstream) as port:
            r = Relay(free_port(), 'old-key', origin=f'127.0.0.1:{port}', admin=Path(d) / 'admin')
            self.addCleanup(r.close)

            def post(body, token):
                c = http.client.HTTPConnection('127.0.0.1', r.port, timeout=6)
                self.addCleanup(c.close)
                c.request('POST', '/v1/responses', body, {'Authorization': 'Bearer ' + token})
                return c.getresponse()

            self.assertEqual(post(b'ignored', 'bad').status, 401)
            self.assertFalse(calls)
            stream = post(b'stream', r.token)
            self.assertEqual(stream.readline(), b'event: first\n')
            self.assertTrue(received.wait(1))
            try:
                r.replace('new-key')
                body = json.dumps({'model': 'selected', 'input': 'fixture'}).encode()
                self.assertEqual(post(body, r.token).status, 429)
                self.assertEqual(calls, [('Bearer old-key', b'stream'), ('Bearer new-key', body)])
            finally:
                release.set()
            self.assertIn(b'event: last', stream.read())
