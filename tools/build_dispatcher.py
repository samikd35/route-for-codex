"""Build the local gateway, bootstrapping a verified Go compiler when needed."""
import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'go1.27.4'
DIGESTS = {
    'darwin-amd64': '2b799377704ef12db39bd254995d5c348c9cc8d86562ca817724390e56c38f43',
    'darwin-arm64': '91a44a2b8a716600ad94a4f143e156116620db8828086a6e3602291be9bd0bb4',
    'windows-amd64': '178ab98950ac69ab25069307dc6ade79f3816e414cce95b4da166a115cde1e7e',
    'windows-arm64': '9e7a72565792b8ab370b37ac9ac109799237abacb39ff2f541c438b963c0cc64',
    'linux-amd64': '7226736c2339719cda28fbf3a54d71aa63bcefe376e98cef00034268dab24840',
    'linux-arm64': '3392582988a273a87ab5043ee1b2c9c17a2c3c00580bf9326c47a2e0aaaeac92',
}


def build():
    windows = os.name == 'nt'
    ext = '.exe' if windows else ''
    with tempfile.TemporaryDirectory() as tmp:
        go = shutil.which('go')
        if not go:
            arch = platform.machine().lower()
            arch = {'x86_64': 'amd64', 'aarch64': 'arm64'}.get(arch, arch)
            target = platform.system().lower() + '-' + arch
            name = VERSION + '.' + target + ('.zip' if windows else '.tar.gz')
            archive = Path(tmp) / name
            subprocess.run(['curl.exe' if windows else 'curl', '-fsSL', '--retry', '2',
                            'https://go.dev/dl/' + name, '-o', archive], check=True)
            with archive.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != DIGESTS[target]:
                    raise RuntimeError('Go compiler checksum mismatch')
            with (zipfile.ZipFile(archive) if windows else tarfile.open(archive)) as files:
                files.extractall(tmp)
            go = str(Path(tmp) / 'go/bin' / ('go' + ext))
        subprocess.run([go, 'build', '-trimpath', '-o', ROOT / 'route/bin' / ('dispatcher' + ext), '.'],
                       cwd=ROOT / 'dispatcher', env=dict(os.environ, CGO_ENABLED='0'), check=True)


if __name__ == '__main__':
    build()
