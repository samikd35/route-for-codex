"""Run paid Route image-tool checks with an existing saved Route key and a signed-out Codex home."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from unittest.mock import patch

from route.cli import Prompt, Session, execute, locked
from route.settings import write
from tests.fixture import free_port
from tests.live import IMAGE_PROMPT



def verify_png(workspace, stage):
    from PIL import Image
    dest = workspace / 'kite.png'
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    if not any(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p in stage):
        raise RuntimeError('Workspace PNG does not match the image staged by Route')
    with Image.open(dest, formats=['PNG']) as png:
        png.load()
        return {'sha256': digest, 'dimensions': list(png.size)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', required=True, action='store_true', help='Send billable coding and image requests')
    parser.add_argument('new_directory', type=Path)
    parser.add_argument('--models', nargs='+', choices=['gpt-6.2-sol', 'gpt-6.2-astra'],
                        default=['gpt-6.2-sol', 'gpt-6.2-astra'])
    args = parser.parse_args()
    dest = args.new_directory.resolve()
    dest.mkdir(mode=0o700, parents=True, exist_ok=False)
    codex = shutil.which('codex')
    source = Session()
    source.load()
    if not source.state.get('saved'):
        raise RuntimeError('This qualification needs a key already saved by Route')
    metadata = (source.home / 'models.json').read_text()
    eligible = {row['slug'] for row in json.loads(metadata)['models']}
    if set(args.models) - eligible:
        raise RuntimeError('A requested model is absent from the saved Route catalog')
    with tempfile.TemporaryDirectory(prefix='route-image-', dir='/tmp') as folder:
        root = Path(folder)
        home = root / 'codex'
        home.mkdir()
        write(home / 'config.toml', 'cli_auth_credentials_store = "file"\n')
        env = {'HOME': str(root), 'CODEX_HOME': str(home), 'PATH': os.environ['PATH']}
        login = subprocess.run([codex, 'login', 'status'], env=env, capture_output=True, text=True)
        if 'not logged in' not in (login.stderr + login.stdout).lower():
            raise RuntimeError('Disposable Codex profile must be signed out')
        # Restore only verified nonsecret Route preferences in an isolated Route home.
        # Normal Reconnect retrieves the existing key inside Route and starts a fresh relay.
        with patch.dict(os.environ, ROUTE_HOME=str(root / 'route'), CODEX_HOME=str(home)), patch('route.cli.PORT', free_port()):
            session = Session()
            with locked(session):
                write(session.home / 'models.json', metadata)
                session.state.update(saved=True, default=True, model=args.models[0], effort='medium')
                session.save()
            try:
                with locked(session):
                    execute(session, 'reconnect', Prompt())
                print('Normal Route reconnect succeeded. Codex login status: signed out.', flush=True)
                for model in args.models:
                    workspace = dest / model
                    workspace.mkdir()
                    stage = session.home / 'images'
                    before = set(stage.glob('*.png'))
                    cmd = [codex, 'exec', '--skip-git-repo-check', '--json', '--sandbox', 'workspace-write',
                           '-m', model, '-c', 'model_reasoning_effort="medium"',
                           '-c', 'mcp_servers.route_images.tools.generate_image.approval_mode="approve"', IMAGE_PROMPT]
                    proc = subprocess.run(cmd, cwd=workspace, env=env, capture_output=True, text=True, timeout=420)
                    frames = [json.loads(line) for line in proc.stdout.splitlines() if line.startswith('{')]
                    ids = [e['thread_id'] for e in frames if e.get('type') == 'thread.started']
                    new = set(stage.glob('*.png')) - before
                    if proc.returncode or len(ids) != 1 or len(new) != 1 or not (workspace / 'kite.png').is_file():
                        # This test-only event summary never includes tool inputs, returned images or credentials.
                        items = [e['item'] for e in frames if e.get('type') == 'item.completed']
                        summary = [(i['type'], i.get('server'), i.get('tool'), i.get('status')) for i in items]
                        safe_categories = [k for k in ('requires approval', 'not trusted', 'not available', 'not found',
                            'failed to start', 'timed out', 'rate limit','authentication failed','image generation is unavailable',
                            'rejected the image request','cannot generate images','invalid png') if k in (proc.stdout+proc.stderr).lower()]
                        raise RuntimeError(f'CLI image check failed ({proc.returncode}, {len(new)} staged), events {summary}, categories {safe_categories}')
                    tool_calls = [e['item'] for e in frames if e.get('type') == 'item.completed'
                                  and e.get('item', {}).get('type') == 'mcp_tool_call']
                    names = {(i.get('server'), i.get('tool')) for i in tool_calls}
                    # Code mode may expose the invocation inside its exec item. The
                    # matching private PNG independently checks which server produced it.
                    tool_name = 'mcp__route_images__generate_image'
                    if ('route_images', 'generate_image') not in names and tool_name not in proc.stdout:
                        raise RuntimeError('Codex did not identify the Route MCP tool in its event stream')
                    if not (workspace / 'index.html').is_file():
                        raise RuntimeError('Codex did not create the page')
                    report = dict(model=model, effort='medium', provider='route', codex_login='signed out',
                                  tool=tool_name, thread=ids[0], prompt=IMAGE_PROMPT,
                                  cli=subprocess.check_output([codex, '--version'], text=True).strip(),
                                  **verify_png(workspace, new))
                    write(workspace / 'result.json', json.dumps(report, indent=2) + '\n')
                    print(json.dumps(report), flush=True)
            finally:
                with locked(session):
                    session.stop()


if __name__ == '__main__':
    main()
