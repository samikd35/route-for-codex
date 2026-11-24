import argparse
from contextlib import contextmanager, nullcontext
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError

from .progress import accent, stage
from .check import CredentialRejected, check, http_error
from .models import discover, selection
from .images import TOOL_SECONDS
from .relay import API_PATHS, MATCH_PATH, CADDY, Relay, admin_socket, configuration, control
from .settings import change, config, write


SERVICE = 'Route:https://api.openai.com/v1/responses'
PORT = 42839


def vault():
    # Select a native implementation, never a file-based fallback backend.
    if sys.platform == 'darwin':
        from keyring.backends.macOS import Keyring
    elif sys.platform.startswith('linux'):
        from keyring.backends.SecretService import Keyring
    elif sys.platform == 'win32':
        from keyring.backends.Windows import WinVaultKeyring
        store = WinVaultKeyring()
        store.persist = 'local machine'
        return store
    else:
        raise RuntimeError('Unsupported credential store')
    return Keyring()


def windows_home(path):
    import pywintypes
    import win32api
    import win32file
    import win32security as sec

    token = sec.OpenProcessToken(win32api.GetCurrentProcess(), sec.TOKEN_QUERY)
    user = sec.ConvertSidToStringSid(sec.GetTokenInformation(token, sec.TokenUser)[0])
    # Elevated processes may default to Administrators as owner. Set the user
    # and inheritable private ACL atomically, before any state files exist.
    path.parent.mkdir(parents=True, exist_ok=True)
    attrs = pywintypes.SECURITY_ATTRIBUTES()
    attrs.SECURITY_DESCRIPTOR = sec.ConvertStringSecurityDescriptorToSecurityDescriptor(
        f'O:{user}D:P(A;OICI;FA;;;{user})(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)', 1)
    try:
        win32file.CreateDirectory(str(path), attrs)
    except pywintypes.error as exc:
        if exc.winerror != 183:  # ERROR_ALREADY_EXISTS
            raise
    sd = sec.GetFileSecurity(str(path), sec.OWNER_SECURITY_INFORMATION | sec.DACL_SECURITY_INFORMATION)
    acl = sd.GetSecurityDescriptorDacl()
    # Python's mode-0700 directories grant OWNER RIGHTS (S-1-3-4).
    # That principal is private only after checking the owner explicitly.
    allowed = {user, 'S-1-3-4', 'S-1-5-32-544', 'S-1-5-18'}
    if (not path.is_dir() or sec.ConvertSidToStringSid(sd.GetSecurityDescriptorOwner()) != user or acl is None
            or any(sec.ConvertSidToStringSid(acl.GetAce(i)[-1]) not in allowed for i in range(acl.GetAceCount()))):
        raise RuntimeError('Route requires a private Windows directory owned by the current user')


class Session:
    def __init__(self):
        self.home = Path(os.environ.get('ROUTE_HOME', Path.home() / '.route')).resolve()
        if sys.platform == 'win32':
            windows_home(self.home)
        else:
            self.home.mkdir(mode=0o700, parents=True, exist_ok=True)
            if self.home.stat().st_uid != os.getuid() or self.home.stat().st_mode & 0o077:
                raise RuntimeError('Route home must be private to your user (mode 0700)')
        self.file = self.home / 'state.json'
        self.admin = self.home / 'admin.sock'
        self.credential = self.home / 'relay.token'

    def load(self):
        self.state = json.loads(self.file.read_text()) if self.file.exists() else {}

    def save(self):
        write(self.file, json.dumps(self.state))

    def active(self):
        if sys.platform == 'win32' and CADDY.with_name('control.exe').is_file():
            return self.admin.exists() and subprocess.run([CADDY.with_name('control.exe'), self.admin, 'ping'], creationflags=subprocess.CREATE_NO_WINDOW).returncode == 0
        if not self.admin.exists():
            return False
        try:
            with admin_socket(self.admin):
                return True
        except (FileNotFoundError, ConnectionRefusedError):
            return False
        except OSError as exc:
            if getattr(exc, 'winerror', None) == 10061:
                return False
            raise

    def start(self, key):
        self.admin.unlink(missing_ok=True)
        relay = Relay(PORT, key, admin=self.admin, detached=True)
        try:
            write(self.credential, relay.token)
            self.state['picker_paths'] = True
            self.state['image_endpoint'] = True
            self.save()
            # Reap the detached child when this UI stays open across Disconnect.
            import threading
            threading.Thread(target=relay.process.wait, daemon=True).start()
        except BaseException:
            relay.close()
            raise

    def configure_images(self):
        # Upgrade the existing matcher through the private admin socket. Session-only
        # connections keep their in-memory upstream credential across this reload.
        if not self.state.get('picker_paths'):
            control(self.admin, MATCH_PATH, API_PATHS)
            self.state['picker_paths'] = True
            self.state['image_endpoint'] = True
            self.save()

    def image_settings(self):
        return {'mcp_servers.route_images': {'command': sys.executable,
                'args': invocation('--home', str(self.home), '--relay-port', str(PORT), 'images-mcp'),
                'tool_timeout_sec': TOOL_SECONDS}}

    def register(self):
        provider = {'name': 'Route', 'base_url': f'http://127.0.0.1:{PORT}/v1', 'wire_api': 'responses',
                    'auth': {'command': sys.executable, 'args': invocation('--home', str(self.home), 'token')}}
        change(self.state, self.file, {'model_providers.route': provider, **self.image_settings()})

    def stop(self):
        if self.active():
            control(self.admin, '/stop')
            for _ in range(100):
                if not self.active():
                    break
                time.sleep(.02)
            else:
                raise RuntimeError('Timed out waiting for relay shutdown')
        (self.home / 'picker.token').unlink(missing_ok=True)
        self.credential.unlink(missing_ok=True)
        self.state.update(intended=False, waiting=False)
        self.save()
        if self.state.get('journal'):
            change(self.state, self.file)


