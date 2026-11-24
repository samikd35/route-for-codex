"""Drive a stock Codex client using settings written by the production setup."""
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from route.cli import Session, execute
from route.relay import Relay
from route.settings import change, config, write
from tests.combined import ASTRA, Client, Fixture, SOL
from tests.fixture import free_port


class InstalledPickerTest(unittest.TestCase):
    def test_upgrade_and_switch_accounts(self):
        codex = shutil.which('codex')
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            project = root / 'project'
            project.mkdir()
            home = root / 'codex'
            home.mkdir()
            (home / 'auth.json').write_text(json.dumps({'OPENAI_API_KEY': 'fixture-native'}))
            (home / 'config.toml').write_text('model = "gpt-6.2-sol"\nmodel_reasoning_effort = "medium"\n'
                                              'cli_auth_credentials_store = "file"\n')
            catalog = json.loads(subprocess.check_output([codex, 'debug', 'models', '--bundled']))
            selected = [row for row in catalog['models'] if row['slug'] in (SOL, ASTRA)]
            for row in selected:
                row.pop('tool_mode', None)
                row['use_responses_lite'] = False
            nonce = secrets.token_hex(16)
            (project / 'value').write_text(nonce)
            (project / 'actual').write_text('wrong')
            fixture = Fixture(next(row for row in selected if row['slug'] == SOL), nonce)
            port = free_port()
            with patch.dict(os.environ, CODEX_HOME=str(home), ROUTE_HOME=str(root/'r')), \
                    fixture.upstream('native') as native, fixture.upstream('route') as api, \
                    patch('route.picker.NATIVE_URL', native), patch('route.cli.PORT', port), \
                    patch('route.picker.native_login', return_value=True), patch('route.cli.check'):
                s = Session()
                s.load()
                s.state.update(model=ASTRA, effort='medium', intended=True)
                write(s.home/'models.json', json.dumps({'models': selected}))
                relay = Relay(port, 'fixture-route', origin=api.split('/')[2], admin=s.admin)
                write(s.credential, relay.token)
                try:
                    s.register()
                    change(s.state, s.file, {'model_provider': 'route', 'model': ASTRA,
                                             'model_catalog_json': str(s.home/'models.json')})
                    prompt = Mock()
                    execute(s, 'onboard', prompt)
                    prompt.yes.assert_not_called()
                    self.assertNotIn('model_catalog_json', config())
                    self.assertEqual(config()['model'], SOL)
                    with Client(codex, home, project) as client:
                        rows = client.rpc('model/list', {})['data']
                        self.assertIn(('route-' + ASTRA, 'Route 6.2 Astra'), [(r['model'], r['displayName']) for r in rows])
                        thread = client.rpc('thread/start', {'cwd': str(project), 'approvalPolicy': 'never',
                                                            'sandbox': 'workspace-write'})['thread']['id']
                        for stage, model in [('read', SOL), ('edit', 'route-' + SOL), ('recall', SOL)]:
                            fixture.stage_is(stage)
                            try:
                                reply = client.turn(thread, model, stage)
                            except RuntimeError as exc:
                                raise AssertionError((fixture.errors, fixture.calls, stage)) from exc
                        self.assertIn(nonce, reply)
                        self.assertEqual((project/'actual').read_text(), nonce)
                    self.assertFalse(fixture.errors)
                finally:
                    s.stop()
                    relay.close()
                self.assertNotIn('model_provider', config())
                self.assertEqual(config()['model'], SOL)
