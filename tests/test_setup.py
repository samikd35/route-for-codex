import json
import http.client
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from route.check import check
from route.cli import Session, execute
from route.models import eligible, selection
from route.settings import config
from tests.fixture import free_port, provider


class SetupTest(unittest.TestCase):
    def test_model_subsets(self):
        catalog = json.loads(subprocess.check_output(['codex', 'debug', 'models', '--bundled']))
        sample = catalog['models'][0]
        catalog['models'] += [dict(sample, slug='gpt-7-test'), dict(sample, slug='gpt-8-test', shell_type='disabled')]
        ids = ['gpt-6.2-sol', 'gpt-6.2-astra', 'gpt-6-luna', 'gpt-6.1-terra', 'gpt-7-test', 'gpt-8-test', 'gpt-5.5', 'gpt-7-absent']
        result = eligible({'data': [{'id': m} for m in ids]}, catalog)
        self.assertEqual({m['slug'] for m in result['models']}, set(ids[:5]))
        self.assertEqual(selection(result, None, None), ('gpt-6.2-sol', 'medium'))
        self.assertEqual(selection(result, 'gpt-6.2-astra', 'high'), ('gpt-6.2-astra', 'high'))
        other = eligible({'data': [{'id': 'gpt-6-luna'}]}, catalog)
        self.assertIsNone(selection(other, None, None))
        self.assertFalse(eligible({'data': []}, catalog)['models'])

    def test_connection_challenge(self):
        calls = []

        def upstream(h, raw):
            req = json.loads(raw)
            calls.append(req)
            if len(calls) == 1:
                output = [{'type': 'function_call', 'name': 'route_setup', 'call_id': 'challenge', 'arguments': '{}'}]
            else:
                result = req['input'][-1]
                output = [{'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': result['output']}]}]
            h.start()
            h.event('response.completed', response={'output': output})

        with provider(upstream) as port:
            check(port, 'dummy', 'gpt-6.2-sol', 'medium')
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]['input'][-1]['call_id'], 'challenge')
        self.assertEqual(len(calls[1]['input'][-1]['output']), 48)

    def test_first_run_key_and_default_selection(self):
        for make_default in (False, True):
            with self.subTest(make_default=make_default), tempfile.TemporaryDirectory() as d, \
                    patch.dict(os.environ, ROUTE_HOME=d, CODEX_HOME=d), patch('route.cli.PORT', free_port()), \
                    patch('route.cli.discover') as discover, patch('route.cli.vault') as store, patch('route.cli.check') as probe:
                discover.return_value = {'models': [{'slug': 'gpt-6.2-sol',
                        'supported_reasoning_levels': [{'effort': 'medium'}], 'default_reasoning_level': 'medium'}]}
                session = Session()
                session.load()
                prompt = Mock()
                try:
                    execute(session, 'connect', prompt, initial_key='fixture-key', make_default=make_default)
                    self.assertEqual(config().get('model_provider') == 'route', make_default)
                    self.assertIn('route_images', config()['mcp_servers'])
                    self.assertEqual(store.return_value.set_password.call_args.args[-1], 'fixture-key')
                    probe.assert_called_once()
                    prompt.text.assert_not_called()
                    prompt.yes.assert_not_called()
                finally:
                    session.stop()

    def test_lifecycle(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as d, patch.dict(os.environ, ROUTE_HOME=d, CODEX_HOME=d), \
                patch('route.cli.PORT', free_port()), patch('route.cli.discover') as discover, \
                patch('route.cli.vault') as store, patch('route.cli.check') as probe:
            discover.return_value = {'models': [{'slug': 'gpt-6.2-sol', 'supported_reasoning_levels': [{'effort': 'medium'}], 'default_reasoning_level': 'medium'}]}
            store.return_value.get_password.return_value = 'saved'
            p = Mock()
            p.text.return_value = 'dummy-secret'
            p.yes.return_value = True
            s = Session()
            s.load()
            try:
                execute(s, 'connect', p)
                first = s.credential.read_text()
                self.assertEqual(config()['model_provider'], 'route')
                for name in ('state.json', 'config.toml', 'models.json'):
                    data = (Path(d) / name).read_text()
                    self.assertNotIn(first, data)
                    self.assertNotIn('dummy-secret', data)
                path = Path(d) / 'config.toml'
                path.write_text(path.read_text().replace('model = "gpt-6.2-sol"', 'model = "user-edit"'))
                execute(s, 'disconnect', p)
                self.assertNotIn('model_provider', config())
                self.assertEqual(config()['model'], 'user-edit')
                self.assertFalse(s.active())
                self.assertFalse(s.credential.exists())
                execute(s, 'login', p)
                self.assertFalse(s.active())
                execute(s, 'reconnect', p)
                self.assertNotEqual(s.credential.read_text(), first)
                from route.cli import PORT
                conn = http.client.HTTPConnection('127.0.0.1', PORT, timeout=2)
                try:
                    conn.request('POST', '/v1/responses', b'{}', {'Authorization': 'Bearer ' + first})
                    self.assertEqual(conn.getresponse().status, 401)
                finally:
                    conn.close()
                self.assertEqual(probe.call_count, 1)
                execute(s, 'forget', p)
                store.return_value.delete_password.assert_called_once()
                self.assertFalse(s.active())
            finally:
                s.stop()

    def test_rejected_replacement_and_session_only(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as d, patch.dict(os.environ, ROUTE_HOME=d, CODEX_HOME=d), \
                patch('route.cli.PORT', free_port()), patch('route.cli.discover') as discover, \
                patch('route.cli.vault') as store, patch('route.cli.check') as probe:
            discover.return_value = {'models': [{'slug': 'gpt-6.2-sol', 'supported_reasoning_levels': [{'effort': 'medium'}], 'default_reasoning_level': 'medium'}]}
            p = Mock()
            p.text.side_effect = ['initial', 'rejected', 'temporary', 'fresh']
            p.yes.return_value = True
            s = Session()
            s.load()
            try:
                execute(s, 'connect', p)
                discover.side_effect = RuntimeError('Rejected')
                with self.assertRaisesRegex(RuntimeError, 'Rejected'):
                    execute(s, 'replace', p)
                self.assertEqual(discover.call_args.args, ('rejected',))
                self.assertEqual(store.return_value.set_password.call_args.args[-1], 'rejected')
                self.assertEqual(probe.call_count, 1)
                self.assertEqual(json.loads((s.home / 'models.json').read_text()), {'models': []})
                discover.side_effect = None
                store.return_value.set_password.side_effect = RuntimeError('Store unavailable')
                execute(s, 'replace', p)
                execute(s, 'disconnect', p)
                execute(s, 'login', p)
                self.assertFalse(s.active())
                execute(s, 'reconnect', p)
                self.assertEqual(discover.call_args.args, ('fresh',))
                store.return_value.get_password.assert_not_called()
            finally:
                s.stop()
