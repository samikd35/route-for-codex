import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from route.cli import Session
from route.relay import Relay
from route.settings import write
from tests.fixture import free_port, provider


class CodexTest(unittest.TestCase):
    def test_coding_task(self):
        for _ in range(2):
            self.fixture_run()

    def fixture_run(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            home, project = root / 'codex', root / 'project'
            home.mkdir()
            project.mkdir()
            nonce = secrets.token_hex(16)
            (project / 'value').write_text(nonce)
            (project / 'actual').write_text('wrong')
            test = ['cmp', 'actual', 'value']
            self.assertNotEqual(subprocess.run(test, cwd=project, capture_output=True).returncode, 0)
            calls = []
            errors = []
            commands = ['cat value', 'cp value actual', 'cmp actual value && printf verified']

            def upstream(h, raw):
                try:
                    self.assertEqual(h.headers['Authorization'], 'Bearer dummy-upstream')
                    req = json.loads(raw)
                    self.assertEqual(req['model'], 'gpt-6.2-sol')
                    idx = len(calls)
                    calls.append(idx)
                    if 1 <= idx <= 3:
                        outputs = [i for i in req['input'] if i.get('call_id') == f'call_{idx-1}' and i['type'] == 'function_call_output']
                        self.assertTrue(outputs, 'Missing matching tool result')
                        if idx in (1, 3):
                            self.assertIn(nonce if idx == 1 else 'verified', str(outputs[-1]['output']))
                    if idx < 3:
                        names = [t.get('name') for t in req['tools']]
                        self.assertIn('exec_command', names, str(names))
                        item = {'type': 'function_call', 'id': f'fc_{idx}', 'call_id': f'call_{idx}',
                                'name': 'exec_command', 'arguments': json.dumps({'cmd': commands[idx]})}
                    else:
                        text = 'Fixture repaired.'
                        if idx == 4:
                            # Retrieve the value from the client's retained tool result, not disk.
                            retained = [i['output'] for i in req['input'] if i.get('call_id') == 'call_0' and i['type'] == 'function_call_output']
                            text = re.search(r'[0-9a-f]{32}', str(retained)).group()
                        item = {'type': 'message', 'id': f'msg_{idx}', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': text}]}
                    h.start()
                    response = {'id': f'resp_{idx}', 'object': 'response', 'output': []}
                    h.event('response.created', response=response)
                    h.event('response.output_item.done', output_index=0, item=item)
                    h.event('response.completed', response=dict(response, status='completed', output=[item]))
                except Exception as exc:
                    errors.append(str(exc))
                    h.send_error(400)

            with provider(upstream) as port:
                with patch.dict(os.environ, ROUTE_HOME=str(root / 'route'), HOME=str(root / 'caddy-home'), CODEX_HOME=str(home)):
                    session = Session()
                    session.load()
                    r = Relay(free_port(), 'dummy-upstream', admin=session.admin, origin=f'127.0.0.1:{port}')
                try:
                    # Use an isolated fixture catalog with conventional shell-tool exposure.
                    catalog = json.loads(subprocess.check_output(['codex', 'debug', 'models', '--bundled']))
                    model = next(m for m in catalog['models'] if m['slug'] == 'gpt-6.2-sol')
                    model.pop('tool_mode', None)
                    model['use_responses_lite'] = False
                    (home / 'catalog.json').write_text(json.dumps({'models': [model]}))
                    (home / 'config.toml').write_text(f'''model = "gpt-6.2-sol"
model_catalog_json = {json.dumps(str(home / 'catalog.json'))}
model_provider = "route"
approval_policy = "never"
sandbox_mode = "workspace-write"
''')
                    with patch.dict(os.environ, CODEX_HOME=str(home)), patch('route.cli.PORT', r.port):
                        write(session.credential, r.token)
                        session.register()
                    env = {'PATH': os.environ['PATH'], 'HOME': str(root), 'CODEX_HOME': str(home)}
                    def run(*args):
                        cmd = ['codex', 'exec', *args, '--json', '--skip-git-repo-check']
                        p = subprocess.run(cmd, cwd=project, env=env, text=True, capture_output=True, timeout=90)
                        self.assertFalse(errors, errors)
                        self.assertEqual(p.returncode, 0, p.stderr[-2000:] + p.stdout[-2000:])
                        return p.stdout
                    first = run('Read value, repair actual and verify it.')
                    thread = next(x['thread_id'] for x in map(json.loads, first.splitlines()) if x['type'] == 'thread.started')
                    self.assertEqual((project / 'actual').read_text(), nonce)
                    subprocess.run(test, cwd=project, check=True)
                    self.assertIn(nonce, run('resume', thread, 'What value did you read earlier?'))
                    self.assertEqual(len(calls), 5)
                    configs = [home / 'config.toml', session.file, *(root / 'caddy-home').rglob('*')]
                    for path in configs:
                        if path.is_file():
                            contents = path.read_bytes()
                            for private in [nonce, r.token, 'dummy-upstream', 'Read value, repair actual']:
                                self.assertNotIn(private.encode(), contents, path.name)
                finally:
                    r.close()
