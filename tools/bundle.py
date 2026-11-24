"""Stage a verified Caddy distribution before installing Route."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-go', action='store_true',
                        help='Build the pinned Caddy version using Go, including on Apple Silicon')
    args = parser.parse_args()
    dest = Path(__file__).resolve().parents[1] / 'route/bin'
    dest.mkdir(exist_ok=True)
    subprocess.run([sys.executable, Path(__file__).with_name('build_dispatcher.py')], check=True)
    if args.from_go or sys.platform != 'darwin' or os.uname().machine != 'arm64':
        # Build on the target OS; Go verifies the module and dependencies via sumdb.
        module = 'github.com/caddyserver/caddy/v2'
        env = dict(os.environ, GOBIN=str(dest), GOFLAGS='', GOSUMDB='sum.golang.org',
                   GOPROXY='https://proxy.golang.org', GONOSUMDB='', GOPRIVATE='')
        subprocess.run(['go', 'install', module + '/cmd/caddy@v2.11.9'], env=env, check=True)
        import json
        info = json.loads(subprocess.check_output(['go', 'mod', 'download', '-json', module + '@v2.11.9'], env=env))
        shutil.copyfile(Path(info['Dir']) / 'LICENSE', dest / 'LICENSE')
        if sys.platform == 'win32':
            subprocess.run(['go', 'build', '-o', str(dest / 'control.exe'), str(Path(__file__).with_name('control.go'))], check=True)
        return
    subprocess.run(['brew', 'fetch', '--force-bottle', 'caddy'], check=True)
    archive = Path(subprocess.check_output(['brew', '--cache', 'caddy'], text=True).strip())
    with archive.open('rb') as f:
        if hashlib.file_digest(f, 'sha256').hexdigest() != '9522302c4179ab5aa1cb2246dc8cb0a3d4668188de10bfaddd282ef82dda67fd':
            sys.exit('Caddy archive differs from the pinned 2.11.9 bottle.')
    with tarfile.open(archive) as tar:
        for name in ('bin/caddy', 'LICENSE'):
            member = tar.extractfile('caddy/2.11.9/' + name)
            target = dest / Path(name).name
            target.write_bytes(member.read())
    (dest / 'caddy').chmod(0o755)


if __name__ == '__main__':
    main()
