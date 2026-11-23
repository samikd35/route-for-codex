"""Prepare separate workspaces and independently verify a live coding result."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import secrets
import subprocess
import sys


IMAGE_PROMPT = ("Use Route's generate_image MCP tool (server route_images) to generate one PNG illustration "
          "of a red kite above a blue lake. Copy the returned file to kite.png in the current workspace "
          "and create a minimal index.html that displays kite.png. If the tool fails, report its error "
          "and stop without retrying or using a different image tool.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['prepare', 'verify'])
    p.add_argument('directory', type=Path)
    p.add_argument('--client', choices=['desktop', 'cli'], required=True)
    p.add_argument('--model', choices=['gpt-6.2-sol', 'gpt-6.2-astra'], required=True)
    p.add_argument('--effort', default='medium')
    p.add_argument('--built-in-image', action='store_true', help='Run the separate Codex built-in tool qualification')
    args = p.parse_args()
    root = args.directory.resolve() / f'{args.client}-{args.model}-{args.effort}'
    code, image = root / 'coding', root / 'image'
    if args.action == 'prepare':
        root.mkdir(parents=True, exist_ok=False)
        code.mkdir()
        image.mkdir()
        nonce = secrets.token_hex(16)
        (code / 'expected').write_text(nonce)
        (code / 'actual').write_text('incorrect')
        (code / 'verify.py').write_text("from pathlib import Path\nassert Path('actual').read_bytes() == Path('expected').read_bytes()\n")
        if subprocess.run([sys.executable, 'verify.py'], cwd=code, capture_output=True).returncode == 0:
            raise RuntimeError('Fixture should fail initially')
        (root / 'fixture.json').write_text(json.dumps({'value': nonce, 'test_sha256': hashlib.sha256((code / 'verify.py').read_bytes()).hexdigest(),
                                                 'image_tool': 'built-in' if args.built_in_image else 'route_images.generate_image'}))
        print('Coding prompt: Read expected, repair actual, and run verify.py. Do not modify expected or verify.py.')
        print('Follow-up in same conversation: What exact value did you read earlier? Do not access files again.')
        image_prompt = ('Use the built-in image generation tool to generate a PNG illustration and display it in index.html.'
                        if args.built_in_image else IMAGE_PROMPT)
        print('Image prompt in the separate image workspace:', image_prompt)
        return
    fixture = json.loads((root / 'fixture.json').read_text())
    if (code / 'actual').read_text() != fixture['value'] or (code / 'expected').read_text() != fixture['value'] or hashlib.sha256((code / 'verify.py').read_bytes()).hexdigest() != fixture['test_sha256']:
        raise RuntimeError('Coding fixture mismatch')
    # Check the resulting files, not arbitrary code produced by the live agent.
    pngs = [f for f in image.rglob('*.png') if f.is_file() and f.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')]
    if fixture.get('image_tool') == 'route_images.generate_image' and image / 'kite.png' not in pngs:
        raise RuntimeError('Missing Route-generated kite.png')
    if not pngs or not (image / 'index.html').is_file():
        raise RuntimeError('Missing generated PNG or page')
    print(json.dumps({'os': platform.platform(), 'client': args.client, 'model_requested': args.model,
                      'effort_requested': args.effort, 'fixture': 'passed', 'image_file': 'present',
                      'follow_up_and_rendered_page': 'require operator evidence'}))


if __name__ == '__main__':
    main()
