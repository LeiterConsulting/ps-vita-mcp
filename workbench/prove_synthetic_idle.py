"""Prove emulated controls do not brighten an idle screen during MCP work.

Uses the normal 30-second idle policy so ordinary Control requests cannot
replace the test policy. Physical interaction makes this test fail truthfully.
"""
import asyncio,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from workbench.prove_power import value
from workbench.runner import Journal,check_identity,utc

async def prove():
    control_build=json.loads((ROOT/'dist/control/build-report.json').read_text())['build_id']
    target_build=json.loads((ROOT/'dist/workbench/build-report.json').read_text())['build_id']
    j=Journal(ROOT,'synthetic-idle');j.report.update(control_build=control_build,target_build=target_build)
    checks=[];renewed=0;submitted=False;original=None
    async with stdio_client(StdioServerParameters(command=sys.executable,args=[str(ROOT/'resident/bridge.py')])) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            async def call(name,args=None):return value(await session.call_tool(name,args or {}))
            async def lease(ttl):
                nonlocal renewed
                j.event('mutation_intent',{'operation':'work_lease','ttl_ms':ttl})
                receipt=await call('vita_workbench_work_lease',{'ttl_ms':ttl})
                j.event('mutation_receipt',{'operation':'work_lease','receipt':receipt});renewed=time.monotonic();return receipt
            async def observe():
                if time.monotonic()-renewed>=10:await lease(30000)
                p=await call('vita_workbench_power_status');j.report.setdefault('samples',[]).append({'utc':utc(),**p});j.save();return p
            try:
                check_identity(await call('vita_control_status'),control_build)
                target=await call('vita_workbench_target_status');screen=await call('vita_control_screen')
                if target['build_id']!=target_build or screen['target_pid']!=target['pid']:raise RuntimeError('Target identity or foreground differs')
                # Screen observation owns a temporary automatic work lease; end it
                # before starting the independently bounded observation.
                await lease(0);submitted=True;await lease(30000)
                deadline=time.monotonic()+45;dim=None
                while time.monotonic()<deadline:
                    p=await observe()
                    if original is None and p.get('motion_fresh') and not p['dimmed'] and p['brightness']>21:original=p['brightness']
                    if original and p['dimmed'] and p['lease_remaining_ms']>0 and p.get('motion_fresh'):dim=p;break
                    await asyncio.sleep(.25)
                if dim is None:raise RuntimeError('Idle dim not reached; physical activity or unavailable motion may confound this observation')
                j.report.update(target=target,dimmed_before_inputs=dim,original_brightness=original)
                requests=[{'buttons':['l'],'ttl_ms':500},{'buttons':['r'],'ttl_ms':500},
                          {'buttons':['right','cross'],'ttl_ms':500,'left_stick':[64,192],'right_stick':[192,64],'front_touch':[700,400],'rear_touch':[1300,700]}]
                for requested,mask in zip(requests,[256,512,16416]):
                    before=await observe()
                    j.event('mutation_intent',{'operation':'synthetic_input','target_pid':target['pid'],'requested':requested})
                    receipt=await call('vita_control_input',{'target_pid':target['pid'],**requested});j.event('mutation_receipt',{'operation':'synthetic_input','receipt':receipt})
                    during=await observe();await asyncio.sleep(.6)
                    readback=await call('vita_workbench_target_status');after=await observe();control=await call('vita_control_status')
                    same_target=readback['build_id']==target_build and readback['pid']==target['pid'] and readback['run']==target['run']
                    samples=[before,during,after]
                    passed=same_target and readback['last_buttons']==mask and readback['buttons']==0 and all(p['dimmed'] and p['lease_remaining_ms']>0 and p.get('motion_fresh') and abs(p['brightness']-dim['brightness'])<=64 and p['idle_elapsed_ms']>=dim['idle_elapsed_ms'] for p in samples) and control['build_id']==control_build and control['lease_remaining_ms']==0 and control['last_release_reason']==1
                    checks.append({'gate':'synthetic mask '+str(mask)+' leaves idle dim intact','passed':bool(passed),'target_readback':readback,'before':before,'during':during,'after':after,'expiry':control});j.save()
                    if not passed:raise RuntimeError('Synthetic delivery or idle filtering failed; inspect physical activity and readbacks')
                j.report['result']='passed synthetic input delivery without idle reset or brightness restoration'
            except Exception as error:j.report.update(result='failed or interrupted',failure_type=type(error).__name__,failure=str(error)[:240])
            finally:
                if submitted:
                    try:
                        j.report['end_work']=await lease(0);await asyncio.sleep(.2);cleanup=await call('vita_workbench_power_status');j.report['cleanup_power']=cleanup
                        if cleanup['lease_remaining_ms'] or cleanup['dimmed'] or original and abs(cleanup['brightness']-original)>max(64,original//100):j.report.update(result='failed cleanup',failure='Work lease or brightness did not restore')
                    except Exception:j.report.update(result='cleanup unconfirmed',cleanup='last accepted work lease expires within 30 seconds')
                j.report['checks']=checks;j.report['finished_utc']=utc();j.save()
    print(json.dumps({'result':j.report['result'],'checks':[{'gate':c['gate'],'passed':c['passed']} for c in checks],'evidence':str(j.folder/'report.json')},indent=2))
if __name__=='__main__':asyncio.run(prove())
