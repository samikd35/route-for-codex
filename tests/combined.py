"""Disposable combined-provider proof. Start with python -m tests.combined --help."""
import argparse
from contextlib import ExitStack, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

from route.models import route_rows
from route.relay import CADDY, combined_configuration
from tests.fixture import free_port


SOL = 'gpt-6.2-sol'
ASTRA = 'gpt-6.2-astra'
ALIAS = 'route-' + SOL
PROVIDER = 'route-combined'


@contextmanager
def service(command, config, ready):
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL) as process:
        try:
            process.stdin.write(json.dumps(config).encode())
            process.stdin.close()
            for _ in range(200):
                if process.poll() is not None:
                    raise RuntimeError('Local proof service failed to start')
                if ready():
                    break
                time.sleep(.02)
            else:
                raise RuntimeError('Local proof service timed out')
            yield
        finally:
            process.terminate()
            try:
                process.wait(4)
            except subprocess.TimeoutExpired:
                process.kill()


def listening(port):
    with socket.socket() as sock:
        return sock.connect_ex(('127.0.0.1', port)) == 0


class Client:
    def __init__(self, binary, home, workspace, *, options=(), env=None):
        self.env = env if env is not None else {'HOME': str(home.parent), 'CODEX_HOME': str(home), 'PATH': os.environ['PATH']}
        self.process = subprocess.Popen([binary, 'app-server', '--listen', 'stdio://', *options], env=self.env,
                                        cwd=workspace, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True)
        self.events = queue.Queue()
        self.seq = 0
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()

    def read(self):
        for line in self.process.stdout:
            self.events.put(json.loads(line))
        self.events.put(None)

    def send(self, frame):
        self.process.stdin.write(json.dumps(frame) + '\n')
        self.process.stdin.flush()

    def next(self, timeout=90):
        result = self.events.get(timeout=timeout)
        if result is None:
            raise RuntimeError('Codex app-server exited')
        return result

    def rpc(self, method, params):
        self.seq += 1
        self.send({'id': self.seq, 'method': method, 'params': params})
        while True:
            frame = self.next()
            if frame.get('id') == self.seq and 'method' not in frame:
                if 'error' in frame:
                    raise RuntimeError(f'{method}: {frame["error"]["message"]}')
                return frame['result']

    def __enter__(self):
        try:
            self.rpc('initialize', {'clientInfo': {'name': 'route_proof', 'version': '1'},
                                    'capabilities': {'experimentalApi': True}})
            self.send({'method': 'initialized'})
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        self.process.stdin.close()
        try:
            self.process.wait(3)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(5)
        self.reader.join(2)
        self.process.stdout.close()

    def complete(self, thread):
        messages = []
        self.compacted = False
        while True:
            frame = self.next(120)
            params = frame.get('params', {})
            if params.get('threadId') != thread:
                continue
            if frame.get('method') == 'item/completed':
                item = params['item']
                if item['type'] == 'contextCompaction':
                    self.compacted = True
                if item['type'] == 'agentMessage':
                    messages.append(item['text'])
            if frame.get('method') == 'turn/completed':
                turn = params['turn']
                if turn['status'] != 'completed':
                    raise RuntimeError(f'Turn {turn["status"]}: {turn.get("error")}')
                return '\n'.join(messages)

    def turn(self, thread, model, prompt):
        self.rpc('turn/start', {'threadId': thread, 'model': model, 'effort': 'medium',
                                'input': [{'type': 'text', 'text': prompt}]})
        return self.complete(thread)


