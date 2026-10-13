"""Workbench tools added to the existing Resident MCP without a separate service."""
from pathlib import Path
import json
import re
import statistics
import time
from mcp.types import ToolAnnotations
from .runner import Device,Journal,ROOT,WORKDIR,run_trial,check_identity,freeze_device_endpoints
from .session import exclusive
from .power import WorkKeeper,lease as work_lease,status as power_status
READ=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False)
WRITE=ToolAnnotations(readOnlyHint=False,destructiveHint=False,idempotentHint=False,openWorldHint=False)
def doctor(expected_control_build=None,device=None):
    d=device or Device()
    with exclusive():
        try:value=d.control_status()
        except Exception:
            return {'control':'unavailable; run the installed Control Starter once after a normal reboot','resident':d.resident.vita_resident_status(),'ready_for_lua_trial':False,'ready_for_script_reload':False,'ready_for_input_trial':False,'ready_for_target_trial':False}
        if expected_control_build:check_identity(value,expected_control_build)
        result={'control':value,'ready_for_lua_trial':False,'ready_for_script_reload':False,'ready_for_input_trial':False,'ready_for_target_trial':False,'input_target_verification':'not observed; use prepare_devloop before an input trial','native_installation':'manual VPK installation and normal reboot; runtime Starter once per boot','work_power':'temporary 30-second lease during active jobs; dims after 30 seconds without device activity, including motion'}
        try:
            foreground=d.status();script=d.script();result['devloop']=foreground;result['script']=script
            result['ready_for_script_reload']=foreground.get('version') in ('01.02','01.03','01.04') and foreground.get('paused') and not script.get('faulted') and not value.get('lease_remaining_ms') and script['revision']==foreground['revision']
        except Exception:result['devloop']='unavailable; leave the foreground DevLoop app open'
        try:result['target']=d.target();result['ready_for_target_trial']=value.get('version') in ('0.3.0','0.3.1','0.3.2','0.3.3','0.3.4') and not value.get('lease_remaining_ms')
        except Exception:result['target']='unavailable; install/open the Input Target for device input qualification'
        return result
def soak(seconds,expected_control_build,device=None,root=WORKDIR):
    if type(seconds) is not int or not 10<=seconds<=3600:raise ValueError('Soak duration must be 10..3600 seconds')
    d=device or Device()
    with exclusive():
        j=Journal(root,'soak');j.report['control_build']=expected_control_build;j.report['requested_s']=seconds;j.save()
        start=time.monotonic();last_uptime=None;last_sequence=None;times=[];samples=[];keeper=WorkKeeper(d.control,j.folder)
        try:
            freeze_device_endpoints(d)
            initial=d.control_status();check_identity(initial,expected_control_build)
            keeper.start(initial)
            while time.monotonic()-start<seconds:
                sample=d.control_status();check_identity(sample,expected_control_build)
                if last_uptime is not None and sample['uptime_ms']<last_uptime:raise RuntimeError('Control restarted during the soak')
                last_uptime=sample['uptime_ms'];png,screen=d.screen()
                if last_sequence is not None and screen['sequence']<=last_sequence:raise RuntimeError('Capture sequence stopped progressing')
                last_sequence=screen['sequence'];times.append(screen['bridge']['round_trip_ms']);samples.append({'control':sample,'screen':screen});j.report['samples']=samples
                if len(samples)==1 or len(samples)%30==0:(j.folder/f'screen-{len(samples):04d}.png').write_bytes(png)
                j.save();time.sleep(min(1,max(0,seconds-(time.monotonic()-start))))
            j.report['result']='passed';j.report['elapsed_s']=round(time.monotonic()-start,3)
        except Exception as error:j.report['result']='failed';j.report['failure_type']=type(error).__name__;j.report['failure']=str(error)[:240]
        finally:
            j.report['work_power']=keeper.stop()
            ordered=sorted(times)
            if times:j.report['screen_roundtrip_ms']={'samples':len(times),'median':statistics.median(times),'p95':ordered[min(len(ordered)-1,int(len(ordered)*.95))],'max':max(times)}
            j.report['finished_utc']=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat();j.save()
        return {**j.report,'evidence_directory':str(j.folder)}
def read_report(relative,root=WORKDIR):
    base=(root/'evidence/workbench').resolve();path=(base/relative).resolve()
    if base not in path.parents or path.name!='report.json' or not path.is_file() or path.stat().st_size>2*1024*1024:raise ValueError('Choose a Workbench report.json under the evidence directory')
    return json.loads(path.read_text())