@contextmanager
def locked(session):
    with (session.home / 'lock').open('a') as lock:
        if sys.platform == 'win32':
            import msvcrt
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        session.load()
        yield


def invocation(*args):
    return list(args) if getattr(sys, 'frozen', False) else ['-I', '-m', 'route.cli', *args]


class Prompt:
    def __init__(self, window=False):
        self.window = window

    def yes(self, message):
        if self.window:
            from tkinter import messagebox
            return messagebox.askyesno('Route', message)
        return input(message + ' [y/N] ').strip().lower() in ('y', 'yes')

    def text(self, message, secret=False):
        if self.window:
            from tkinter import simpledialog
            value = simpledialog.askstring('Route', message, show='*' if secret else None)
        else:
            # Windows getpass reads the console even when stdin is a pipe.
            # Interactive entry stays masked. Redirected input is never echoed.
            value = (getpass.getpass if secret and sys.stdin.isatty() else input)(message + ': ')
        if not value:
            raise RuntimeError('Cancelled')
        return value.strip()


def install_picker(s):
    from .picker import install
    install(s, PORT, invocation('--home', str(s.home), 'picker-token'))


def execute(s, action, prompt, *, initial_key=None, progress=lambda label: nullcontext()):
    onboarding = action == 'onboard'
    state = s.state
    active = s.active()
    if action == 'onboard':
        if not active and state.get('saved') and state.get('model'):
            execute(s, 'reconnect', prompt)
            active = True
        if state.get('saved') and not state.get('model') and initial_key is None:
            try:
                initial_key = vault().get_password(SERVICE, 'upstream')
            except Exception:
                raise RuntimeError('Unlock the OS credential store and run onboard again') from None
        if active and state.get('model'):
            action = 'test'
        else:
            action = 'replace' if active else 'connect'
    if action == 'status':
        if active:
            return 'Connected.'
        if state.get('waiting'):
            return 'Waiting for unlock.'
        return 'Disconnected.' + (' Your API key is saved on this device.' if state.get('saved') else '')
    if action in ('disconnect', 'forget'):
        s.stop()
        if action == 'forget' and (state.get('saved') or state.get('stale_saved')):
            vault().delete_password(SERVICE, 'upstream')
            state.update(saved=False, stale_saved=False)
            s.save()
        return execute(s, 'status', prompt)
    if active and action in ('reconnect', 'login', 'test', 'select'):
        s.configure_images()
        change(s.state, s.file, s.image_settings())
    if action == 'login' and (active or not state.get('intended') or not state.get('saved')):
        return execute(s, 'status', prompt)
    if action in ('login', 'reconnect') and not active and state.get('saved'):
        if action == 'login' and sys.platform == 'darwin':
            import ctypes
            framework = ctypes.CDLL('/System/Library/Frameworks/Security.framework/Security')
            if framework.SecKeychainSetUserInteractionAllowed(False) != 0:
                raise RuntimeError('Cannot disable login-time credential prompts')
        try:
            if action == 'login' and sys.platform.startswith('linux'):
                import secretstorage
                from contextlib import closing
                with closing(secretstorage.dbus_init()) as bus:
                    collection = secretstorage.Collection(bus, '/org/freedesktop/secrets/aliases/default')
                    if collection.is_locked():
                        raise RuntimeError('Locked')
                    items = list(collection.search_items(vault()._query(SERVICE, 'upstream')))
                    key = items[0].get_secret().decode() if items and not items[0].is_locked() else None
                    if not key:
                        raise RuntimeError('Unavailable')
            else:
                key = vault().get_password(SERVICE, 'upstream')
        except Exception:
            if action != 'login':
                raise RuntimeError('Unlock the OS credential store and reconnect') from None
            state['waiting'] = True
            s.save()
            return 'Waiting for unlock.'
        if not key:
            raise RuntimeError('The saved API key was not found. Connect with a key.')
        s.start(key)
        s.register()
        if state.get('model'):
            install_picker(s)
        state.update(intended=True, waiting=False)
        s.save()
        return 'Reconnected.'
    if action == 'reconnect':
        if active:
            return 'Already connected.'
        action = 'connect'
    if action in ('connect', 'replace'):
        if active and action == 'connect':
            raise RuntimeError('Already connected. Use test or replace.')
        if not active and action == 'replace':
            raise RuntimeError('Relay stopped. Use connect.')
        key = initial_key if initial_key is not None else prompt.text('OpenAI API key', secret=True)
        if active:
            control(s.admin, '/load', configuration(PORT, s.credential.read_text(), key, admin=s.admin))
        else:
            s.start(key)
            state['default'] = False
        state.pop('verified_selection', None)
        state.pop('model', None)
        # A rejected replacement must never cause recovery with an older saved key.
        old_saved = state.get('saved', False)
        state.update(intended=False, waiting=False, saved=False, stale_saved=old_saved or state.get('stale_saved', False))
        s.save()
        try:
            vault().set_password(SERVICE, 'upstream', key)
        except Exception:
            if old_saved:
                # Keep old storage ineligible for reconnect until explicitly forgotten.
                state['stale_saved'] = True
            state['saved'] = False
            s.save()
            if not prompt.yes('Secure storage unavailable. Use this key for this session only?'):
                s.stop()
                raise RuntimeError('Disconnected without saving the new key') from None
        else:
            state.update(saved=True, stale_saved=False)
        state['intended'] = bool(state['saved'])
        s.save()
        # Remove old entries before discovery, including on a failed key replacement.
        write(s.home / 'models.json', '{"models":[]}')
        with progress('Finding models available to your key'):
            catalog = discover(key)
        write(s.home / 'models.json', json.dumps(catalog))
        if not catalog['models']:
            raise RuntimeError('This key has no discoverable compatible GPT-6-or-later model')
    if action in ('connect', 'replace', 'select'):
        if not s.active():
            raise RuntimeError('Relay stopped. Use reconnect.')
        catalog = json.loads((s.home / 'models.json').read_text())
        if not catalog['models']:
            raise RuntimeError('No eligible models. Use replace to repeat discovery.')
        doc = config()
        selected = selection(catalog, doc.get('model'), doc.get('model_reasoning_effort'))
        if selected is None or action == 'select':
            ids = [m['slug'] for m in catalog['models']]
            model = prompt.text('Choose a model: ' + ', '.join(ids))
            if model not in ids:
                raise RuntimeError('Model is not in the eligible catalog')
            selected = selection(catalog, model, None)
        state['model'], state['effort'] = selected
        s.save()
    elif action != 'test':
        raise RuntimeError('Unknown action')
    if not s.active():
        raise RuntimeError('Relay stopped. Use reconnect.')
    if not state.get('model'):
        raise RuntimeError('No selected model. Use replace to repeat discovery.')
    doc = config()
    selected = (state['model'], state['effort'])
    if action == 'test' and doc.get('model_provider') == 'route':
        selected = (doc.get('model', selected[0]), doc.get('model_reasoning_effort', selected[1]))
    if not onboarding or state.get('verified_selection') != list(selected):
        check(PORT, s.credential.read_text(), *selected, progress=progress)
        state['verified_selection'] = list(selected)
        s.save()
    else:
        print('Your connection was already verified.', flush=True)
    with progress('Registering and checking models in Codex'):
        s.register()
        install_picker(s)
    return 'Connection test passed.'


