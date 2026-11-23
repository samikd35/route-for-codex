"""Exercise a native installation with stock Codex on a disposable test account."""
import argparse
from contextlib import contextmanager, nullcontext
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import tomllib
from unittest.mock import patch

from route import relay
from tests.fixture import provider


PORT = 42839
MODEL = 'gpt-6.2-sol'
DUMMY_KEY = 'installer-fixture-upstream'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run(args, env, cwd, *, answers=None, expected=0, timeout=150):
    # Never report prompts, assistant output, auth helper output or supplied stdin.
    result = subprocess.run(args, input=answers, stdin=subprocess.DEVNULL if answers is None else None,
                            env=env, cwd=cwd, capture_output=True, text=True, encoding='utf-8',
                            errors='replace', timeout=timeout)
    if result.returncode != expected:
        known = next((msg for msg in ('Caddy could not start', 'Caddy did not become ready',
                     'Credential rejected', 'Access denied', 'Rate limit reached', 'No selected model',
                     'Route requires a private Windows directory', 'Invalid credential format',
                     'Could not locate the installed Codex CLI', 'Unlock the OS credential store')
                     if msg in result.stderr), '')
        raise RuntimeError(f'{Path(args[0]).name} {args[1]} exited {result.returncode}. {known}')
    return result.stdout.strip()


def check_dummy_key(exe, env, project):
    """Drive connect and the OS vault while keeping discovery entirely offline."""
    require(os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted' and os.environ.get('GITHUB_ACTIONS') == 'true',
            'The native credential check requires a disposable hosted account')
    attempted = []

    class OfflineProxy(BaseHTTPRequestHandler):
        def do_CONNECT(self):
            attempted.append(self.path)
            self.send_error(503, 'Offline installer fixture')

        def log_message(self, *args):
            pass

    with HTTPServer(('127.0.0.1', 0), OfflineProxy) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            proxy = f'http://127.0.0.1:{server.server_port}'
            offline = dict(env, https_proxy=proxy, HTTPS_PROXY=proxy, NO_PROXY='', no_proxy='')
            run([exe, 'connect'], offline, project, answers=DUMMY_KEY + '\nn\n', expected=1)
            require(attempted == ['api.openai.com:443'], 'Setup did not reach model discovery using the dummy key')
            config = tomllib.loads((Path(env['CODEX_HOME']) / 'config.toml').read_text())
            require('model_provider' not in config, 'Failed discovery changed the default provider')
            require('saved on this device' in run([exe, 'disconnect'], env, project), 'Native key storage failed')
            require(run([exe, 'reconnect'], env, project) == 'Reconnected.', 'Native key recovery failed')
        finally:
            server.shutdown()
            worker.join()
            require(run([exe, 'forget'], env, project) == 'Disconnected.', 'Dummy credential cleanup failed')
    print('Public connect accepted a dummy key, preserved defaults on discovery failure, and recovered the key from the OS store.', flush=True)


@contextmanager
def fixture(exe, codex, env, project, marker):
    home = Path(env['ROUTE_HOME'])
    calls = []
    errors = []

    def respond(handler, raw):
        try:
            request = json.loads(raw)
            require(handler.path == '/v1/responses' and request['model'] == MODEL, 'Wrong destination or model')
            require(handler.headers['Authorization'] == 'Bearer ' + DUMMY_KEY, 'Wrong upstream credential')
            choice = request.get('tool_choice')
            if len(calls) == 0:
                require(isinstance(choice, dict) and choice['name'] == 'route_setup', 'Expected setup challenge')
                item = dict(type='function_call', id='fc_setup', call_id='call_setup',
                            name='route_setup', arguments='{}')
            else:
                if len(calls) == 1:
                    output, = [i for i in request['input'] if i.get('type') == 'function_call_output']
                    require(output['call_id'] == 'call_setup' and choice == 'none', 'Wrong challenge continuation')
                    reply = output['output']
                else:
                    require(len(calls) == 2 and marker in json.dumps(request['input']), 'Missing Codex prompt')
                    reply = marker
                item = dict(type='message', id='msg_' + str(len(calls)), role='assistant',
                            content=[dict(type='output_text', text=reply)])
            calls.append(len(calls))
            response = dict(id='resp_' + str(len(calls)), object='response', output=[])
            handler.start()
            handler.event('response.created', response=response)
            handler.event('response.output_item.done', output_index=0, item=item)
            handler.event('response.completed', response=dict(response, status='completed', output=[item]))
        except Exception as exc:
            errors.append(type(exc).__name__ + ': ' + str(exc))
            handler.send_error(400)

    bundled = json.loads(run([codex, 'debug', 'models', '--bundled'], env, project))
    model = next(m for m in bundled['models'] if m['slug'] == MODEL)
    model['use_responses_lite'] = False  # This fixture speaks streaming Responses.
    (home / 'models.json').write_text(json.dumps({'models': [model]}))
    (home / 'state.json').write_text(json.dumps({'model': MODEL, 'effort': 'medium', 'image_endpoint': True}))
    caddy = (exe.parent / '_internal/route/bin/caddy.exe' if os.name == 'nt'
             else exe.parent.parent / 'Frameworks/route/bin/caddy')
    require(caddy.is_file(), 'Installed Caddy missing')
    with provider(respond) as port, patch.object(relay, 'CADDY', caddy):
        service = relay.Relay(PORT, DUMMY_KEY, origin=f'127.0.0.1:{port}', admin=home / 'admin.sock')
        try:
            (home / 'relay.token').write_text(service.token)
            yield
            require(not errors and len(calls) == 3, f'Failed fixture exchange ({len(calls)} requests): {errors}')
        finally:
            service.close()


