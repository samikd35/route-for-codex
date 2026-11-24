"""Install the public source snapshot into a private, managed CLI environment."""
import argparse
import hashlib
import os
from pathlib import Path
import platform
import shutil
import shlex
import subprocess
import sys
import tarfile
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
WINDOWS = os.name == 'nt'
CADDY_VERSION = '2.11.9'
CADDY_ASSETS = {
    ('Darwin', 'arm64'): ('mac_arm64.tar.gz', 'd075afc620376679a77b453399bf7ada264cab3280b2833e4ed1372abc0c1c13'),
    ('Darwin', 'x86_64'): ('mac_amd64.tar.gz', '22af256a2cc45606f6bfa8786cd89130529331319665926f4e972234a658fb30'),
    ('Windows', 'amd64'): ('windows_amd64.zip', 'ad93112d335ee687100c4c9f11bced16ca590377976b7fe7883882b9e797e472'),
    ('Windows', 'arm64'): ('windows_arm64.zip', 'bdf5fa34e7f3646ee04f59634d66cbcbfa39516f08108d8661ff3ceb3913a0c7'),
}
CODEX_VERSION = '0.171.0-alpha.13'


def download(url, target, expected):
    subprocess.run(['curl.exe' if WINDOWS else 'curl', '--proto', '=https', '--fail', '--silent',
                    '--show-error', '--location', '--retry', '2', '-o', target, url], check=True)
    with target.open('rb') as f:
        if hashlib.file_digest(f, 'sha256').hexdigest() != expected:
            raise RuntimeError(f'Checksum mismatch for {target.name}')


def stage_caddy(work):
    asset, digest = CADDY_ASSETS[platform.system(), platform.machine().lower()]
    filename = f'caddy_{CADDY_VERSION}_{asset}'
    archive = work / filename
    download(f'https://github.com/caddyserver/caddy/releases/download/v{CADDY_VERSION}/{filename}', archive, digest)
    binary = 'caddy.exe' if WINDOWS else 'caddy'
    dest = ROOT / 'route/bin'  # The bootstraps unpack Route into a temporary source directory.
    with (zipfile.ZipFile(archive) if WINDOWS else tarfile.open(archive)) as package:
        for name in (binary, 'LICENSE'):
            member = package.open(name) if WINDOWS else package.extractfile(name)
            with member, (dest / name).open('wb') as out:
                shutil.copyfileobj(member, out)
    (dest / binary).chmod(0o755)


def install_codex(bindir, work):
    found = shutil.which('codex')
    if not found:
        default = (Path(os.environ['LOCALAPPDATA']) / 'Programs/OpenAI/Codex/bin/codex.exe' if WINDOWS
                   else Path.home() / '.local/bin/codex')
        if default.is_file():
            found = str(default)
    if not found:
        name, digest = (('install.ps1', 'cd8eba002fb62e30e9fb05d627a84f08b2372980b84d7e2eb674f04f37813acf')
                        if WINDOWS else ('install.sh', 'b698d8eb50c0fbe0214ea57b5bf2af439054108404c6d2b872989db02f4bd574'))
        installer = work / name
        print(f'Installing OpenAI Codex CLI {CODEX_VERSION}…', flush=True)
        download(f'https://github.com/openai/codex/releases/download/rust-v{CODEX_VERSION}/{name}', installer, digest)
        cmd = ['powershell.exe', '-NoProfile', '-File'] if WINDOWS else ['/bin/sh']
        env = dict(os.environ, CODEX_RELEASE=CODEX_VERSION, CODEX_NON_INTERACTIVE='1',
                   CODEX_INSTALL_DIR=str(bindir))
        if WINDOWS:
            # A caller running pwsh may export its PowerShell 7 modules to Windows PowerShell 5.1.
            env.pop('PSMODULEPATH', None)
        subprocess.run([*cmd, installer], env=env, check=True)
        found = shutil.which('codex')
    if not found:
        raise RuntimeError('The Codex installer did not provide a codex command')
    # The setup flow uses this capability to discover models accessible to the key.
    if subprocess.run([found, 'debug', 'models', '--bundled'], stdout=subprocess.DEVNULL).returncode:
        raise RuntimeError(f'Codex at {found} could not read its bundled model catalog. '
                           'Run codex debug models --bundled for details, fix or update Codex, then rerun this installer.')
    return found