def onboard(session, prompt):
    action = 'onboard'
    print('Connect your OpenAI project. Verifying a new key uses two billable model requests.\n'
          'When prompted, paste your key and press Enter. Input is hidden.', flush=True)
    while True:
        try:
            result = execute(session, action, prompt, progress=stage)
            break
        except (HTTPError, CredentialRejected) as exc:
            if isinstance(exc, HTTPError) and exc.code not in (401, 403):
                raise
            if not sys.stdin.isatty():
                raise
            print('OpenAI rejected the key or its project permissions.', flush=True)
            if not prompt.yes('Paste another key?'):
                raise RuntimeError('Setup paused. Run route-for-codex onboard to continue.') from None
            action = 'replace' if session.active() else 'connect'
    print(result)
    print('\n' + accent('Ready to use Route', sys.stdout) + '\n')
    rows = json.loads((session.home / 'models.json').read_text())['models']
    from .models import branded_rows
    selected = next(row for row in branded_rows(rows) if row['slug'] == 'route-' + session.state['model'])
    print('In a new Codex chat, open the model picker.')
    if config()['model_providers']['route-combined']['requires_openai_auth']:
        print('  Ordinary models    Use your existing Codex connection')
    print(f'  {selected["display_name"]:<18} Uses your OpenAI project key')