def exercise(exe, codex, root, live):
    key = os.environ.pop('ROUTE_INSTALL_TEST_KEY', None)
    if live:
        require(os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted' and os.environ.get('GITHUB_ACTIONS') == 'true',
                'Live mode requires a disposable GitHub-hosted account')
        require(key, 'Set the ROUTE_INSTALL_TEST_KEY Actions secret for the live qualification run')
    env = dict(os.environ)
    for name in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'CODEX_ACCESS_TOKEN', 'OPENAI_BASE_URL'):
        env.pop(name, None)
    profile, project = root / 'codex', root / 'workspace'
    profile.mkdir()
    project.mkdir()
    env.update(ROUTE_HOME=str(root / 'r'), CODEX_HOME=str(profile))
    config = profile / 'config.toml'
    config.write_text('cli_auth_credentials_store = "file"\n')
    with socket.socket() as sock:
        require(sock.connect_ex(('127.0.0.1', PORT)) != 0, 'Route port already in use')
    require(run([exe, 'status'], env, project) == 'Disconnected.', 'Expected fresh Route profile')
    # Codex emits login status on stderr. Verify the reason as well as the exit code.
    login = subprocess.run([codex, 'login', 'status'], env=env, cwd=project, capture_output=True,
                           text=True, timeout=30)
    require(login.returncode == 1 and 'not logged in' in (login.stdout + login.stderr).lower(),
            'Expected a signed-out Codex profile')
    marker = 'route-' + secrets.token_hex(12)
    mode = 'live' if live else 'fixture'
    print(f'{platform.platform()} {platform.machine()} | {run([codex, "--version"], env, project)} | {mode}', flush=True)
    if not live:
        check_dummy_key(exe, env, project)
    with nullcontext() if live else fixture(exe, codex, env, project, marker):
        try:
            if live:
                result = run([exe, 'connect'], env, project, answers=key + '\ny\n', timeout=240)
            else:
                result = run([exe, 'test'], env, project, answers='y\n')
            require('Connection test passed.' in result, 'Two-request setup challenge failed')
            doc = tomllib.loads(config.read_text())
            require(doc.get('model_provider') == 'route' and doc['model'] == MODEL,
                    'Route was not selected as the default')
            require(Path(doc['model_providers']['route']['auth']['command']).samefile(exe),
                    'Codex credential helper does not point to the installed app')
            if live:
                require('saved on this device' in run([exe, 'disconnect'], env, project), 'Native key storage failed')
                require(run([exe, 'reconnect'], env, project) == 'Reconnected.', 'Native credential recovery failed')
            answer = project / 'answer.txt'
            run([codex, 'exec', '--ephemeral', '--skip-git-repo-check', '--sandbox', 'read-only',
                 '--output-last-message', str(answer), 'Reply with exactly this text: ' + marker], env, project)
            require(answer.read_text(encoding='utf-8').strip() == marker, 'Codex returned the wrong answer')
        finally:
            require(run([exe, 'forget'], env, project) == 'Disconnected.', 'Forget failed')
        restored = tomllib.loads(config.read_text())
        require('model_provider' not in restored and 'route' not in restored.get('model_providers', {})
                and restored.get('cli_auth_credentials_store') == 'file', 'Codex settings were not restored')
        require(not (root / 'r/relay.token').exists(), 'Local token survived Forget')
    print(f'Passed ({mode}): installed helper, two-request challenge, Codex answer and cleanup.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe', type=Path, help='Installed Route executable')
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    exe = args.exe.resolve(strict=True)
    codex = shutil.which('codex')
    require(codex, 'Install Codex CLI first')
    # Darwin limits the length of a Unix socket path.
    with tempfile.TemporaryDirectory(prefix='ri-', dir='/tmp' if sys.platform == 'darwin' else None) as temp:
        exercise(exe, codex, Path(temp), args.live)


if __name__ == '__main__':
    main()
