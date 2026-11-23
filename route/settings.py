import copy
import json
import os
from pathlib import Path
import tempfile

import tomlkit


def write(path, text):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, mode='w', encoding='utf8') as f:
        try:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
            f.close()
            os.replace(f.name, path)
        finally:
            Path(f.name).unlink(missing_ok=True)


def config_path():
    return Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')) / 'config.toml'


def config():
    p = config_path()
    return tomlkit.parse(p.read_text()) if p.exists() else tomlkit.document()


def change(state, statefile, values=None):
    doc = config()
    original = tomlkit.dumps(doc)
    journal = copy.deepcopy(state.get('journal', {}))
    for path in (values if values is not None else list(journal)):
        parent = doc
        if '.' in path:
            table, _ = path.split('.', 1)
            if table not in doc and values is not None:
                doc[table] = tomlkit.table()
            parent = doc.get(table, {})
        k = path.split('.')[-1]
        if values is not None:
            if '.' in path and k in parent and path not in journal:
                raise RuntimeError(f'Codex setting {path} already exists. Choose another name for the existing entry.')
            if path == 'mcp_servers.route_images' and path in journal and parent.get(k) not in journal[path]:
                # An edited MCP definition belongs to the developer, including on later registration.
                continue
            new = values[path]
            old = parent.get(k)
            if hasattr(old, 'unwrap'):
                old = old.unwrap()
            if path not in journal or old != journal[path][1]:
                journal[path] = [old, new]
            journal[path][1] = new
            parent[k] = new
        else:
            old, written = journal[path]
            if parent.get(k) == written:
                if old is None:
                    del parent[k]
                else:
                    parent[k] = old
    updated = tomlkit.dumps(doc)
    if values is not None and updated == original and journal == state.get('journal'):
        return
    if values is not None:
        state['journal'] = journal
        write(statefile, json.dumps(state))  # Persist undo information before editing Codex.
    if updated != original:
        write(config_path(), updated)
    if values is None:
        state['journal'] = {}
        write(statefile, json.dumps(state))
