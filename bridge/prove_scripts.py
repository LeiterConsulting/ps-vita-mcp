"""Physical Lua edit/push/run/recovery acceptance through actual MCP stdio."""
import asyncio
import base64
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from workbench.runner import check_devloop_runtime,devloop_runtime_identity


def scene_ownership(script):
    return {key:script[key] for key in ('revision','sha256','active')}


def check_scene_ownership(status,script,owned,runtime_pin):
    """A fault may pause our scene once; another editor's revision is never adopted."""
    if owned is None:raise RuntimeError('Scene ownership is unconfirmed; cleanup skipped')
    check_devloop_runtime(status,runtime_pin);check_devloop_runtime(script,runtime_pin)
    revisions={owned['revision']}
    if script.get('faulted') and script.get('paused'):revisions.add(owned['revision']+1)
    if (script.get('revision') not in revisions or status.get('revision')!=script.get('revision') or
            script.get('sha256')!=owned['sha256'] or script.get('active')!=owned['active'] or
            (status.get('experiment')=='lua')!=owned['active']):
        raise RuntimeError('Scene ownership changed; cleanup skipped without mutation')
    return script['revision']


async def restore_owned_native(call,owned,runtime_pin):
    status,_=await call('vita_status');script,_=await call('vita_script_status')
    revision=check_scene_ownership(status,script,owned,runtime_pin)
    restored,_=await call('vita_script_control',{'action':'native','expected_revision':revision})
    check_devloop_runtime(restored,runtime_pin)
    if restored.get('revision')!=revision+1 or restored.get('active') or not restored.get('paused'):
        raise RuntimeError('Native restoration receipt differs; cleanup unconfirmed')
    return restored


