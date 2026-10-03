"""Collect bounded live control proof through the actual registered resident MCP entry point."""
import argparse
import asyncio
import base64
from datetime import datetime,timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import sys
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'resident'))
from prove_device import describe_error

async def call(session,name,args):
    result=await session.call_tool(name,args)
    if result.isError: raise RuntimeError(result.content[0].text)
    return result,result.structuredContent or json.loads(next(item.text for item in result.content if item.type=='text'))

async def prove(args):
    config=json.loads((ROOT/'.devloop-private/resident.json').read_text(encoding='utf-8'))
    address=ipaddress.IPv4Address(config['host'])
    if address.is_loopback or not address.is_private or config['port']!=17866: raise ValueError('Live proof requires the paired LAN device')
    build=json.loads((ROOT/'dist/control/build-report.json').read_text(encoding='utf-8'))
    folder=ROOT/'evidence/control'/('live-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));folder.mkdir()
    report={'started_utc':datetime.now(timezone.utc).isoformat(),'user_reported_foreground':args.label,'expected_build_id':build['build_id'],'device_endpoint':str(address)+':17867','device_mutation':args.files,'status_samples':[],'screens':[],'result':'pending','physical_acceptance':'visible image and actual app response require image/human assessment'}
    try:
        async with stdio_client(StdioServerParameters(command=sys.executable,args=[str(ROOT/'resident/bridge.py')])) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                for i in range(3):
                    _,status=await call(session,'vita_control_status',{})
                    report['status_samples'].append(status)
                    if status['build_id']!=build['build_id'] or status.get('port')!=17867 or status.get('keep_awake') is not False: raise ValueError('Unexpected live control build or capabilities')
                    result,metadata=await call(session,'vita_control_screen',{'detail':False})
                    if metadata['sequence']<=report['screens'][-1]['sequence'] if report['screens'] else False: raise ValueError('Frame sequence did not advance')
                    images=[item for item in result.content if item.type=='image']
                    if len(images)!=1: raise ValueError('Expected one screen image')
                    png=base64.b64decode(images[0].data,validate=True)
                    if hashlib.sha256(png).hexdigest()!=metadata['png_sha256']: raise ValueError('Screen image hash differs')
                    path=folder/f'preview-{i+1}.png';path.write_bytes(png);report['screens'].append({**metadata,'local_image':str(path)})
                    await asyncio.sleep(.25)
                result,metadata=await call(session,'vita_control_screen',{'detail':True})
                png=base64.b64decode(next(item.data for item in result.content if item.type=='image'),validate=True)
                if hashlib.sha256(png).hexdigest()!=metadata['png_sha256']: raise ValueError('Detail image hash differs')
                path=folder/'detail.png';path.write_bytes(png);report['detail_screen']={**metadata,'local_image':str(path)}
                if args.files:
                    _,receipt=await call(session,'vita_control_write_text',{'name':'proof.txt','text':'Vita Control live file proof\n'})
                    report['workspace_write']=receipt
                    _,readback=await call(session,'vita_control_read_text',{'attempt':receipt['attempt'],'name':receipt['name'],'expected_sha256':receipt['sha256']})
                    if readback['text']!='Vita Control live file proof\n': raise ValueError('Workspace content differs')
                    report['workspace_read']=readback
                    _,info=await call(session,'vita_control_file_info',{'attempt':receipt['attempt'],'name':receipt['name']})
                    if info['sha256']!=receipt['sha256'] or info['bytes']!=receipt['bytes']: raise ValueError('On-device workspace hash differs')
                    report['workspace_info']=info
                _,after=await call(session,'vita_control_status',{})
                if after['build_id']!=build['build_id'] or after.get('lease_remaining_ms')!=0: raise ValueError('Control identity changed or unexpected input is active')
                report['after']=after;report['result']='passed device MCP checks; image/input acceptance separate'
    except Exception as error:
        report['result']='failed or interrupted live MCP checks';report['error']=describe_error(error);raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat();(folder/'proof.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'result':report['result'],'evidence':str(folder/'proof.json')},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--label',choices=['livearea','devloop','quake','after-return','after-wake'],required=True);parser.add_argument('--files',action='store_true')
    try: asyncio.run(prove(parser.parse_args()))
    except Exception as error: print(describe_error(error),file=sys.stderr);raise SystemExit(1)