class Fixture:
    def __init__(self, seed, nonce):
        self.seed = seed
        self.nonce = nonce
        self.stage = ''
        self.calls = []
        self.catalogs = []
        self.errors = []
        self.tools = []
        self.replies = 0

    def stage_is(self, name):
        self.stage = name
        self.replies = 0

    def reply(self, account, payload):
        self.calls.append((account, payload['model'], self.stage))
        assert payload['model'] == (ASTRA if self.stage == 'astra-check' else SOL)
        assert account == ('route' if self.stage in ('edit', 'route-recall', 'astra-check') else 'native')
        items = payload['input']
        outputs = {x['call_id']: str(x['output']) for x in items if x.get('type') == 'function_call_output'}
        call_id = 'call_' + self.stage
        self.replies += 1
        if self.stage in ('read', 'edit') and self.replies == 1:
            cmd = 'cat value'
            if self.stage == 'edit':
                match = re.search(r'\b[0-9a-f]{32}\b', outputs['call_read'])
                assert match and match[0] == self.nonce
                cmd = f"printf '%s' {match[0]} > actual && cmp actual value && printf verified"
            assert 'exec_command' in [tool.get('name') for tool in payload['tools']]
            self.tools.append(call_id)
            return dict(type='function_call', name='exec_command', id='fc_' + self.stage,
                        call_id=call_id, arguments=json.dumps({'cmd': cmd}))
        if self.stage == 'read':
            assert self.nonce in outputs[call_id]
            answer = 'Read the value.'  # Later turns must retrieve it from the original tool result.
        elif self.stage == 'edit':
            assert 'verified' in outputs[call_id]
            answer = 'File verified.'
        elif self.stage == 'astra-check':
            answer = 'Astra received.'
        elif self.stage in ('recall', 'compact'):
            assert self.nonce in outputs['call_read'] and 'verified' in outputs['call_edit']
            answer = 'Verified value ' + self.nonce
        else:
            assert self.stage == 'route-recall'
            assert 'call_read' not in outputs, 'Codex replayed the pre-compaction tool history'
            assert any(self.nonce in str(item.get('content')) and 'Verified' in str(item.get('content'))
                       for item in items)
            answer = 'Verified value ' + self.nonce
        return dict(type='message', id='msg_' + self.stage, role='assistant',
                    content=[{'type': 'output_text', 'text': answer}])

    @contextmanager
    def upstream(self, account):
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def credential(self):
                assert self.headers.get('Authorization') == 'Bearer fixture-' + account
                assert self.headers.get('X-Route-Token') is None
                if account == 'route':
                    assert self.headers.get('ChatGPT-Account-ID') is None

            def do_GET(self):
                try:
                    self.credential()
                    assert account == 'native' and self.path.startswith('/v1/models?client_version=')
                    fixture.catalogs.append(self.path)
                    data = json.dumps({'models': [fixture.seed]}).encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(data)
                except Exception as exc:
                    fixture.errors.append(repr(exc))
                    self.send_error(400)

            def do_POST(self):
                try:
                    self.credential()
                    assert self.path == '/v1/responses', self.path
                    payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                    item = fixture.reply(account, payload)
                    response = dict(id=f'resp_{len(fixture.calls)}', object='response', output=[])
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/event-stream')
                    self.end_headers()
                    for kind, fields in [('response.created', dict(response=response)),
                                         ('response.output_item.done', dict(output_index=0, item=item)),
                                         ('response.completed', dict(response=dict(response, status='completed', output=[item])))]:
                        body = json.dumps(dict(type=kind, **fields))
                        self.wfile.write(f'event: {kind}\ndata: {body}\n\n'.encode())
                        self.wfile.flush()
                except Exception as exc:
                    fixture.errors.append(f'{account}/{fixture.stage}: {exc!r}')
                    self.send_error(400)

        with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                yield f'http://127.0.0.1:{server.server_port}/v1'
            finally:
                server.shutdown()
                worker.join()


def write_profile(home, base, token_path, *, default_model=SOL, native_sign_in=True):
    # Avoid inherited shell and provider settings. This helper reads only the disposable local token.
    helper = [str(sys.executable), '-I', '-c',
              'import pathlib,sys;print(pathlib.Path(sys.argv[1]).read_text())', str(token_path)]
    (home / 'config.toml').write_text(f'''model_provider = "{PROVIDER}"
model = "{default_model}"
cli_auth_credentials_store = "file"
approval_policy = "never"
sandbox_mode = "workspace-write"
[model_providers.{PROVIDER}]
name = "Route combined"
wire_api = "responses"
base_url = "{base}"
model_catalog_url = "{base}/models"
requires_openai_auth = {str(native_sign_in).lower()}
supports_websockets = false
request_max_retries = 0
stream_max_retries = 0
[model_providers.{PROVIDER}.gateway_oauth]
delivery = {{kind="header", name="X-Route-Token"}}
[model_providers.{PROVIDER}.gateway_oauth.credential_export]
command = {json.dumps(helper[0])}
args = {json.dumps(helper[1:])}
''')


