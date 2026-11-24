import json
import re
import subprocess
import urllib.request
import shutil
from pathlib import Path


def eligible(discovered, catalog):
    ids = {x['id'] for x in discovered['data']}
    result = []
    for model in catalog['models']:
        slug = model['slug']
        match = re.match(r'^gpt-(\d+)(?:[.-]|$)', slug)
        if (slug in ids and match and int(match[1]) >= 6 and model.get('supported_in_api')
                and model.get('shell_type') in {'default', 'local', 'shell_command', 'unified_exec'}
                and model.get('supported_reasoning_levels')):
            result.append(model)
    return {'models': result}


def discover(key):
    # Never follow a redirect carrying the developer's bearer credential.
    class FixedOrigin(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            return None

    req = urllib.request.Request('https://api.openai.com/v1/models', headers={'Authorization': 'Bearer ' + key})
    with urllib.request.build_opener(FixedOrigin()).open(req, timeout=20) as response:
        listed = json.load(response)
    codex = codex_path()
    catalog = json.loads(subprocess.check_output([codex, 'debug', 'models', '--bundled']))
    result = eligible(listed, catalog)
    result["accessible_ids"] = sorted({row["id"] for row in listed["data"]})
    return result


def codex_path():
    codex = shutil.which('codex')
    if not codex:
        for path in (Path.home() / '.local/bin/codex', Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex'),
                     Path('/Applications/Codex.app/Contents/Resources/codex'), Path('/opt/homebrew/bin/codex')):
            if path.is_file():
                codex = str(path)
                break
    if not codex:
        raise RuntimeError('Could not locate the installed Codex CLI to read its model catalog')
    return codex


def selection(catalog, previous, effort):
    for model in catalog['models']:
        if model['slug'] == previous:
            levels = [x['effort'] for x in model['supported_reasoning_levels']]
            return previous, effort if effort in levels else model['default_reasoning_level']
    for model in catalog['models']:
        if model['slug'] == 'gpt-6.2-sol' and 'medium' in [x['effort'] for x in model['supported_reasoning_levels']]:
            return model['slug'], 'medium'
    return None


def route_rows(discovered, catalog):
    """Brand only eligible Route rows, keeping model capabilities and upgrades on their billing path."""
    return branded_rows(eligible(discovered, catalog)['models'])


def branded_rows(models):
    slugs = {model['slug'] for model in models}
    rows = []
    for model in models:
        slug = model['slug']
        name = ' '.join(part.capitalize() for part in slug.removeprefix('gpt-').split('-'))
        row = dict(model, slug='route-' + slug, display_name='Route ' + name,
                   description='Uses your OpenAI API key')
        upgrade = model.get('upgrade')
        if upgrade:
            target = upgrade['model']
            row['upgrade'] = dict(upgrade, model='route-' + target) if target in slugs else None
        rows.append(row)
    return rows