def install(uv, only):
    data = (Path(os.environ['LOCALAPPDATA']) / 'RouteForCodexCLI' if WINDOWS
            else Path.home() / '.local/share/route-for-codex')
    bindir = data / 'bin'
    bindir.mkdir(mode=0o700, parents=True, exist_ok=True)
    fingerprint = hashlib.sha256()
    for file in sorted([*ROOT.glob('route/*.py'), *ROOT.glob('dispatcher/*.go'), ROOT / 'dispatcher/go.mod', ROOT / 'tools/build_dispatcher.py', ROOT / 'pyproject.toml', Path(__file__)]):
        fingerprint.update(file.read_bytes())
    version = data / 'versions' / fingerprint.hexdigest()[:16]
    tool = version / 'tools/route-for-codex'
    python = tool / ('Scripts/python.exe' if WINDOWS else 'bin/python')
    command = version / 'commands' / ('route-for-codex.exe' if WINDOWS else 'route-for-codex')
    # update-shell must see the user's original PATH when persisting the new directory.
    shell_env = dict(os.environ, UV_TOOL_BIN_DIR=str(bindir))
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        if not command.is_file():
            print('Installing Route and its local relay…', flush=True)
            stage_caddy(work)
            subprocess.run([sys.executable, ROOT / 'tools/build_dispatcher.py'], check=True)
            subprocess.run([uv, 'tool', 'install', '--quiet', '--python', sys.executable, ROOT], check=True,
                           env=dict(os.environ, UV_TOOL_DIR=str(version / 'tools'),
                                    UV_TOOL_BIN_DIR=str(command.parent)))
        subprocess.run([uv, 'tool', 'update-shell'], env=shell_env, check=True)
        os.environ['PATH'] = str(bindir) + os.pathsep + os.environ.get('PATH', '')
        codex = install_codex(bindir, work)
        # Publish the launcher only after Route and the selected Codex both work.
        launcher = bindir / ('route-for-codex.cmd' if WINDOWS else 'route-for-codex')
        with tempfile.TemporaryDirectory(dir=bindir) as staging:
            new = Path(staging) / launcher.name
            if WINDOWS:
                relative = python.relative_to(data.parent)
                prefix = f'"%LOCALAPPDATA%\\{relative}" -I -m route.cli'
                new.write_bytes(('@echo off\r\nif "%~1"=="" (\r\n  ' + prefix +
                                 ' --help\r\n) else (\r\n  ' + prefix + ' %*\r\n)\r\n').encode('ascii'))
            else:
                new.write_text(f'#!/bin/sh\nif [ "$#" -eq 0 ]; then set -- --help; fi\nexec {shlex.quote(str(python))} -I -m route.cli "$@"\n')
                new.chmod(0o755)
            os.replace(new, launcher)
        # A compatible Codex outside PATH may have been discovered at the standard location.
        if not shutil.which('codex'):
            subprocess.run([uv, 'tool', 'update-shell'], check=True,
                           env=dict(shell_env, UV_TOOL_BIN_DIR=str(Path(codex).parent)))
            os.environ['PATH'] += os.pathsep + str(Path(codex).parent)
        print(f'Installed {launcher}. In a new terminal, run route-for-codex onboard to connect.', flush=True)
        if only:
            return
        subprocess.run([python, '-I', '-m', 'route.cli', 'onboard'], check=True)
    if sys.stdin.isatty() and input('Open Codex in this folder now? [y/N] ').strip().lower() in ('y', 'yes'):
        subprocess.run([codex], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('uv')
    parser.add_argument('--install-only', action='store_true')
    args = parser.parse_args()
    try:
        install(args.uv, args.install_only)
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
    except (RuntimeError, OSError) as exc:
        sys.exit(str(exc))
