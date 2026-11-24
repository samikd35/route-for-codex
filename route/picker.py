"""Start the combined gateway before registering its provider in Codex."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.request

from .models import branded_rows, codex_path, eligible
from .relay import CADDY, combined_configuration, control
from .settings import change, config, write

PROVIDER = 'route-combined'
NATIVE_URL = 'https://chatgpt.com/backend-api/codex'


def client_version():
    return subprocess.check_output([codex_path(), '--version'], text=True).split()[-1].split('-')[0]


def native_login():
    codex = codex_path()
    login = subprocess.run([codex, 'login', 'status'], capture_output=True, text=True)
    return login.returncode == 0 and 'chatgpt' in (login.stdout + login.stderr).lower()


def desktop_clients():
    if sys.platform == 'darwin':
        return (Path('/Applications/Codex.app/Contents/Resources/codex'),
                Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex'))
    if os.name == 'nt':
        programs = Path(os.environ['LOCALAPPDATA']) / 'Programs'
        return (programs / 'Codex/resources/codex.exe', programs / 'ChatGPT/resources/codex.exe')
    return (Path('/opt/Codex/resources/codex'),)


def check_catalog(base, version, token, rows):
    request = urllib.request.Request(base + '/models?client_version=' + version,
                                     headers={'X-Route-Token': 'Bearer ' + token})
    with urllib.request.urlopen(request, timeout=5) as response:
        staged = json.load(response)['models']
    if [row['slug'] for row in staged] != [row['slug'] for row in rows]:
        raise RuntimeError('Combined gateway returned an unexpected model catalog')


def install(session, port, helper):
    current = config()
    if current.get('model_provider', 'openai') not in ('openai', 'route', PROVIDER):
        raise RuntimeError('Combined picker requires the native Codex provider or a previous Route installation')
    journal = session.state.get('journal', {})
    catalog_override = current.get('model_catalog_json')
    provider_key = 'model_providers.' + PROVIDER
    if PROVIDER in current.get('model_providers', {}) and provider_key not in journal:
        raise RuntimeError('An existing route-combined provider controls the Codex picker')
    if journal.get('model_catalog_json', [None])[0]:
        raise RuntimeError('A pre-existing custom catalog must be resolved before combining the native models')
    if catalog_override and journal.get('model_catalog_json', [None, None])[1] != catalog_override:
        raise RuntimeError('An existing model_catalog_json setting controls the Codex picker')
    version = client_version()
    native = native_login()
    rows = branded_rows(json.loads((session.home / 'models.json').read_text())['models'])
    token = secrets.token_urlsafe()
    sock = session.home / ('g' + secrets.token_hex(3))
    lease = session.home / 'picker.token'
    legacy_token = session.credential.read_text()
    cfg = dict(Socket=str(sock), Lease=str(lease), GatewayToken=token, RouteKey=legacy_token,
               NativeURL=NATIVE_URL, RouteURL=f'http://127.0.0.1:{port}/v1',
               Catalogs={version: rows})
    # Desktop can bundle a different CLI build from the one found on PATH.
    for app in desktop_clients():
        if app.is_file():
            other = subprocess.check_output([app, '--version'], text=True).split()[-1].split('-')[0]
            if other not in cfg['Catalogs']:
                bundled = json.loads(subprocess.check_output([app, 'debug', 'models', '--bundled']))
                ids = {'data': [{'id': row['slug'].removeprefix('route-')} for row in rows]}
                cfg['Catalogs'][other] = branded_rows(eligible(ids, bundled)['models'])
    fingerprint = hashlib.sha256(json.dumps([cfg['Catalogs'], native, helper, sys.executable],
                                            sort_keys=True).encode()).hexdigest()
    gateway_port = session.state.get('picker_port')
    if (gateway_port and current.get('model_provider') == PROVIDER
            and session.state.get('picker_fingerprint') == fingerprint and lease.is_file()):
        try:
            check_catalog(f'http://127.0.0.1:{gateway_port}/v1', version, lease.read_text(), rows)
        except (OSError, ValueError, RuntimeError):
            pass
        else:
            return
    binary = CADDY.with_name('dispatcher.exe' if os.name == 'nt' else 'dispatcher')
    child = subprocess.Popen([binary], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=os.name != 'nt',
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        child.stdin.write(json.dumps(cfg).encode())
        child.stdin.close()
        for _ in range(300):
            if child.poll() is not None:
                raise RuntimeError('Combined model gateway failed to start')
            if Path(str(sock) + '.control').exists():
                break
            time.sleep(.01)
        else:
            raise RuntimeError('Combined model gateway timed out')
        if gateway_port is None:
            with socket.socket() as available:
                available.bind(('127.0.0.1', 0))
                gateway_port = available.getsockname()[1]
        base = f'http://127.0.0.1:{gateway_port}/v1'
        server = combined_configuration(gateway_port, sock)['apps']['http']['servers']['combined']
        control(session.admin, '/config/apps/http/servers/combined', server)
        check_catalog(base, version, token, rows)
        write(lease, token)
        provider = dict(name='Route combined', wire_api='responses', base_url=base, model_catalog_url=base+'/models',
                        requires_openai_auth=native, supports_websockets=False, request_max_retries=0, stream_max_retries=0,
                        gateway_oauth=dict(delivery=dict(kind='header', name='X-Route-Token'),
                                           credential_export=dict(command=sys.executable, args=helper)))
        settings = {'model_providers.' + PROVIDER: provider, 'model_provider': PROVIDER}
        if not native:
            settings['model'] = 'route-' + session.state['model']
        restore = ('model_catalog_json', 'model_reasoning_effort', 'model')
        change(session.state, session.file, settings, restore_defaults=restore)
        session.state['picker_fingerprint'] = fingerprint
        session.state['picker_port'] = gateway_port
        session.state['default'] = False
        session.save()
    except BaseException:
        child.terminate()
        child.wait()
        raise
    threading.Thread(target=child.wait, daemon=True).start()