async def main():
    folder=ROOT/"evidence/devloop"/("lua-live-"+datetime.now().strftime("%Y-%m-%d_%H%M%S-%f"))
    folder.mkdir(parents=True)
    report={"startedUtc":datetime.now(timezone.utc).isoformat(),"evidenceTier":"actual physical Vita through MCP stdio",
            "package":json.loads((ROOT/"dist/devloop/build-report.json").read_text())["package"],"steps":[],"passed":False,
            "humanInputAcceptance":"not inferred from these calls"}
    cleanup_allowed=False
    runtime_pin=None
    owned=None
    async with stdio_client(StdioServerParameters(command=sys.executable,args=[str(ROOT/"bridge/server.py")])) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            watermark={"revision":0,"frame":0}
            async def call(name,arguments=None):
                result=await session.call_tool(name,arguments or {})
                if result.isError: raise RuntimeError(result.content[0].text)
                data=result.structuredContent or json.loads(result.content[0].text)
                if runtime_pin is not None and name!='vita_screenshot':check_devloop_runtime(data,runtime_pin)
                assert data["revision"]>=watermark["revision"] and data["frame"]>=watermark["frame"],"acknowledged revision/frame regressed"
                watermark.update({key:data[key] for key in watermark})
                report["steps"].append({"tool":name,"arguments":{key:value for key,value in (arguments or {}).items() if key!="source"},"result":data})
                return data,result
            async def load(name,source):
                nonlocal owned
                current,_=await call("vita_status")
                script,_=await call('vita_script_status')
                revision=check_scene_ownership(current,script,owned,runtime_pin)
                owned=None # A lost mutation reply must not authorize later cleanup.
                data,_=await call("vita_load_script",{"name":name,"source":source,"expected_revision":revision})
                assert data['revision']==revision+1 and data["sha256"]==hashlib.sha256(source.encode()).hexdigest() and data["paused"] and data['active']
                owned=scene_ownership(data)
                return data
            async def control(name,action):
                nonlocal owned
                current,_=await call("vita_status")
                script,_=await call('vita_script_status')
                revision=check_scene_ownership(current,script,owned,runtime_pin)
                previous=dict(owned);owned=None
                data=(await call(name,{"action":action,"expected_revision":revision}))[0]
                assert data['revision']==revision+1,'Mutation revision differs; ownership unconfirmed'
                owned=scene_ownership(data) if name=='vita_script_control' else {**previous,'revision':data['revision']}
                return data
            async def capture(label):
                data,result=await call("vita_screenshot")
                image=next(item for item in result.content if item.type=="image"); pixels=base64.b64decode(image.data)
                path=folder/(label+".png"); path.write_bytes(pixels)
                report["steps"][-1].update(imageFile=path.name,imageSha256=hashlib.sha256(pixels).hexdigest())
                print(f"Captured {label}, frame {data['frame']}",flush=True)
            try:
                names=[tool.name for tool in (await session.list_tools()).tools]; assert len(names)==10
                initial,_=await call("vita_status"); report["initial"]=initial
                assert initial["version"]==report["package"]["version"] and initial['version'] in ('01.03','01.04'),"Install and open the exact built DevLoop candidate before Lua proof"
                runtime_pin=devloop_runtime_identity(initial,report['package'].get('buildId') if initial['version']=='01.04' else None)
                if initial['version']=='01.04':assert report['package'].get('buildId'),'Native01.04 proof requires the package build pin'
                report['runtimeIdentity']=runtime_pin
                assert initial["experiment"]=="tilt_playground","Start in native mode to avoid replacing an existing Lua experiment"
                script,_=await call('vita_script_status')
                assert script['revision']==initial['revision'] and not script['active']
                owned=scene_ownership(script)
                cleanup_allowed=True
                bounce=(ROOT/"experiments/bounce.lua").read_text(); scope=(ROOT/"experiments/input_scope.lua").read_text()
                await load("bounce",bounce); await control("vita_run_experiment","resume"); await asyncio.sleep(.4)
                await control("vita_run_experiment","pause")
                original,_=await call("vita_script_status"); assert original["updates"]>0 and original["metrics"]["seconds"]>0
                await capture("bounce-running-result")
                edited=bounce.replace("LIVE LUA PLAYGROUND","LIVE EDIT: GOLD PLAYGROUND").replace("vita.rgb(64,220,191)","vita.rgb(255,197,98)")
                await load("bounce_edit",edited); await capture("hot-reloaded")
                rolled=await control("vita_script_control","rollback")
                assert rolled["sha256"]==original["sha256"] and rolled["metrics"]["seconds"]==original["metrics"]["seconds"]
                await capture("rolled-back")
                await control("vita_script_control","restart")
                await load("input_scope",scope); await control("vita_run_experiment","resume"); await asyncio.sleep(.3)
                await control("vita_run_experiment","pause"); await call("vita_read_input"); await capture("input-scope")
                current,_=await call("vita_script_status")
                for label,source in (("syntax","return {update=function(}"),("loop","while true do end")):
                    result=await session.call_tool("vita_load_script",{"name":"bad_"+label,"source":source,"expected_revision":current["revision"]})
                    assert result.isError
                    report["steps"].append({"tool":"vita_load_script","expectedError":label,"error":result.content[0].text})
                    after,_=await call("vita_script_status")
                    assert after["sha256"]==current["sha256"] and after["revision"]==current["revision"] and not after["faulted"]
                await load("late_fault","local n=0; return {update=function() n=n+1; if n>1 then error('expected live proof fault') end end,draw=function() vita.text(44,140,1,vita.rgb(255,197,98),'Fault recovery proof') end}")
                await control("vita_run_experiment","resume"); await asyncio.sleep(.2)
                faulted,_=await call("vita_script_status"); assert faulted["faulted"] and faulted["paused"] and "expected live proof fault" in faulted["error"]
                await capture("controlled-fault")
                recovery=await control("vita_script_control","rollback"); assert not recovery["faulted"] and recovery["name"]=="input_scope"
                report["passed"]=True
            except Exception as error:
                report["error"]=str(error); print("Live Lua proof did not pass: "+str(error),flush=True)
            finally:
                if cleanup_allowed:
                    try:
                        await restore_owned_native(call,owned,runtime_pin)
                        final,_=await call("vita_status")
                        assert final["paused"] and final["experiment"]=="tilt_playground" and final["parameters"]==initial["parameters"]
                        report["final"]=final; report["restoredNativePaused"]=True
                    except Exception as error:
                        report["cleanupError"]=str(error);report['restoredNativePaused']=False;report['cleanup']='skipped or unconfirmed; no mutation replay';report["passed"]=False
                report["completedUtc"]=datetime.now(timezone.utc).isoformat()
                (folder/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(("PASS live Lua hot reload, screenshots, rejection, metrics and rollback" if report["passed"] else "FAIL live Lua proof")+"; report: "+str(folder/"report.json"))
    return 0 if report["passed"] else 1


if __name__=="__main__": sys.exit(asyncio.run(main()))
