"""Discover Codex's active service and read its user-visible model picker."""
import asyncio
import json
import os
from pathlib import Path
import subprocess

from .models import codex_path
from .relay import admin_socket


def daemon_info():
    home = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))
    socket_path = home / 'app-server-control/app-server-control.sock'
    if not socket_path.exists() and os.name != 'nt':
        return None
    result = subprocess.run([codex_path(), 'app-server', 'daemon', 'version'], text=True,
                            capture_output=True, timeout=15)
    if result.returncode:
        if socket_path.exists():
            raise RuntimeError('Could not inspect the active Codex service')
        return None
    info = json.loads(result.stdout)
    return info if info.get('status') == 'running' else None


async def read_stdio(binary):
    process = await asyncio.create_subprocess_exec(str(binary), 'app-server', '--listen', 'stdio://',
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, limit=8 << 20)
    async def request(frame):
        process.stdin.write(json.dumps(frame).encode() + b'\n')
        await process.stdin.drain()
        while line := await process.stdout.readline():
            reply = json.loads(line)
            if reply.get('id') == frame['id']:
                return reply
        raise RuntimeError('Codex closed the model picker connection')

    try:
        return await asyncio.wait_for(model_list(request), 45)
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()


async def model_list(request, reload_provider=None):
    async def call(method, params, seq):
        reply = await request(dict(id=seq, method=method, params=params))
        if 'result' not in reply:
            raise RuntimeError(f'Codex rejected {method}')
        return reply['result']
    await call('initialize', {'clientInfo': {'name': 'route_picker_check', 'version': '1'},
                              'capabilities': {'experimentalApi': True}}, 1)
    if reload_provider:
        settings = await call('config/read', {}, 2)
        if settings['config'].get('model_provider', 'openai') != reload_provider:
            raise RuntimeError('Codex is using a different provider. Check your active profile.')
        updated = await call('modelProvider/default/set', {'providerId': reload_provider}, 3)
        if updated.get('status') != 'ok':
            raise RuntimeError('Codex could not reload the registered Route provider')
    rows = {}
    cursor = None
    for page in range(64):
        result = await call('model/list', {'cursor': cursor, 'limit': 100}, page + 4)
        rows.update((row['model'], row['displayName']) for row in result['data'])
        cursor = result.get('nextCursor')
        if not cursor:
            return rows
    raise RuntimeError('Codex model list exceeded its page limit')


def read_service(path, reload_provider=None):
    from websockets.sync.client import unix_connect
    with admin_socket(path) as sock, unix_connect(sock=sock, uri='ws://localhost/rpc',
                                                  open_timeout=8, close_timeout=2) as ws:
        async def request(frame):
            ws.send(json.dumps(frame))
            while True:
                reply = json.loads(ws.recv(timeout=30))
                if reply.get('id') == frame['id']:
                    return reply
        return asyncio.run(model_list(request, reload_provider))


def verify(clients, catalogs, native, service, provider):
    from websockets.exceptions import WebSocketException

    for label, binary, version in clients:
        expected = {row['slug']: row['display_name'] for row in catalogs[version]
                    if row.get('visibility', 'list') == 'list'}

        def missing(rows):
            if not expected or not expected.items() <= rows.items():
                return 'the eligible Route models'
            if native and not any(not slug.startswith('route-') for slug in rows):
                return 'the native Codex models'
            return None

        try:
            if label == 'Codex service':
                visible = read_service(service['socketPath'])
                if missing(visible):
                    visible = read_service(service['socketPath'], reload_provider=provider)
            else:
                visible = asyncio.run(read_stdio(binary))
        except (OSError, WebSocketException, subprocess.SubprocessError) as exc:
            raise RuntimeError(f'Could not read the model picker in {label} {version}. '
                               'Run route-for-codex onboard to retry.') from exc
        problem = missing(visible)
        if problem:
            raise RuntimeError(f'{label} {version} has not loaded {problem}. '
                               'Run route-for-codex onboard to retry.')
