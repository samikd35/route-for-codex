"""Build a development installer on its target OS. Never installs it."""
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def put(path, data):
    path.parent.mkdir(exist_ok=True, parents=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())


def main():
    win = sys.platform == 'win32'
    binary = ROOT / 'route/bin' / ('caddy.exe' if win else 'caddy')
    if not binary.is_file():
        sys.exit('Stage the pinned binary with tools/bundle.py first.')
    out = ROOT / 'dist'
    out.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        dest = work / 'bundle'
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--onedir', '--noupx', '--name', 'route',
                        '--paths', str(ROOT), '--distpath', str(dest), '--workpath', str(work / 'build'),
                        '--specpath', tmp, '--collect-submodules', 'keyring.backends', '--copy-metadata', 'mcp',
                        '--add-binary', f'{binary}{os.pathsep}route/bin',
                        '--add-binary', f'{binary.with_name("dispatcher.exe" if win else "dispatcher")}{os.pathsep}route/bin',
                        '--add-data', f'{binary.parent / "LICENSE"}{os.pathsep}route/bin',
                        '--add-data', f'{ROOT / "LICENSE"}{os.pathsep}.',
                        *(['--add-binary', f'{binary.parent / "control.exe"}{os.pathsep}route/bin'] if win else []),
                        str(ROOT / 'tools/entry.py')], cwd=tmp, check=True)
        root = work / 'root'
        if sys.platform == 'darwin':
            app = root / 'Applications/Route.app/Contents'
            app.mkdir(parents=True)
            shutil.move(dest / 'route', app / 'MacOS')
            (app / 'MacOS/_internal').rename(app / 'Frameworks')
            put(app / 'Info.plist', plistlib.dumps({'CFBundleExecutable': 'route', 'CFBundleName': 'Route',
                'CFBundleIdentifier': 'local.route.setup', 'CFBundlePackageType': 'APPL',
                'CFBundleVersion': '2', 'CFBundleShortVersionString': '0.1.1'}))
            exe = '/Applications/Route.app/Contents/MacOS/route'
            put(root / 'Library/LaunchAgents/local.route.login.plist', plistlib.dumps({
                'Label': 'local.route.login', 'ProgramArguments': [exe, 'login'], 'RunAtLoad': True}))
            bindir = root / 'usr/local/bin'
            bindir.mkdir(parents=True)
            (bindir / 'route-for-codex').symlink_to(exe)
            target = out / f'Route-dev-{platform.machine()}.pkg'
            subprocess.run(['pkgbuild', '--root', str(root), '--identifier', 'local.route.dev',
                            '--version', '0.1.1', '--install-location', '/', str(target)], check=True)
        elif sys.platform.startswith('linux'):
            target = out / f'route-dev-{platform.machine()}.deb'
            (root / 'opt').mkdir(parents=True)
            shutil.move(dest / 'route', root / 'opt/route')
            (root / 'usr/bin').mkdir(parents=True)
            (root / 'usr/bin/route-for-codex').symlink_to('/opt/route/route')
            # Avoid shadowing the OS network utility named route.
            for path, action in [('usr/share/applications/route-codex.desktop', 'setup'), ('etc/xdg/autostart/route-codex.desktop', 'login')]:
                put(root / path, f'[Desktop Entry]\nType=Application\nName=Route for Codex\nExec=/opt/route/route {action}\nTerminal=false\n')
            arch = subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip()
            put(root / 'DEBIAN/control', f'Package: route-for-codex\nVersion: 0.1~dev1\nArchitecture: {arch}\nMaintainer: Route developers\nDescription: Local Responses relay for Codex\n')
            subprocess.run(['dpkg-deb', '--build', '--root-owner-group', str(root), str(target)], check=True)
        elif win:
            target = out / 'Route-dev-setup.exe'
            script = work / 'route.iss'
            # Only this launcher directory goes on PATH. The private route.exe
            # remains available at its original location for installed helpers.
            put(dest / 'route/bin/route-for-codex.cmd', '@echo off\r\n"%~dp0..\\route.exe" %*\r\n')
            put(script, f'''[Setup]
AppId=RouteForCodex
AppName=Route for Codex
AppVersion=0.1dev1
DefaultDirName={{localappdata}}\\Programs\\RouteForCodex
PrivilegesRequired=lowest
ChangesEnvironment=yes
OutputDir={out}
OutputBaseFilename=Route-dev-setup
[Files]
Source: "{dest / 'route'}\\*"; DestDir: "{{app}}"; Flags: recursesubdirs createallsubdirs
[Icons]
Name: "{{userprograms}}\\Route for Codex"; Filename: "{{app}}\\route.exe"; Parameters: "setup"
Name: "{{userstartup}}\\Route Login"; Filename: "{{app}}\\route.exe"; Parameters: "login"; Flags: runminimized
''' + (ROOT / 'tools/windows-path.iss').read_text())
            subprocess.run(['ISCC', str(script)], check=True)
        else:
            sys.exit('Unsupported platform')
        print(target)


if __name__ == '__main__':
    main()
