"""Prove the published default installer reaches a private key prompt from a project directory."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('launcher', nargs='?', choices=['direct', 'npx'], default='direct')
    args = parser.parse_args()
    ref = os.environ['ROUTE_INSTALL_REF']
    prefix = f'https://raw.githubusercontent.com/samikd35/route-for-codex/{ref}/install.'
    if args.launcher == 'npx':
        if os.name == 'nt':
            command = ['pwsh', '-NoProfile', '-Command', 'npx --yes $env:NPX_ROUTE_SPEC; exit $LASTEXITCODE']
        else:
            command = ['npx', '--yes', os.environ['NPX_ROUTE_SPEC']]
    elif os.name == 'nt':
        # The first install step uses Windows PowerShell 5.1. Exercise PowerShell 7 here.
        command = ['pwsh', '-NoProfile', '-Command',
                   f"Invoke-RestMethod '{prefix}ps1' | Invoke-Expression"]
    else:
        command = ['bash', '-c', f'bash -c "$(curl -fsSL {prefix}sh)"']
    with tempfile.TemporaryDirectory(prefix='route project ') as work:
        env = dict(os.environ, CODEX_HOME=str(Path(work) / 'codex'), ROUTE_HOME=str(Path(work) / 'route'))
        result = subprocess.run(command, cwd=work, env=env, input='\n', capture_output=True,
                                text=True, errors='replace', timeout=240)
        output = result.stdout + result.stderr
        if result.returncode == 0 or 'OpenAI API key' not in output or 'Cancelled' not in output:
            raise RuntimeError('Rerunning the public install command did not reach and cancel the key prompt: '
                               + output[-1500:])
    print('The normal one-command install reached the key prompt. Cancellation made no API requests.')


if __name__ == '__main__':
    main()
