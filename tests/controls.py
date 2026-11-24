"""Interactive Stop/drop fixture for disposable Codex profiles only."""
import argparse
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from unittest.mock import patch

from route.cli import Session
from route.relay import Relay
from route.settings import change, write
from tests.fixture import free_port, provider


def main():
    p = argparse.ArgumentParser()
    p.add_argument('case', choices=['stop', 'drop'])
    p.add_argument('fresh_directory', type=Path)
    p.add_argument('--combined-dispatcher', type=Path, help='Exercise the combined provider in Route-key-only mode')
    args = p.parse_args()
    root = args.fresh_directory.resolve()
    root.mkdir(mode=0o700, exist_ok=False)
    home = root / 'codex'
    home.mkdir(mode=0o700)
    requests = []

    def stream(h, raw):
        n = len(requests) + 1
        requests.append(n)
        print(f'Upstream request {n} started', flush=True)
        h.send_response(200)
        h.send_header('Content-Type', 'text/event-stream')
        if args.case == 'drop':
            h.send_header('Content-Length', '100000')
        h.end_headers()
        response = {'id': f'resp_{n}', 'object': 'response', 'output': []}
        try:
            h.event('response.created', response=response)
            if args.case == 'drop':
                item = {'type': 'function_call', 'id': f'fc_{n}', 'call_id': f'call_{n}',
                        'name': 'exec_command', 'arguments': json.dumps({'cmd': 'pwd'})}
                h.event('response.output_item.done', output_index=0, item=item)
                time.sleep(.5)
                h.connection.shutdown(socket.SHUT_RDWR)
                print(f'Upstream request {n} dropped after tool call', flush=True)
            else:
                for _ in range(300):
                    h.wfile.write(b': waiting for Stop\n\n')
                    h.wfile.flush()
                    time.sleep(.1)
                h.event('response.completed', response=dict(response, status='completed'))
                print(f'Upstream request {n} finished without Stop', flush=True)
        except (OSError, http.client.HTTPException):
            print(f'Upstream request {n} disconnected before completion', flush=True)

    with provider(stream) as port, patch.dict(os.environ, CODEX_HOME=str(home), ROUTE_HOME=str(root / 'route')):
        if args.combined_dispatcher:
            from contextlib import ExitStack
            from route.models import route_rows
            from route.relay import CADDY, combined_configuration
            from tests.combined import ALIAS, SOL, service, listening, write_profile
            catalog = json.loads(subprocess.check_output(['codex', 'debug', 'models', '--bundled']))
            rows = route_rows({'data': [{'id': SOL}]}, catalog)
            version = subprocess.check_output(['codex', '--version'], text=True).split()[-1].split('-')[0]
            sock, local_port = root / 'dispatch.sock', free_port()
            local_token = 'fixture-gateway'
            (root / 'token').write_text(local_token)
            base = f'http://127.0.0.1:{local_port}/v1'
            write_profile(home, base, root / 'token', default_model=ALIAS, native_sign_in=False)
            with ExitStack() as services:
                origin = f'http://127.0.0.1:{port}'
                services.enter_context(service([args.combined_dispatcher], dict(Socket=str(sock),
                    GatewayToken=local_token, RouteKey='fixture-project', NativeURL=origin, RouteURL=origin,
                    Catalogs={version: rows}), sock.exists))
                services.enter_context(service([CADDY, 'run', '--config', '-'], combined_configuration(local_port, sock),
                                              lambda: listening(local_port)))
                print(f'Launch the test client with CODEX_HOME={home}. Send one prompt. No live key needed.', flush=True)
                input('After the observation, press Enter here to stop the fixture. ')
            print(f'Total upstream requests: {len(requests)}')
            return
        s = Session()
        s.load()
        r = Relay(free_port(), 'dummy', admin=s.admin, origin=f'127.0.0.1:{port}')
        try:
            catalog = json.loads(subprocess.check_output(['codex', 'debug', 'models', '--bundled']))
            model = next(m for m in catalog['models'] if m['slug'] == 'gpt-6.2-sol')
            model.pop('tool_mode', None)
            model['use_responses_lite'] = False
            write(s.home / 'models.json', json.dumps({'models': [model]}))
            write(s.credential, r.token)
            with patch('route.cli.PORT', r.port):
                s.register()
            s.state.update(model=model['slug'], effort='medium')
            # Exercise existing conversations that still use the legacy provider.
            from route.settings import change
            change(s.state, s.file, {'model_provider': 'route', 'model': model['slug'],
                                     'model_catalog_json': str(s.home / 'models.json')})
            from route.settings import config, config_path
            import tomlkit
            doc = config()
            doc['model_providers']['route'].update(request_max_retries=0, stream_max_retries=0)
            write(config_path(), tomlkit.dumps(doc))
            print(f'Launch the test client with CODEX_HOME={home}. Send one prompt. No live key needed.', flush=True)
            input('After the observation, press Enter here to stop the fixture. ')
        finally:
            r.close()
            s.credential.unlink(missing_ok=True)
            change(s.state, s.file)
            print(f'Total upstream requests: {len(requests)}')


if __name__ == '__main__':
    main()
