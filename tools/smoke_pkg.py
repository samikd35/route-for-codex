"""Exercise the binary in a macOS installer without touching the installed profile."""
import asyncio
import os
from pathlib import Path
import subprocess
import sys
import tempfile


with tempfile.TemporaryDirectory() as d:
    dest = Path(d) / 'expanded'
    subprocess.run(['pkgutil', '--expand-full', sys.argv[1], str(dest)], check=True)
    exe, = dest.glob('**/Route.app/Contents/MacOS/route')
    command, = dest.glob('**/usr/local/bin/route-for-codex')
    assert os.readlink(command) == '/Applications/Route.app/Contents/MacOS/route'
    assert not (command.parent / 'route').is_symlink()
    env = dict(os.environ, ROUTE_HOME=d, CODEX_HOME=d)
    assert subprocess.check_output([exe, 'status'], env=env, text=True).strip() == 'Disconnected.'
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def check_image_tool():
        params = StdioServerParameters(command=str(exe), args=['--home', d, 'images-mcp'], env=env)
        async with asyncio.timeout(45), stdio_client(params) as streams, ClientSession(*streams) as client:
            await client.initialize()
            assert [tool.name for tool in (await client.list_tools()).tools] == ['generate_image']
            result = await client.call_tool('generate_image', {'prompt': 'probe'})
            assert result.isError and 'Route is stopped' in result.content[0].text
    asyncio.run(check_image_tool())
    print('Packaged Route Images stdio command passed discovery and stopped-relay handling.')
    caddy, = dest.glob('**/Frameworks/route/bin/caddy')
    print(subprocess.check_output([caddy, 'version'], text=True).strip())
