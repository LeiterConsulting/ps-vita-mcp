"""Call one tool through MCP stdio; print JSON metadata, never image base64."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("tool")
parser.add_argument("--arguments", default="{}")
args = parser.parse_args()
async def main():
    async with stdio_client(StdioServerParameters(command=sys.executable,args=[str(ROOT/"bridge/server.py")])) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize(); result=await session.call_tool(args.tool,json.loads(args.arguments))
            if result.isError:
                print(result.content[0].text); return 1
            print(json.dumps(result.structuredContent or json.loads(result.content[0].text),indent=2)); return 0
if __name__ == "__main__": sys.exit(asyncio.run(main()))