def desktop_check(home, target, project, fixture):
    # The normal Desktop launcher reads its own user's config. Install the fixture
    # only in a completely new profile, never over an existing login or settings.
    target.mkdir(mode=0o700, parents=True, exist_ok=False)
    managed = {}
    try:
        for name in ('config.toml', 'auth.json'):
            path = target / name
            payload = (home / name).read_bytes()
            with path.open('xb') as f:
                f.write(payload)
            path.chmod(0o600)
            managed[path] = payload
        print(f'Launch stock Desktop normally from this test OS account. Open workspace {project}.', flush=True)
        print('Start one new chat and capture its ID and model picker. Select the ordinary Sol row.', flush=True)
        input('Press Enter when the chat is ready. ')
        for stage, action in [('read', 'Send "Read value" on ordinary Sol'),
                              ('edit', 'Select Route 6.2 Sol and send "Repair and test actual"'),
                              ('recall', 'Select ordinary Sol and ask it to recall the verified value'),
                              ('compact', 'Run the client compact command and wait for completion'),
                              ('route-recall', 'Select Route 6.2 Sol and ask for the verified value'),
                              ('route-recall', 'Close and reopen Desktop. Resume that chat on Route Sol and ask for the value')]:
            fixture.stage_is(stage)
            count = len(fixture.calls)
            input(action + '. Press Enter here after the reply. ')
            if len(fixture.calls) <= count or fixture.errors:
                raise RuntimeError(f'Desktop failed stage {stage}: {fixture.errors}')
        if (project / 'actual').read_text() != fixture.nonce or fixture.tools != ['call_read', 'call_edit']:
            raise RuntimeError('Desktop edit or tool-call count failed')
        print('Desktop requests:', fixture.calls)
        print('Capture the unchanged chat ID, visible recalled value, and picker before closing Desktop.')
        input('Close the test app and press Enter to remove fixture credentials. ')
    finally:
        for path, payload in managed.items():
            if path.is_file() and path.read_bytes() == payload:
                path.unlink()


