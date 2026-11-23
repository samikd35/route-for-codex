import asyncio
import base64
import http.client
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from PIL import Image

from route.cli import Session, execute
from route.images import TOOL_SECONDS, png_bytes
from route.relay import Relay, control
from route.settings import config, config_path, write
from tests.fixture import free_port, provider


class ImageTest(unittest.TestCase):
    def test_stdio_generation_and_relay_upgrade(self):
        buffer = io.BytesIO()
        Image.new('RGB', (2, 2), 'blue').save(buffer, 'PNG')
        png = buffer.getvalue()
        calls = []

        def upstream(h, raw):
            calls.append((h.path, h.headers['Authorization'], json.loads(raw)))
            prompt = calls[-1][2]['prompt']
            if prompt == 'limited':
                h.send_error(429)
                return
            b64 = base64.b64encode(png if prompt != 'invalid' else png[:30]).decode()
            body = json.dumps({'data': [{'b64_json': b64}]}).encode()
            h.send_response(200)
            h.send_header('Content-Length', str(len(body)))
            h.end_headers()
            h.wfile.write(body)

        with tempfile.TemporaryDirectory() as d, provider(upstream) as origin, \
                patch.dict(os.environ, ROUTE_HOME=d, CODEX_HOME=d), patch('route.cli.PORT', free_port()) as port:
            s = Session()
            s.load()
            relay = Relay(port, 'project', origin=f'127.0.0.1:{origin}', admin=s.admin)
            try:
                write(s.credential, relay.token)
                # Reproduce an active pre-upgrade relay with only the Responses matcher.
                from route.relay import MATCH_PATH
                control(s.admin, MATCH_PATH, ['/v1/responses'])
                def request(path, token, method='POST'):
                    c = http.client.HTTPConnection('127.0.0.1', port)
                    try:
                        c.request(method, path, b'{}', {'Authorization': 'Bearer ' + token})
                        return c.getresponse().status
                    finally:
                        c.close()
                path = '/v1/images/generations'
                self.assertEqual(request(path, relay.token), 401)
                for _ in range(2):
                    execute(s, 'reconnect', Mock())
                self.assertEqual(request(path, 'invalid'), 401)
                self.assertEqual(request(path + '/extra', relay.token), 401)
                self.assertEqual(request(path, relay.token, 'GET'), 401)
                self.assertFalse(calls)
                entry = config()['mcp_servers']['route_images']
                self.assertEqual(entry['tool_timeout_sec'], TOOL_SECONDS)
                async def exercise():
                    params = StdioServerParameters(command=entry['command'], args=list(entry['args']))
                    async with stdio_client(params) as streams, ClientSession(*streams) as client:
                        await client.initialize()
                        self.assertEqual([t.name for t in (await client.list_tools()).tools], ['generate_image'])
                        async def call(prompt):
                            return await client.call_tool('generate_image', {'prompt': prompt})
                        results = await asyncio.gather(call('blue'), call('green'))
                        paths = []
                        for result in results:
                            self.assertFalse(result.isError, result.content)
                            file = Path(result.content[0].text)
                            self.assertTrue(file.is_absolute())
                            self.assertEqual(file.parent, s.home / 'images')
                            self.assertEqual(file.read_bytes(), png)
                            paths.append(file)
                        self.assertNotEqual(*paths)
                        for prompt, reason in [('invalid', 'invalid PNG'), ('limited', 'rate or quota')]:
                            result = await call(prompt)
                            self.assertTrue(result.isError)
                            self.assertIn(reason, result.content[0].text)
                        self.assertEqual(set((s.home / 'images').iterdir()), set(paths))
                asyncio.run(exercise())
                self.assertEqual(len(calls), 4)
                for endpoint, auth, body in calls:
                    self.assertEqual((endpoint, auth), (path, 'Bearer project'))
                    self.assertEqual(body['n'], 1)
                    self.assertEqual(body['output_format'], 'png')
                s.stop()
                self.assertNotIn('route_images', config().get('mcp_servers', {}))
            finally:
                relay.close()

    def test_cancelling_an_mcp_call_closes_the_upstream(self):
        started, stopped = threading.Event(), threading.Event()
        calls = []

        def slow(h, raw):
            calls.append(h.path)
            h.send_response(200)
            h.send_header('Content-Type', 'application/json')
            h.end_headers()
            started.set()
            try:
                for _ in range(200):
                    h.wfile.write(b' ' * 2048)
                    h.wfile.flush()
                    time.sleep(.02)
            except OSError:
                stopped.set()

        with tempfile.TemporaryDirectory() as d, provider(slow) as origin, \
                patch.dict(os.environ, ROUTE_HOME=d, CODEX_HOME=d), patch('route.cli.PORT', free_port()) as port:
            s = Session()
            s.load()
            relay = Relay(port, 'fixture-key', origin=f'127.0.0.1:{origin}', admin=s.admin)
            self.addCleanup(relay.close)
            write(s.credential, relay.token)
            s.register()
            entry = config()['mcp_servers']['route_images']

            async def exercise():
                client = await asyncio.create_subprocess_exec(entry['command'], *entry['args'],
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
                async def send(method, params, request_id=None):
                    frame = {'jsonrpc': '2.0', 'method': method, 'params': params}
                    if request_id is not None:
                        frame['id'] = request_id
                    client.stdin.write(json.dumps(frame).encode() + b'\n')
                    await client.stdin.drain()
                try:
                    await send('initialize', {'protocolVersion': '2025-11-25', 'capabilities': {},
                                              'clientInfo': {'name': 'fixture', 'version': '1'}}, 1)
                    self.assertEqual(json.loads(await asyncio.wait_for(client.stdout.readline(), 10))['id'], 1)
                    await send('notifications/initialized', {})
                    await send('tools/call', {'name': 'generate_image', 'arguments': {'prompt': 'cancel'}}, 2)
                    self.assertTrue(await asyncio.to_thread(started.wait, 5))
                    await send('notifications/cancelled', {'requestId': 2})
                    self.assertTrue(await asyncio.to_thread(stopped.wait, 2))
                finally:
                    client.stdin.close()
                    await asyncio.wait_for(client.wait(), 5)
            asyncio.run(exercise())
            self.assertEqual(calls, ['/v1/images/generations'])
            self.assertFalse((s.home / 'images').exists())

    def test_journal_preserves_user_entry_and_edits(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, ROUTE_HOME=d, CODEX_HOME=d):
            s = Session()
            s.load()
            write(config_path(), '[mcp_servers.route_images]\ncommand = "user-command"\n')
            with self.assertRaisesRegex(RuntimeError, 'already exists'):
                s.register()
            self.assertNotIn('model_providers', config())
            self.assertEqual(config()['mcp_servers']['route_images']['command'], 'user-command')
            write(config_path(), '')
            s.register()
            s.register()
            doc = config()
            doc['mcp_servers']['route_images']['tool_timeout_sec'] = 600
            write(config_path(), doc.as_string())
            s.register()
            self.assertEqual(config()['mcp_servers']['route_images']['tool_timeout_sec'], 600)
            s.stop()
            self.assertEqual(config()['mcp_servers']['route_images']['tool_timeout_sec'], 600)

    def test_malformed_response(self):
        for body in (b'{}', b'{"data":null}', b'{"data":[{"b64_json":"!!!!"}]}', b'bad JSON'):
            with self.assertRaisesRegex(RuntimeError, 'invalid PNG'):
                png_bytes(body)
