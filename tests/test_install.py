import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import venv


class InstallTest(unittest.TestCase):
    def test_retry_seeds_missing_pip_before_bundling(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env = root / '.venv'
            venv.create(env, with_pip=False, symlinks=os.name != 'nt')
            tools = root / 'tools'
            tools.mkdir()
            installer = tools / 'install.py'
            shutil.copyfile(Path(__file__).resolve().parents[1] / 'tools/install.py', installer)
            # The bundle step runs in the target venv. Stop there to avoid any network or setup.
            (tools / 'bundle.py').write_text(
                'import pip, sys\nfrom pathlib import Path\n'
                'assert Path(pip.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())\n'
                'sys.exit(39)\n'
            )
            for needs_pip in (True, False):
                result = subprocess.run([sys.executable, str(installer)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 39, result.stderr)
                self.assertEqual('Setting up pip' in result.stdout, needs_pip)