def proof(binary, dispatcher, root, interactive=False, desktop_home=None):
    root = root.resolve()
    home, project = root / 'codex', root / 'workspace'
    home.mkdir()
    project.mkdir()
    nonce = secrets.token_hex(16)
    (project / 'value').write_text(nonce)
    (project / 'actual').write_text('wrong')
    (home / 'auth.json').write_text(json.dumps({'OPENAI_API_KEY': 'fixture-native'}))
    probe_env = {'HOME': str(root), 'CODEX_HOME': str(home), 'PATH': os.environ['PATH']}
    version = subprocess.check_output([binary, '--version'], text=True, env=probe_env).strip().split()[-1]
    catalog = json.loads(subprocess.check_output([binary, 'debug', 'models', '--bundled'], env=probe_env))
    selected = [dict(row) for row in catalog['models'] if row['slug'] in (SOL, ASTRA)]
    for row in selected:
        row.pop('tool_mode', None)
        row['use_responses_lite'] = False
    rows = route_rows({'data': [{'id': slug} for slug in (SOL, ASTRA)]}, {'models': selected})
    seed = next(row for row in selected if row['slug'] == SOL)
    fixture = Fixture(seed, nonce)
    port = free_port()
    base = f'http://127.0.0.1:{port}/v1'
    token = secrets.token_urlsafe()
    token_path = root / 'token'
    token_path.write_text(token)
    write_profile(home, base, token_path)
    sock = root / 'dispatch.sock'
    with ExitStack() as stack:
        native = stack.enter_context(fixture.upstream('native'))
        route = stack.enter_context(fixture.upstream('route'))
        cfg = dict(Socket=str(sock), GatewayToken=token, RouteKey='fixture-route', NativeURL=native,
                   RouteURL=route, Catalogs={version.split('-')[0]: rows})
        stack.enter_context(service([dispatcher], cfg, sock.exists))
        stack.enter_context(service([CADDY, 'run', '--config', '-'], combined_configuration(port, sock),
                                    lambda: listening(port)))
        invalid = urllib.request.Request(base + '/responses', data=json.dumps({'model': ALIAS}).encode(),
                                         headers={'X-Route-Token': 'Bearer invalid'})
        try:
            urllib.request.urlopen(invalid)
            raise AssertionError('The gateway accepted an invalid token')
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        assert not fixture.calls and not fixture.catalogs
        if desktop_home is not None:
            desktop_check(home, desktop_home, project, fixture)
            return
        if interactive:
            print(f'Disposable CLI profile: {home}', flush=True)
            subprocess.run([binary, '--no-alt-screen'], env={'CODEX_HOME': str(home), 'HOME': str(root),
                           'PATH': os.environ['PATH'], 'TERM': os.environ.get('TERM', 'xterm-256color')}, cwd=project)
            return
        with Client(binary, home, project) as client:
            models = [(m['model'], m['displayName']) for m in client.rpc('model/list', {})['data']]
            print('Picker model list:', models, flush=True)
            assert models == [(SOL, seed['display_name']), (ALIAS, 'Route 6.2 Sol'),
                              ('route-' + ASTRA, 'Route 6.2 Astra')], (models, fixture.errors)
            info = client.rpc('thread/start', {'cwd': str(project), 'approvalPolicy': 'never', 'sandbox': 'workspace-write'})
            assert info['modelProvider'] == PROVIDER
            thread = info['thread']['id']
            try:
                for stage, model, prompt in [('read', SOL, 'Read value.'), ('edit', ALIAS, 'Repair and test actual.'),
                                             ('recall', SOL, 'Recall the verified value.')]:
                    fixture.stage_is(stage)
                    answer = client.turn(thread, model, prompt)
                    if stage == 'recall':
                        assert nonce in answer
                assert (project / 'actual').read_text() == nonce
                fixture.stage_is('compact')
                client.rpc('thread/compact/start', {'threadId': thread})
                client.complete(thread)
                assert client.compacted, 'Missing completed context compaction'
                fixture.stage_is('route-recall')
                assert nonce in client.turn(thread, ALIAS, 'Recall the result after compaction.')
            finally:
                if fixture.errors:
                    raise AssertionError(fixture.errors)
        with Client(binary, home, project) as client:
            info = client.rpc('thread/resume', {'threadId': thread})
            assert info['thread']['id'] == thread and info['modelProvider'] == PROVIDER
            fixture.stage_is('route-recall')
            assert nonce in client.turn(thread, ALIAS, 'Recall the result after restarting Codex.')
        for preferred in (ALIAS, SOL):
            write_profile(home, base, token_path, default_model=preferred)
            with Client(binary, home, project) as client:
                visible = [(m['model'], m['displayName']) for m in client.rpc('model/list', {})['data']]
                assert visible == models
                chat = client.rpc('thread/start', {'cwd': str(project), 'ephemeral': True})
                assert chat['modelProvider'] == PROVIDER and chat['model'] == preferred
                if preferred == ALIAS:
                    fixture.stage_is('astra-check')
                    assert 'Astra received' in client.turn(chat['thread']['id'], 'route-' + ASTRA, 'Confirm receipt.')
        assert not fixture.errors and fixture.tools == ['call_read', 'call_edit']
        print(json.dumps(dict(client=version, thread=thread, calls=fixture.calls,
                              tool_calls=fixture.tools, verified_edit=True, compacted=True, resumed=True, default_rows=[ALIAS, SOL])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dispatcher', type=Path, required=True)
    parser.add_argument('--codex', default=shutil.which('codex'))
    parser.add_argument('--interactive', action='store_true', help='Open the real CLI for a picker screenshot')
    parser.add_argument('--desktop-home', type=Path, help='New Codex home of a disposable OS user for normal Desktop launch')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='route-mix-', dir='/tmp') as work:
        proof(args.codex, args.dispatcher.resolve(), Path(work), args.interactive, args.desktop_home)
