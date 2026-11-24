import io
import os
from contextlib import redirect_stdout, redirect_stderr
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from route.cli import Session, onboard
from tests.fixture import free_port


class WizardTest(unittest.TestCase):
    def test_retry_then_resume_without_repeating_verification(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as root, patch.dict(os.environ, ROUTE_HOME=root, CODEX_HOME=root), \
                patch('route.cli.PORT', free_port()), patch('route.cli.vault'), patch('route.cli.check') as check, \
                patch('route.client_catalog.verify'), patch('route.picker.native_login', return_value=False), patch('route.picker.desktop_clients', return_value=()), \
                patch('route.picker.client_version', return_value='0.171.0'), patch('sys.stdin.isatty', return_value=True), \
                patch('route.cli.discover') as discover, redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()):
            prompt = Mock()
            prompt.text.side_effect = ['bad-fixture-key', 'good-fixture-key']
            prompt.yes.return_value = True
            discover.side_effect = [HTTPError('fixture', 401, '', {}, None), {'models': [
                {'slug': 'gpt-6.2-sol', 'supported_reasoning_levels': [{'effort': 'medium'}],
                 'default_reasoning_level': 'medium'}]}]
            session = Session()
            session.load()
            try:
                onboard(session, prompt)
                onboard(session, prompt)
                check.assert_called_once()
                self.assertEqual(prompt.text.call_count, 2)
                self.assertEqual(prompt.yes.call_count, 1)
                self.assertIn('Route 6.2 Sol', output.getvalue())
                self.assertIn('already verified', output.getvalue())
                self.assertNotIn('fixture-key', output.getvalue())
                self.assertNotIn('Ordinary models', output.getvalue())
            finally:
                session.stop()
