"""Call the combined Resident/Control MCP server without exposing image base64."""
import argparse
import asyncio
import base64
import json
from pathlib import Path
import sys
import uuid
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]

async def main(args):
    async with stdio_client(StdioServerParameters(command=sys.executable, args=[str(ROOT / 'resident/bridge.py')])) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            if args.tool == 'list':
                result = await session.list_tools()
                print(json.dumps({'tools': [tool.name for tool in result.tools]}, indent=2))
                return 0
            result = await session.call_tool(args.tool, json.loads(args.arguments))
            if result.isError:
                print(next(item.text for item in result.content if item.type == 'text'), file=sys.stderr)
                return 1
            data = result.structuredContent or json.loads(next(item.text for item in result.content if item.type == 'text'))
            if args.save_images:
                images = [item for item in result.content if item.type == 'image']
                if images:
                    folder = ROOT / 'evidence/control' / ('capture-' + uuid.uuid4().hex)
                    folder.mkdir(parents=True, exist_ok=False)
                    for index, item in enumerate(images):
                        if item.mimeType != 'image/png':
                            raise ValueError('Unexpected image format')
                        (folder / f'{index + 1}.png').write_bytes(base64.b64decode(item.data, validate=True))
                    (folder / 'metadata.json').write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
                    data = {**data, 'local_evidence': str(folder)}
            print(json.dumps(data, indent=2))
            return 0

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('tool', help='MCP tool name, or list')
    parser.add_argument('--arguments', default='{}')
    parser.add_argument('--save-images', action='store_true')
    raise SystemExit(asyncio.run(main(parser.parse_args())))
