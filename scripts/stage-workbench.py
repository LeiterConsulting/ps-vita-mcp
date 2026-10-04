"""Stage exact verified candidates once through the actual Workbench MCP boundary."""
import argparse,asyncio,json,sys
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1]
async def main(selected=None):
    async with stdio_client(StdioServerParameters(command=sys.executable,args=[str(ROOT/'resident/bridge.py')])) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            for package,relative,key in [('starter','dist/control/build-report.json','starter_package'),('target','dist/workbench/build-report.json','package')]:
                if selected and package!=selected:continue
                report=json.loads((ROOT/relative).read_text())
                result=await session.call_tool('vita_workbench_stage_candidate',{'package':package,'expected_sha256':report[key]['sha256']})
                if result.isError:raise RuntimeError(result.content[0].text)
                value=result.structuredContent or json.loads(next(c.text for c in result.content if c.type=='text'))
                print(json.dumps({'package':package,'result':value['result'],'build_id':value['build_id'],'sha256':value['sha256'],'receipt':value.get('receipt'),'evidence':value['evidence_directory']}),flush=True)
                if not value['result'].startswith('verified'):break
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--package',choices=['starter','target']);args=parser.parse_args();asyncio.run(main(args.package))
