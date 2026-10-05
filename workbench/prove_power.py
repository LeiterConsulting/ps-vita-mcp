"""Bounded live MCP brightness/motion-readback qualification with explicit cleanup.

Leave Input Target open and the Vita still. Physical activity/wake tests are separate.
Status reads never renew the working lease, so expiry is observed independently.
"""
import asyncio,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from workbench.runner import Journal,check_identity,utc

def value(result):
    if result.isError:
        detail=' '.join(c.text for c in result.content if c.type=='text')
        raise RuntimeError('MCP operation rejected: '+detail[:1000])
    return result.structuredContent or json.loads(next(c.text for c in result.content if c.type=='text'))
async def prove():
    build=json.loads((ROOT/'dist/control/build-report.json').read_text());target=json.loads((ROOT/'dist/workbench/build-report.json').read_text())
    j=Journal(ROOT,'power-live');j.report.update(control_build=build['build_id'],target_build=target['build_id'],physical_acceptance='pending: visible dim/restore and restoration by each physical input class; Wi-Fi loss and manual sleep/wake separate')
    checks=[];samples=[];leased=False;original=None
    async with stdio_client(StdioServerParameters(command=sys.executable,args=[str(ROOT/'resident/bridge.py')])) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            async def call(name,args={}):return value(await session.call_tool(name,args))
            async def power():
                p=await call('vita_workbench_power_status');samples.append({'utc':utc(),**p});j.report['samples']=samples;j.save();return p
            async def lease(ttl,label):
                j.event('mutation_intent',{'operation':'work_lease','phase':label,'ttl_ms':ttl,'idle_ms':5000,'dim_percent':20})
                try:r=await call('vita_workbench_work_lease',{'ttl_ms':ttl,'idle_ms':5000,'dim_percent':20})
                except Exception as error:
                    j.event('mutation_unconfirmed',{'operation':'work_lease','phase':label,'failure_type':type(error).__name__,'replayed':False});raise
                j.event('mutation_receipt',{'operation':'work_lease','phase':label,'receipt':r});return r
            async def observe(predicate,seconds):
                deadline=time.monotonic()+seconds
                while True:
                    p=await power()
                    if predicate(p):return p
                    if time.monotonic()>=deadline:raise RuntimeError('Timed power observation did not reach the required state')
                    await asyncio.sleep(.2)
            try:
                control=await call('vita_control_status');check_identity(control,build['build_id'])
                if control.get('power_protocol')!=1:raise RuntimeError('Native work power protocol is absent')
                t=await call('vita_workbench_target_status')
                if t['build_id']!=target['build_id']:raise RuntimeError('Input Target build differs')
                before=await power();j.report['before']=before;j.report['target']=t
                if before['lease_remaining_ms'] or before['dimmed']:raise RuntimeError('Another working lease is active')
                leased=True;await lease(15000,'idle-dim')
                fresh=await observe(lambda p:p.get('motion_fresh') and p.get('motion_result',-1)>=0 and type(p.get('brightness')) is int and 21<p['brightness']<=65536,3)
                original=fresh['brightness'];j.report['working_baseline_brightness']=original
                tolerance=max(64,original//100);expected=max(21,original*20//100)
                checks.append({'gate':'fresh accelerometer/gyroscope readback','passed':True,'observation':fresh})
                dim=await observe(lambda p:p['dimmed'] and abs(p['brightness']-expected)<=tolerance,9)
                if dim.get('power_tick_result',-1)<0 or dim.get('brightness_result',-1)<0:raise RuntimeError('Native timer/brightness operation failed')
                checks.append({'gate':'idle dim to 20 percent during work','passed':True,'original':original,'expected':expected,'tolerance':tolerance,'observation':dim})
                await lease(0,'explicit-end')
                restored=await observe(lambda p:not p['dimmed'] and p['lease_remaining_ms']==0 and abs(p['brightness']-original)<=tolerance,3)
                checks.append({'gate':'explicit end restores runtime brightness','passed':True,'observation':restored})
                await lease(12000,'independent-expiry')
                dim=await observe(lambda p:p['dimmed'] and p['lease_remaining_ms']>0,10)
                expired=await observe(lambda p:p['lease_remaining_ms']==0 and not p['dimmed'] and abs(p['brightness']-original)<=tolerance,10)
                checks.append({'gate':'expiry restores brightness without prior end request','passed':True,'dimmed':dim,'expired':expired})
                after=await call('vita_control_status')
                if after['build_id']!=build['build_id']:raise RuntimeError('Control build changed during power checks')
                j.report['after']=after;j.report['result']='passed software/device brightness and timer readbacks; physical and visual gates pending'
            except Exception as error:
                j.report.update(result='failed or interrupted live power checks',failure_type=type(error).__name__,failure=str(error)[:200])
            finally:
                if leased:
                    try:
                        j.report['end_receipt']=await lease(0,'final-cleanup')
                        j.report['cleanup_power']=await observe(lambda p:not p['dimmed'] and not p['lease_remaining_ms'],3)
                    except Exception:j.report['cleanup']='unconfirmed; last accepted work lease remains bounded'
                j.report['checks']=checks;j.report['finished_utc']=utc();j.save()
    print(json.dumps({'result':j.report['result'],'checks':[{k:v for k,v in c.items() if k in ('gate','passed','original','expected')} for c in checks],'evidence':str(j.folder/'report.json')},indent=2))
if __name__=='__main__':asyncio.run(prove())
