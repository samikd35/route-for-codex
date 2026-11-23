"""Exercise a live native → Route → native coding task with an existing connected Route relay."""
import argparse
from contextlib import ExitStack
import json
import hashlib
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile
import tomllib

from route.models import route_rows
from route.relay import CADDY, combined_configuration
from tests.combined import ASTRA, SOL, PROVIDER, Client, free_port, listening, service, write_profile


def overrides(config, prefix=''):
    args = []
    for key, val in config.items():
        name = prefix + key
        if isinstance(val, dict):
            args.extend(overrides(val, name + '.'))
        else:
            args.extend(['-c', name + '=' + json.dumps(val)])
    return args


def run(dispatcher, codex, root, native_model, image_dir=None):
    alias = "route-" + native_model
    workspace = root / 'workspace'
    workspace.mkdir()
    nonce = secrets.token_hex(16)
    (workspace / 'value').write_text(nonce)
    (workspace / 'actual').write_text('wrong')
    # The legacy relay keeps the upstream project key in its existing process.
    route_home = Path(os.environ.get('ROUTE_HOME', Path.home() / '.route'))
    token = subprocess.check_output([os.sys.executable, '-m', 'route.cli', 'token'], text=True).strip()
    saved = json.loads((route_home / 'models.json').read_text())
    catalog = json.loads(subprocess.check_output([codex, 'debug', 'models', '--bundled']))
    version = subprocess.check_output([codex, '--version'], text=True).split()[-1]
    rows = route_rows({'data': [{'id': m['slug']} for m in saved['models']]}, catalog)
    assert alias in {r['slug'] for r in rows}
    gateway_token = secrets.token_urlsafe()
    token_file = root / 'proof.token'
    token_file.write_text(gateway_token)
    port = free_port()
    sock = root / 'dispatch.sock'
    write_profile(root, f'http://127.0.0.1:{port}/v1', token_file)
    config = tomllib.loads((root / 'config.toml').read_text())
    # The test keeps Codex in charge of its existing native login. Only this command
    # sees the new provider, independent of any catalog override in config.toml.
    del config['cli_auth_credentials_store']
    config['log_dir'] = str(root / 'logs')
    args = overrides(config)
    plan = [
        (native_model, 'Run cat value in the workspace and print its stdout into the tool result so that the full value is visible to the next turn. If calling exec_command inside a JavaScript tool, use text(result.output). Confirm that the output contains 32 hexadecimal characters. Reply with just READ.'),
        (alias, 'Write the exact value you read in the previous turn into actual. Use your conversation history. Do not read value again. Run cmp actual value and report the result.'),
        (native_model, 'Reply with the exact value you read and verified earlier, using only conversation history. Use no tools.'),
    ]
    cfg = dict(Socket=str(sock), GatewayToken=gateway_token, RouteKey=token,
               NativeURL='https://chatgpt.com/backend-api/codex', RouteURL='http://127.0.0.1:42839/v1',
               Catalogs={version.split('-')[0]: rows})
    with ExitStack() as stack:
        stack.enter_context(service([dispatcher], cfg, sock.exists))
        stack.enter_context(service([CADDY, 'run', '--config', '-'], combined_configuration(port, sock),
                                    lambda: listening(port)))
        if image_dir is not None:
            image_dir.mkdir(parents=True, exist_ok=False)
            prompt = ('Use the built-in image generation tool to generate a watercolor of a red cable plugged into a blue router. '
                      'Save its PNG in the current workspace and create index.html displaying that image. '
                      'If the built-in tool is unavailable, reply IMAGE_TOOL_UNAVAILABLE and stop. Use only that tool to generate the illustration.')
            cmd = [codex, 'exec', '--ignore-user-config', '--skip-git-repo-check', '--json', *args, '-m', alias, prompt]
            proc = subprocess.run(cmd, cwd=image_dir, capture_output=True, text=True, timeout=300)
            frames = [json.loads(line) for line in proc.stdout.splitlines() if line.startswith('{')]
            items = [e['item'] for e in frames if e.get('type') == 'item.completed']
            pngs = [p for p in image_dir.rglob('*.png') if p.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')]
            threads = [e['thread_id'] for e in frames if e.get('type') == 'thread.started']
            if len(threads) != 1:
                raise RuntimeError('CLI did not report the image chat ID')
            codex_home = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))
            generated = codex_home / 'generated_images' / threads[0]
            def digest(path):
                with path.open('rb') as f:
                    return hashlib.file_digest(f, 'sha256').digest()
            matches_client_artifact = bool({digest(p) for p in pngs} & {digest(p) for p in generated.glob('*.png')})
            outcome = dict(client=version, model=alias, matches_client_artifact=matches_client_artifact, client_reported_unavailable=any(
                'IMAGE_TOOL_UNAVAILABLE' in i.get('text','') for i in items), png_count=len(pngs),
                page_exists=(image_dir/'index.html').is_file(), emitted_item_types=sorted({i['type'] for i in items}))
            print(json.dumps(outcome),flush=True)
            if proc.returncode or not matches_client_artifact or not outcome['page_exists']:
                raise RuntimeError('Client image generation and page creation did not pass')
            return
        thread = None
        for model, prompt in plan:
            cmd = [codex, 'exec', *(['resume'] if thread else []), '--ignore-user-config', '--skip-git-repo-check',
                   '--json', *args, '-m', model, *([thread] if thread else []), prompt]
            result = subprocess.run(cmd, cwd=workspace, capture_output=True, text=True, timeout=150)
            events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
            ids = [e['thread_id'] for e in events if e.get('type') == 'thread.started']
            if len(ids)!=1 or (thread and ids[0]!=thread):
                raise RuntimeError('Codex failed to start or resume the test thread')
            thread = ids[0]
            if result.returncode or any(e.get('type') == 'turn.failed' for e in events):
                # Emit only status/code categories. Error bodies can include request data.
                why = (result.stderr + result.stdout).lower()
                categories = [x for x in ('native model unavailable', 'native catalog unavailable','unsupported codex version',
                    'unsupported gateway endpoint','unsupported request encoding','invalid_encrypted_content',
                    'could not be verified','invalid_request_error','insufficient_quota','account_deactivated',
                    'unsupported parameter','model_not_found','invalid_api_key','upstream connection failed','stream disconnected',
                    'previous_response_id') if x in why]
                status = re.findall(r'(?:status(?: code)?[ :]+|http[ /]+)([45]\d\d)', why)
                print(json.dumps(dict(thread=thread, model=model, success=False, status=status, categories=categories)),flush=True)
                raise RuntimeError('Live turn failed')
            if model == alias and (workspace / 'actual').read_text().strip()!=nonce:
                raise RuntimeError('Route turn did not write the verified value')
            print(json.dumps(dict(thread=thread, model=model, success=True)),flush=True)
        messages = [e.get('item',{}).get('text','') for e in events if e.get('type')=='item.completed']
        if not any(nonce in msg for msg in messages):
            raise RuntimeError('Native turn lost the prior value')
        print('Live edit and recall verified.', flush=True)
        # Resume just the test chat in the stock app-server to invoke manual compaction.
        # Auth and session persistence stay with Codex. The child-only overrides win
        # over the user's legacy catalog for this one RPC process.
        compaction_catalog = root / 'compaction-models.json'
        seed = next(m for m in catalog['models'] if m['slug'] == native_model)
        compaction_catalog.write_text(json.dumps({'models': [seed, *rows]}))
        compact_options = [*args, '-c', 'model_catalog_json=' + json.dumps(str(compaction_catalog))]
        with Client(codex, root, workspace, options=compact_options, env=os.environ.copy()) as client:
            resumed = client.rpc('thread/resume', {'threadId': thread, 'model': native_model, 'modelProvider': PROVIDER})
            assert resumed['thread']['id'] == thread and resumed['modelProvider'] == PROVIDER
            client.rpc('thread/compact/start', {'threadId': thread})
            client.complete(thread)
            if not client.compacted:
                raise RuntimeError('Codex did not report a completed compaction')
        for model in (alias, native_model):
            cmd = [codex, 'exec', 'resume', '--ignore-user-config', '--skip-git-repo-check',
                   '--json', *args, '-m', model, thread, 'Using only conversation history, return the previously verified value. Do not run tools.']
            proc = subprocess.run(cmd, cwd=workspace, capture_output=True, text=True, timeout=150)
            frames = [json.loads(line) for line in proc.stdout.splitlines() if line.startswith('{')]
            ids = [e['thread_id'] for e in frames if e.get('type') == 'thread.started']
            items = [e['item'] for e in frames if e.get('type') == 'item.completed']
            if (proc.returncode or ids != [thread] or not any(nonce in i.get('text','') for i in items)
                    or any(i['type'] in ('command_execution', 'mcp_tool_call', 'file_change') for i in items)):
                raise RuntimeError(f'{model} did not recall the value after compaction and resume')
            print(json.dumps(dict(thread=thread, model=model, compacted=True, resumed=True, recall=True)),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dispatcher', required=True, type=Path)
    parser.add_argument('--codex', default=shutil.which('codex'))
    parser.add_argument('--live', action='store_true', required=True, help='Send billable requests to both accounts')
    parser.add_argument('--image', type=Path, help='Run the built-in CLI image check in a new workspace')
    parser.add_argument('--model', choices=(SOL, ASTRA), default=SOL)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(dir='/tmp', prefix='route-live-mix-') as directory:
        run(args.dispatcher.resolve(), args.codex, Path(directory), args.model, args.image.resolve() if args.image else None)
