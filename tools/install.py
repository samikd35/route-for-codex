"""Install Route into this checkout's virtual environment."""
import argparse
from pathlib import Path
import shlex
import subprocess
import sys
import venv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connect', action='store_true', help='Start terminal setup after installation')
    parser.add_argument('--from-go', action='store_true', help='Use Go to build the relay on Apple Silicon')
    args = parser.parse_args()
    windows = sys.platform == 'win32'
    required = (3, 13) if windows else (3, 11)
    if sys.version_info < required:
        parser.exit(1, f'Route requires Python {required[0]}.{required[1]} or newer on this platform.\n')
    root = Path(__file__).resolve().parents[1]
    env = root / '.venv'
    bindir = env / ('Scripts' if windows else 'bin')
    python = bindir / ('python.exe' if windows else 'python')
    command = bindir / ('route-for-codex.exe' if windows else 'route-for-codex')
    if not python.is_file():
        venv.create(env, with_pip=False, symlinks=not windows)
    # An interrupted install can leave the interpreter in place before pip is seeded.
    probe = subprocess.run([str(python), '-I', '-m', 'pip', '--version'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if probe.returncode:
        print('Setting up pip in the Route virtual environment…', flush=True)
        seed = subprocess.run([str(python), '-I', '-m', 'ensurepip', '--default-pip'])
        if seed.returncode:
            parser.exit(1, f'Could not bootstrap pip in {env}. See the Python error above. '
                        'To use another supported Python, move this .venv aside and rerun '
                        'tools/install.py with that interpreter.\n')
    # Stage the verified platform binary before pip collects the package data.
    bundle = [str(python), str(root / 'tools/bundle.py')]
    if args.from_go:
        bundle.append('--from-go')
    subprocess.run(bundle, check=True)
    subprocess.run([str(python), '-I', '-m', 'pip', 'install', '-e', str(root)], check=True)
    if args.connect:
        subprocess.run([str(command), 'connect'], check=True)
    else:
        launch = '& "' + str(command) + '"' if windows else shlex.quote(str(command))
        print(f'Installed Route. To connect your API key, run:\n{launch} connect')


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
