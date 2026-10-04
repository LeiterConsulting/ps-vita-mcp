"""Run separate, hash-pinned device gates through a fresh actual stdio MCP."""
import argparse
import asyncio
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from workbench.prove_power import value
from workbench.runner import Journal,check_identity,utc

PROFILES={'smoke':'b3c5eb6d4dde5f276563ae531931dd1029cdd53c0ba13825359ffe1dfe868039',
          'input':'2032c2c48ad0dba7feeca9000e2852ba90185233d9736eaf200483ca57704173'}

async def prove(phase,seconds):
    control=json.loads((ROOT/'dist/control/build-report.json').read_text())['build_id']
    target=json.loads((ROOT/'dist/workbench/build-report.json').read_text())['build_id']
    j=Journal(ROOT,'integration-'+phase)
    j.report.update(control_build=control,target_build=target,boundary='fresh actual stdio MCP to live hardware')
    async with stdio_client(StdioServerParameters(command=sys.executable,args=[str(ROOT/'resident/bridge.py')])) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            async def call(name,args=None,mutation=False,timeout=90):
                args=args or {}
                if mutation:j.event('mutation_intent',{'operation':name,'arguments':args})
                try:
                    response=await session.call_tool(name,args,read_timeout_seconds=timedelta(seconds=timeout))
                    if response.isError:j.event('mcp_rejection',{'operation':name,'detail':' '.join(c.text for c in response.content if c.type=='text')[:1200]})
                    r=value(response)
                except Exception as error:
                    if mutation:j.event('mutation_unconfirmed',{'operation':name,'failure_type':type(error).__name__,'replayed':False})
                    raise
                if mutation:j.event('mutation_receipt',{'operation':name,'receipt':r})
                return r
            try:
                check_identity(await call('vita_control_status'),control)
                if phase=='input':
                    r=await call('vita_workbench_qualify_input',{'expected_control_build':control,'expected_target_build':target},True)
                    j.report['qualification']=r
                    if r['result']!='passed':raise RuntimeError('Input qualification failed: '+r.get('failure','inspect its report'))
                elif phase=='files':
                    payload=bytes(range(256))*4096;digest=hashlib.sha256(payload).hexdigest()
                    local=ROOT/'outgoing'/('control-probe-'+uuid.uuid4().hex+'.bin');local.parent.mkdir(exist_ok=True);local.write_bytes(payload)
                    j.report['local_fixture']={'path':str(local),'bytes':len(payload),'sha256':digest}
                    published=await call('vita_control_publish_file',{'relative_file':local.name,'expected_sha256':digest},True)
                    j.report['published']=published
                    if published['sha256']!=digest or published['bytes']!=len(payload) or published['read_back_checks']!=2:raise RuntimeError('Publication proof differs')
                    identity={'attempt':published['attempt'],'name':published['name']}
                    info=await call('vita_control_file_info',identity);j.report['native_file_info']=info
                    if info['sha256']!=digest or info['bytes']!=len(payload):raise RuntimeError('Native file hash differs')
                    copied=await call('vita_control_copy_file',{**identity,'expected_sha256':digest,'new_name':'verified-copy.bin'},True)
                    j.report['copied']=copied
                    if copied['sha256']!=digest or copied['read_back_checks']!=2:raise RuntimeError('Copy proof differs')
                    copy_identity={'attempt':copied['attempt'],'name':copied['name']}
                    j.report['removed_owned_copy']=await call('vita_control_delete_file',{**copy_identity,'expected_sha256':digest},True)
                    j.report['retained_original']=await call('vita_control_file_info',identity)
                    if j.report['retained_original']['sha256']!=digest:raise RuntimeError('Original fixture changed')
                elif phase=='trials':
                    j.report['launch']=await call('vita_control_app',{'action':'launch','title_id':'CHRS00003'},True)
                    await asyncio.sleep(1)
                    ready=await call('vita_workbench_doctor',{'expected_control_build':control})
                    j.report['doctor']=ready
                    if not ready['ready_for_lua_trial']:raise RuntimeError('DevLoop is not healthy and paused; launch is not replayed')
                    j.report['trials']=[]
                    for name,digest in PROFILES.items():
                        r=await call('vita_workbench_run_trial',{'relative_profile':name+'/trial.json','expected_profile_sha256':digest,'expected_control_build':control},True)
                        j.report['trials'].append(r);j.save()
                        print(json.dumps({'phase':name,'result':r['result'],'restoration':r.get('restoration'),'evidence':r['evidence_directory']}),flush=True)
                        if r['result']!='passed' or not r.get('restoration','').startswith('passed'):raise RuntimeError('Lua trial failed: '+r.get('failure','inspect its report'))
                elif phase=='soak':
                    r=await call('vita_workbench_soak',{'seconds':seconds,'expected_control_build':control},True,seconds+60)
                    j.report['soak']=r
                    if r['result']!='passed':raise RuntimeError('Capture soak failed: '+r.get('failure','inspect its report'))
                j.report['result']='passed'
            except Exception as error:
                j.report.update(result='failed',failure_type=type(error).__name__,failure=str(error)[:240])
            finally:
                if phase in ('files','trials'):
                    try:j.report['end_work']=await call('vita_workbench_work_lease',{'ttl_ms':0},True)
                    except Exception:j.report['end_work']='unconfirmed; last accepted lease expires within 30 seconds'
                j.report['finished_utc']=utc();j.save()
    summary={'phase':phase,'result':j.report['result'],'failure':j.report.get('failure'),'evidence':str(j.folder/'report.json')}
    if phase=='input':summary['checks']=[{'gate':c['gate'],'passed':c['passed']} for c in j.report.get('qualification',{}).get('checks',[])]
    if phase=='soak':summary['screen_roundtrip_ms']=j.report.get('soak',{}).get('screen_roundtrip_ms')
    print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['input','files','trials','soak']);parser.add_argument('--seconds',type=int,default=120)
    args=parser.parse_args()
    if not 10<=args.seconds<=3600:parser.error('Soak needs 10..3600 seconds')
    asyncio.run(prove(args.phase,args.seconds))
