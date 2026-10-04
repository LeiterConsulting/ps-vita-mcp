"""Observe real activity restoring a dimmed screen during a bounded MCP work job."""
import argparse,asyncio,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from workbench.runner import Journal,check_identity,utc
from workbench.prove_power import value
KINDS={'motion':8,'buttons':1,'sticks':2,'front-touch':4,'rear-touch':4}
async def watch(kind,duration,idle_ms=30000):
    if kind not in KINDS or not 30<=duration<=1800:raise ValueError('Choose an activity and a 30..1800 second bounded observation')
    build=json.loads((ROOT/'dist/control/build-report.json').read_text());j=Journal(ROOT,'physical-'+kind);j.report.update(activity=kind,control_build=build['build_id'],requested_s=duration)
    if not 5000<=idle_ms<=120000:raise ValueError('Idle delay is out of bounds')
    started=time.monotonic();renewed=0;dim=None;original=None;samples=[];submitted=False;observed_at=None;was_dimmed=False;confounded=False
    async with stdio_client(StdioServerParameters(command=sys.executable,args=[str(ROOT/'resident/bridge.py')])) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            async def call(name,args={}):return value(await session.call_tool(name,args))
            async def lease(ttl,phase):
                nonlocal renewed
                j.event('mutation_intent',{'operation':'work_lease','ttl_ms':ttl,'idle_ms':idle_ms,'dim_percent':20,'phase':phase})
                try:r=await call('vita_workbench_work_lease',{'ttl_ms':ttl,'idle_ms':idle_ms,'dim_percent':20})
                except Exception as error:
                    j.event('mutation_unconfirmed',{'operation':'work_lease','phase':phase,'failure_type':type(error).__name__,'replayed':False});raise
                j.event('mutation_receipt',{'operation':'work_lease','phase':phase,'receipt':r});renewed=time.monotonic()
            try:
                control=await call('vita_control_status');check_identity(control,build['build_id']);before=await call('vita_workbench_power_status');j.report['before']=before
                if before['lease_remaining_ms'] or before['dimmed']:raise RuntimeError('Another work session is active')
                submitted=True;await lease(30000,'begin')
                while time.monotonic()-started<duration:
                    if (j.folder/'stop.requested').is_file():
                        j.report['result']='observation ended by operator; inspect device events and human report';break
                    if time.monotonic()-renewed>=10:await lease(30000,'working-heartbeat')
                    p=await call('vita_workbench_power_status');sample={'utc':utc(),**p};samples.append(sample)
                    if len(samples)>128:del samples[0]
                    with (j.folder/'samples.jsonl').open('a',encoding='utf-8') as log:log.write(json.dumps(sample)+'\n')
                    j.report['samples']=samples;j.report['sample_count']=j.report.get('sample_count',0)+1;j.report['complete_samples_log']='samples.jsonl'
                    if original is None and p.get('motion_fresh') and not p['dimmed'] and 21<p['brightness']<=65536:original=p['brightness'];j.report['original_brightness']=original
                    if original is not None and p['dimmed'] and not was_dimmed and p['lease_remaining_ms']>0:
                        dim=p;confounded=False;j.report['dimmed']=dim;j.report['phase']='ready for physical '+kind;j.save()
                        print(json.dumps({'phase':'ready for physical '+kind,'brightness':p['brightness'],'original':original,'remaining_job_s':round(duration-(time.monotonic()-started)),'evidence':str(j.folder/'report.json')}),flush=True)
                    if kind=='motion' and dim is not None and p['idle_elapsed_ms']<1200 and p['last_activity_flags']&7 and not confounded:
                        confounded=True;j.report.setdefault('other_input_during_motion',[]).append(p)
                        print(json.dumps({'phase':'physical control detected; wait for screen to dim again before tilt','flags':p['last_activity_flags'],'brightness':p['brightness']}),flush=True)
                    if observed_at is None and not confounded and dim is not None and not p['dimmed'] and p['lease_remaining_ms']>0 and p.get('motion_fresh') and p['idle_elapsed_ms']<1200 and p['last_activity_flags']&KINDS[kind] and not p['last_activity_flags']&(7 if kind=='motion' else 0) and abs(p['brightness']-original)<=max(64,original//100):
                        j.report['restored_by_activity']=p;observed_at=time.monotonic();j.report['phase']='restored; holding work session for visual assessment'
                        print(json.dumps({'phase':j.report['phase'],'brightness':p['brightness'],'hold_s':20}),flush=True)
                    if observed_at is not None and time.monotonic()-observed_at>=20:
                        j.report['result']='passed device activity/restoration readback and continued work hold; human gesture/visual confirmation required';break
                    was_dimmed=p['dimmed'];j.save();await asyncio.sleep(.25)
                else:j.report['result']='physical activity was not confirmed during the bounded observation'
            except Exception as error:j.report.update(result='failed or interrupted physical observation',failure_type=type(error).__name__,failure=str(error)[:200])
            finally:
                if submitted:
                    try:
                        await lease(0,'end');await asyncio.sleep(.15);j.report['cleanup_power']=await call('vita_workbench_power_status')
                    except Exception:j.report['cleanup']='unconfirmed; last accepted lease expires within 30 seconds'
                j.report['finished_utc']=utc();j.save()
    print(json.dumps({'result':j.report['result'],'activity':kind,'evidence':str(j.folder/'report.json')},indent=2),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('kind',choices=list(KINDS));p.add_argument('--duration',type=int,default=150);p.add_argument('--idle-ms',type=int,default=30000);a=p.parse_args();asyncio.run(watch(a.kind,a.duration,a.idle_ms))