def register(mcp):
    from .script_session import run_session
    from resident.launch_client import prepare_script_session
    from .prepare import prepare
    from .qualify_target import qualify
    from .candidates import stage
    from .verify_file import verify
    from typing import Literal
    @mcp.tool(annotations=WRITE)
    def vita_workbench_prepare_script_session(expected_devloop_build:str,allow_launch:bool=False,expected_resident_build:str|None=None,expected_resident_instance:str|None=None,timeout_s:int=15)->dict:
        """Prepare Control-free script work by observing healthy paused native DevLoop 01.04 twice. Requires its exact native build and returns PID/run/revision pins for script_session. Launch is disabled by default. Explicit allow_launch additionally requires an exact Resident broker build/native instance; installed Resident 0.1.4 has a disabled broker and refuses submission. The new native lifecycle path qualifies its separate lab title. Queues at most one fixed-title attempt, reconciles lost replies with GET only, then checks actual DevLoop build/session. No input, power, installation or scene mutation; polling 2..60 seconds plus socket deadlines."""
        return prepare_script_session(expected_devloop_build,allow_launch=allow_launch,expected_resident_build=expected_resident_build,expected_resident_instance=expected_resident_instance,timeout_s=timeout_s)
    @mcp.tool(annotations=WRITE)
    def vita_workbench_script_session(candidates:list[dict],expected_devloop_build:str,expected_pid:int,expected_run:str,expected_revision:int,retain_best:bool=False,selection:dict|None=None)->dict:
        """Autonomously deploy/run/measure/evaluate 1..8 SHA-pinned inline Lua candidates in already-open paused DevLoop 01.04. Pin exact native build/PID/run/revision; no Control required. Aggregate measurement <=120s plus HTTP deadlines. Restores original scene paused between candidates; optional retain_best reloads the chosen passing source paused. Holds the shared local lock, freezes endpoints and journals mutations. Uncertain writes or changed ownership stop without replay or unowned cleanup. No remote scene lease, screenshot, input, keepawake or native installer. Returns metrics, decisions and private evidence path."""
        return run_session(candidates,expected_devloop_build,expected_pid,expected_run,expected_revision,retain_best=retain_best,selection=selection)
    @mcp.tool(annotations=WRITE)
    def vita_workbench_prepare_devloop(expected_control_build:str,expected_devloop_version:Literal['01.02','01.03','01.04']='01.04',timeout_s:int=30,expected_devloop_build:str|None=None)->dict:
        """Prepare healthy paused DevLoop: pin Control, refuse active input/work leases, launch CHRS00003 at most once if unavailable, and observe progress. Input readiness requires 01.04 native CHRS00003 PID matching captures plus expected_devloop_build from its exact package report; run/build are rechecked. Legacy and unpinned runtimes remain script-only. Journals evidence and ends temporary power. Never installs, loads modules, sends input or replaces a scene. Lost launch replies are inspected without repeating launch. Polls 2..60 seconds plus socket timeouts."""
        return prepare(expected_control_build,expected_devloop_version,timeout_s,expected_devloop_build=expected_devloop_build)
    @mcp.tool(annotations=READ)
    def vita_workbench_doctor(expected_control_build:str|None=None)->dict:
        """Inspect Control identity and paused script runtime or Input Target availability. Script readiness is distinct from synthetic input readiness; doctor does not map the foreground PID. Optional build pin rejects drift."""
        return doctor(expected_control_build)
    @mcp.tool(annotations=WRITE)
    def vita_workbench_run_trial(relative_profile:str,expected_profile_sha256:str,expected_control_build:str,expected_devloop_build:str|None=None)->dict:
        """Run one hash-pinned Lua trial: upload once, check metrics, evidence and paused restoration. Synthetic steps require 01.04 expected_devloop_build from its package report and native CHRS00003 PID matching a fresh capture before load and each input. Pins/rechecks native run/build; legacy runtimes support script-only profiles. Freezes endpoints for the job. Takes roughly 90 seconds; never replays uncertain mutations."""
        return run_trial(relative_profile,expected_profile_sha256,expected_control_build,expected_devloop_build=expected_devloop_build)
    @mcp.tool(annotations=READ)
    def vita_workbench_read_report(relative_report:str)->dict:
        """Read an existing evidence/workbench/.../report.json without contacting the Vita."""
        return read_report(relative_report)
    @mcp.tool(annotations=WRITE)
    def vita_workbench_soak(seconds:int,expected_control_build:str)->dict:
        """Perform 10..3600 seconds of status/capture checks with temporary work power leases; fail on restart, input lease, changed build or stalled captures. Stores timings and screens; physical input and sleep/wake acceptance remain separate."""
        return soak(seconds,expected_control_build)
    @mcp.tool(annotations=READ)
    def vita_workbench_target_status()->dict:
        """Read Input Target app identity, input latches, neutral-after-input frames and resume counter on port 17868."""
        with exclusive():return Device().target()
    @mcp.tool(annotations=WRITE)
    def vita_workbench_verify_file(attempt:str,name:str,expected_bytes:int,expected_sha256:str,expected_control_build:str)->dict:
        """Resolve an uncertain managed upload/copy by native hash and two full readbacks, retaining a verified PC artifact. Never rewrites or removes device files. Pins build, file identity, size and hash; keeps the awake Vita alive during the bounded job. Takes up to roughly 90 seconds; no uncertain request replay."""
        return verify(attempt,name,expected_bytes,expected_sha256,expected_control_build)
    @mcp.tool(annotations=WRITE)
    def vita_workbench_qualify_input(expected_control_build:str,expected_target_build:str)->dict:
        """Test all normal buttons, both additive sticks, both touch panels and expiry in foreground Input Target. Ends by START+SELECT self-exit and proves kernel focus cancellation without an app command or prior release; retains device evidence."""
        return qualify(expected_control_build,expected_target_build)
    @mcp.tool(annotations=WRITE)
    def vita_workbench_stage_candidate(package:Literal['starter','target'],expected_sha256:str)->dict:
        """Validate exact sources, accepted app hashes and native candidate package; publish once through boot Resident with two readbacks. Works while Control is inactive after reboot. Journals the attempt before upload. Installation and activation remain manual."""
        return stage(package,expected_sha256)
    @mcp.tool(annotations=READ)
    def vita_workbench_power_status()->dict:
        """Read temporary work lease, dimming, brightness, physical activity and motion freshness without renewing the lease."""
        with exclusive():return power_status(Device().control)
    @mcp.tool(annotations=WRITE)
    def vita_workbench_work_lease(ttl_ms:int=30000,idle_ms:int=30000,dim_percent:int=20)->dict:
        """Keep the awake Vita display alive for 5..30 seconds; 0 ends work and restores brightness. Dim after 5..120 seconds of no device activity including motion, to 5..50 percent of current brightness. Renew while doing work; heartbeats do not reset inactivity. Does not force-wake the Vita or change saved settings."""
        with exclusive():return work_lease(Device().control,ttl_ms,idle_ms,dim_percent)
