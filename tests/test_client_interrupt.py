import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import unittest


class ClientInterruptTest(unittest.TestCase):
    def test_cli_cancellation_and_drop(self):
        for case in ('stop', 'drop'):
            with self.subTest(case=case), tempfile.TemporaryDirectory(dir='/tmp') as d:
                base = Path(d) / 'fixture'
                cmd = [sys.executable, '-m', 'tests.controls', case, base]
                if dispatcher := os.environ.get('ROUTE_PROOF_DISPATCHER'):
                    cmd.extend(['--combined-dispatcher', dispatcher])
                helper = subprocess.Popen(cmd,
                                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
                client = None
                try:
                    self.assertIn('Launch the test client', helper.stdout.readline())
                    env = {'HOME': d, 'CODEX_HOME': str(base / 'codex'), 'PATH': os.environ['PATH']}
                    client = subprocess.Popen(['codex', 'exec', '--ephemeral', '--json', '--skip-git-repo-check', 'Test the stream'],
                                              cwd=d, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    observed = []
                    arrived = threading.Event()
                    def watch():
                        for line in helper.stdout:
                            observed.append(line)
                            if 'Upstream request 1 started' in line:
                                arrived.set()
                    reader = threading.Thread(target=watch, daemon=True)
                    reader.start()
                    self.assertTrue(arrived.wait(15), 'CLI did not contact the fixture')
                    if case == 'stop':
                        client.send_signal(signal.SIGINT)
                    stdout, _ = client.communicate(timeout=20)
                    if case == 'drop':
                        self.assertIn('turn.failed', stdout, stdout)
                    helper.stdin.write('\n')
                    helper.stdin.flush()
                    helper.wait(5)
                    reader.join(2)
                    observation = ''.join(observed)
                    self.assertIn('Total upstream requests: 1', observation)
                    self.assertIn('disconnected before completion' if case == 'stop' else 'dropped after tool call', observation)
                finally:
                    if client and client.poll() is None:
                        client.kill()
                        client.communicate()
                    if helper.poll() is None:
                        helper.stdin.write('\n')
                        helper.stdin.flush()
                        helper.wait(5)
                    helper.stdout.close()
                    helper.stdin.close()
