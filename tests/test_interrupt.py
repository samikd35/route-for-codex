import http.client
import socket
import threading
import time
import unittest

from route.relay import Relay
from tests.fixture import free_port, provider


class InterruptTest(unittest.TestCase):
    def test_cancel_drop_and_retry(self):
        calls = []
        cancelled = threading.Event()
        drop = threading.Event()

        def upstream(h, raw):
            calls.append(raw)
            if raw == b'drop':
                # Advertise more bytes than we send, after delivering a tool call.
                h.send_response(200)
                h.send_header('Content-Type', 'text/event-stream')
                h.send_header('Content-Length', '10000')
                h.end_headers()
                h.event('response.output_item.done', item={'type': 'function_call', 'call_id': 'fixture'})
                drop.wait(3)
                h.connection.shutdown(socket.SHUT_RDWR)
                return
            h.start()
            if raw == b'long':
                try:
                    for _ in range(100):
                        h.event('partial')
                        time.sleep(.02)
                except OSError:
                    cancelled.set()
            else:
                h.event('response.completed')

        with provider(upstream) as port:
            r = Relay(free_port(), 'dummy', origin=f'127.0.0.1:{port}')
            self.addCleanup(r.close)
            def start(body):
                c = http.client.HTTPConnection('127.0.0.1', r.port, timeout=4)
                self.addCleanup(c.close)
                c.request('POST', '/v1/responses', body, {'Authorization': 'Bearer ' + r.token})
                return c, c.getresponse()
            long, response = start(b'long')
            self.assertEqual(response.readline(), b'event: partial\n')
            _, interrupted = start(b'drop')
            self.assertIn(b'output_item.done', interrupted.readline())
            response.close()
            long.close()
            self.assertTrue(cancelled.wait(1), 'Provider kept generating after downstream cancelled')
            try:
                self.assertIn(b'response.completed', start(b'independent')[1].read())
            finally:
                drop.set()
            with self.assertRaises((http.client.IncompleteRead, ConnectionResetError)):
                interrupted.read()
            self.assertEqual(calls, [b'long', b'drop', b'independent'])
            self.assertIn(b'response.completed', start(b'explicit-retry')[1].read())
            self.assertEqual(len(calls), 4)