def main():
    p = argparse.ArgumentParser(prog='route-for-codex')
    p.add_argument('--home', help=argparse.SUPPRESS)
    p.add_argument('--relay-port', type=int, default=PORT, help=argparse.SUPPRESS)
    actions = ('connect', 'test', 'select', 'replace', 'disconnect', 'reconnect', 'forget', 'status', 'setup', 'login', 'token', 'images-mcp', 'onboard', 'picker-token', 'catalog-for-version')
    p.add_argument('action', choices=actions, nargs='?', default='setup')
    p.add_argument('--client-version', help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.home:
        os.environ['ROUTE_HOME'] = args.home
    try:
        s = Session()
        if args.action == 'catalog-for-version':
            from .picker import refresh_rows
            print(json.dumps(refresh_rows(s, args.client_version)))
            return
        if args.action == 'images-mcp':
            from .images import serve
            serve(s, args.relay_port)
            return
        if args.action in ('token', 'picker-token'):
            if not s.active():
                raise RuntimeError('Relay stopped')
            print(((s.home / 'picker.token') if args.action == 'picker-token' else s.credential).read_text())
            return
        if args.action == 'setup':
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.title('Route for Codex')
            panel = tk.Frame(root, padx=16, pady=14)
            panel.pack(fill='both', expand=True)

            def click(action, **options):
                try:
                    with locked(s):
                        result = execute(s, action, Prompt(True), **options)
                except Exception as exc:
                    messagebox.showerror('Route', str(http_error(exc.code)) if isinstance(exc, HTTPError) else str(exc))
                    return False
                if result == 'Connection test passed.':
                    result += ' Open a new local Codex chat and select a Route model.'
                messagebox.showinfo('Route', result)
                show_setup()
                return True

            def show_setup():
                for widget in panel.winfo_children():
                    widget.destroy()
                s.load()
                if s.active() or s.state.get('saved') or s.state.get('stale_saved'):
                    for action in actions[:8]:
                        tk.Button(panel, text=action.capitalize(), command=lambda a=action: click(a)).pack(fill='x', pady=2)
                    return
                tk.Label(panel, text='OpenAI API key').pack(anchor='w')
                field = tk.Entry(panel, show='*', width=40)
                field.pack(fill='x')
                field.focus_set()
                tk.Label(panel, text='Route verifies your key with two billable model requests.\nCoding and image generation use your OpenAI project.',
                         anchor='w', justify='left').pack(fill='x', pady=8)
                def connect():
                    key = field.get().strip()
                    if not key:
                        field.focus_set()
                        return
                    field.delete(0, 'end')
                    submit.config(state='disabled', text='Checking connection…')
                    root.update_idletasks()
                    # A rejected first key can leave an active relay. A retry must rotate it.
                    if not click('replace' if s.active() else 'connect', initial_key=key):
                        submit.config(state='normal', text='Connect to Codex')
                        field.focus_set()

                submit = tk.Button(panel, text='Connect to Codex', command=connect)
                submit.pack(fill='x', pady=6)
                field.bind('<Return>', lambda _: submit.invoke())

            show_setup()
            root.mainloop()
        else:
            with locked(s):
                if args.action == 'onboard':
                    onboard(s, Prompt())
                else:
                    print(execute(s, args.action, Prompt()))
    except HTTPError as exc:
        p.exit(1, str(http_error(exc.code)) + '\n')
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        p.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
