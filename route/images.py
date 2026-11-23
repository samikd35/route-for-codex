"""Route's stdio image tool. Its only credential is the local relay token."""
import asyncio
import base64
import io
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4


REQUEST_SECONDS = 240
TOOL_SECONDS = REQUEST_SECONDS + 30
IMAGE_MODEL = 'gpt-image-2'
MAX_RESPONSE_BYTES = 32 * 1024 * 1024


def png_bytes(body):
    from PIL import Image

    try:
        images = json.loads(body)['data']
        if not isinstance(images, list) or len(images) != 1:
            raise ValueError
        data = base64.b64decode(images[0]['b64_json'], validate=True)
        if not data.endswith(b'\x00\x00\x00\x00IEND\xaeB\x60\x82'):
            raise ValueError
        with Image.open(io.BytesIO(data), formats=['PNG']) as image:
            if image.width * image.height > 16_777_216:
                raise ValueError
            image.verify()
        with Image.open(io.BytesIO(data), formats=['PNG']) as image:
            image.load()
    except (KeyError, TypeError, ValueError, OSError, SyntaxError, Image.DecompressionBombError):
        raise RuntimeError('The image service returned an invalid PNG. No image was saved.') from None
    return data


def save_png(directory, data):
    directory.mkdir(mode=0o700, exist_ok=True)
    target = directory / f'{uuid4().hex}.png'
    with tempfile.NamedTemporaryFile(dir=directory, suffix='.part', delete=False) as f:
        temp = Path(f.name)
        try:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
            f.close()
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
    return str(target)


async def generate(session, port, prompt):
    import httpx

    if not prompt.strip():
        raise ValueError('Provide a description of the image to generate.')
    if not session.active():
        raise RuntimeError('Route is stopped. Reconnect Route and try again.')
    try:
        token = session.credential.read_text().strip()
    except OSError:
        raise RuntimeError('Route’s local token is unavailable. Reconnect Route.') from None

    payload = {'model': IMAGE_MODEL, 'n': 1, 'prompt': prompt, 'output_format': 'png'}
    url = f'http://127.0.0.1:{port}/v1/images/generations'
    try:
        async with asyncio.timeout(REQUEST_SECONDS), httpx.AsyncClient(trust_env=False, timeout=REQUEST_SECONDS) as client:
            # No redirects, proxy environment, or automatic generation retries.
            async with client.stream('POST', url, json=payload, headers={'Authorization': 'Bearer ' + token}) as response:
                if response.status_code != 200:
                    message = {
                        400: 'OpenAI rejected the image request. Check the prompt and project model access.',
                        401: 'Authentication failed. Check the Route connection and the saved OpenAI API key.',
                        403: f'This project cannot generate images with {IMAGE_MODEL}. Check model access.',
                        404: f'Image generation is unavailable. Check access to {IMAGE_MODEL} and reconnect Route.',
                        429: 'OpenAI rejected the request for rate or quota limits. Check project usage.',
                    }.get(response.status_code, f'Image service failed (HTTP {response.status_code}).')
                    raise RuntimeError(message)
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise RuntimeError('Image response exceeded the size limit. No image was saved.')
                    body.extend(chunk)
    except (TimeoutError, httpx.TimeoutException):
        raise RuntimeError('Image generation timed out. Route did not retry the request.') from None
    except httpx.TransportError:
        raise RuntimeError('The Route connection was interrupted. Check Route status before retrying.') from None
    return save_png(session.home / 'images', png_bytes(body))


def serve(session, port):
    import sys

    from anyio import wrap_file
    from mcp import types
    from mcp.server.lowlevel import Server
    from mcp.server.stdio import stdio_server

    server = Server('Route Images')
    tool = types.Tool(name='generate_image',
                      description='Generate one PNG billed to the API key saved in Route. Returns its absolute local path.',
                      inputSchema={'type': 'object', 'properties': {'prompt': {'type': 'string', 'minLength': 1}},
                                   'required': ['prompt'], 'additionalProperties': False},
                      annotations=types.ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                                        idempotentHint=False, openWorldHint=True))

    @server.list_tools()
    async def list_tools():
        return [tool]

    @server.call_tool()
    async def call_tool(name, arguments):
        if name != tool.name:
            raise ValueError('Unknown Route image tool')
        path = await generate(session, port, arguments['prompt'])
        return [types.TextContent(type='text', text=path)]

    async def run():
        # Keep ownership of the process streams with the launcher, including frozen executables.
        sys.stdin.reconfigure(encoding='utf-8')
        sys.stdout.reconfigure(encoding='utf-8')
        async with stdio_server(wrap_file(sys.stdin), wrap_file(sys.stdout)) as streams:
            await server.run(*streams, server.create_initialization_options())

    asyncio.run(run())
