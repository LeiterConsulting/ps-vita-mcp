"""Bounded development trials. Journals precede mutations; uncertain requests are never replayed."""
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import uuid
from .session import exclusive
from .power import WorkKeeper
ROOT=Path(__file__).resolve().parents[1]
WORKDIR=Path(os.environ.get('VITA_WORKBENCH_ROOT',str(ROOT))).resolve()
def utc(): return datetime.now(timezone.utc).isoformat()
def sha(data): return hashlib.sha256(data).hexdigest()
def inside(base,relative):
    path=(base/relative).resolve()
    if base.resolve() not in path.parents or not path.is_file(): raise ValueError('Choose a regular file inside the project directory')
    return path
def profile(relative,expected_sha256,root=WORKDIR):
    base=root/'workbench/projects';path=inside(base,relative)
    raw=path.read_bytes()
    if len(raw)>16384 or sha(raw)!=expected_sha256: raise ValueError('Trial profile hash differs or exceeds 16 KiB')
    p=json.loads(raw)
    if not isinstance(p,dict) or set(p)-{'name','source','source_sha256','duration_s','warmup_s','steps','checks'}: raise ValueError('Unknown trial fields')
    if not re.fullmatch('[A-Za-z0-9_-]{1,32}',p.get('name','')): raise ValueError('Invalid experiment name')
    source=inside(path.parent,p['source']).read_bytes()
    if not 0<len(source)<=16384 or sha(source)!=p['source_sha256']: raise ValueError('Lua source hash differs or exceeds 16 KiB')
    source.decode('utf-8')
    if any(c<32 and c not in (9,10,13) for c in source): raise ValueError('Lua source contains binary controls')
    duration=p.get('duration_s',5);warmup=p.get('warmup_s',.5)
    if type(duration) not in (int,float) or not math.isfinite(duration) or not 1<=duration<=60 or type(warmup) not in (int,float) or not math.isfinite(warmup) or not .1<=warmup<=5: raise ValueError('Invalid trial duration or warmup')
    steps=p.get('steps',[]);checks=p.get('checks',[])
    if not isinstance(steps,list) or len(steps)>20 or not isinstance(checks,list) or not 1<=len(checks)<=8: raise ValueError('Trial needs 1..8 metric checks and at most 20 inputs')
    from resident.control.bridge_tools import ControlClient
    last=-1
    for step in steps:
        if not isinstance(step,dict) or set(step)-{'at_s','buttons','ttl_ms','left_stick','right_stick','front_touch','rear_touch'}: raise ValueError('Unexpected input step')
        at=step.get('at_s');values={k:v for k,v in step.items() if k!='at_s'}
        if type(at) not in (int,float) or not math.isfinite(at) or not 0<=at<duration or at<last: raise ValueError('Input schedule must be sorted and bounded')
        last=at;ControlClient.pack_input(1,**values)
    if sum(s['ttl_ms'] for s in steps)>5000: raise ValueError('Total requested input exceeds five seconds')
    for check in checks:
        if not isinstance(check,dict) or set(check)-{'metric','min','max','equals'} or not re.fullmatch('[A-Za-z0-9_]{1,31}',check.get('metric','')) or not set(check)&{'min','max','equals'}: raise ValueError('Invalid metric predicate')
        for key in set(check)-{'metric'}:
            if type(check[key]) not in (int,float) or not math.isfinite(check[key]): raise ValueError('Predicates must be finite numbers')
    return p,source.decode('utf-8'),{'profile_file':str(path),'profile_sha256':sha(raw),'source_sha256':sha(source)}
class Device:
    def __init__(self):
        sys.path.insert(0,str(ROOT/'resident'))
        sys.path.insert(0,str(ROOT/'bridge'))
        spec=importlib.util.spec_from_file_location('vita_workbench_foreground',ROOT/'bridge/server.py');self.foreground=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.foreground)
        spec=importlib.util.spec_from_file_location('vita_workbench_resident',ROOT/'resident/bridge.py');resident=importlib.util.module_from_spec(spec);spec.loader.exec_module(resident)
        from resident.control.bridge_tools import ControlClient
        self.control=ControlClient(resident.configuration);self.resident=resident
    def status(self): return self.foreground.vita_status()
    def script(self): return self.foreground.vita_script_status()
    def load(self,name,source,rev): return self.foreground.vita_load_script(name,source,rev)
    def resume(self,rev): return self.foreground.vita_run_experiment('resume',rev)
    def restore(self,action,rev): return self.foreground.vita_script_control(action,rev)
    def release(self): return self.control.release()
    def screen(self): return self.control.capture()
    def input(self,pid,values): return self.control.input(pid,**values)
    def control_status(self): return self.control.status()
    def target(self):
        config=self.resident.configuration();port=int(os.environ.get('VITA_TARGET_PORT','17868'))
        if not 1<=port<=65535:raise ValueError('Invalid target port')
        import http.client
        c=http.client.HTTPConnection(config['host'],port,timeout=7)
        try:
            c.request('GET','/status',headers={'Authorization':'Bearer '+config['token'],'Connection':'close'});r=c.getresponse();raw=r.read(4097)
            if r.status!=200 or len(raw)>4096 or r.getheader('Content-Type','').split(';')[0]!='application/json': raise RuntimeError('Target reply rejected')
            value=json.loads(raw)
            if value.get('app')!='Vita Input Target' or value.get('title_id')!='CHRS00012' or value.get('protocol')!=1 or value.get('version')!='01.00' or not re.fullmatch('[0-9a-f]{64}',value.get('build_id','')) or not re.fullmatch('[0-9a-f]{32}',value.get('run','')) or type(value.get('pid')) is not int or value['pid']<=0 or type(value.get('frame')) is not int or value['frame']<=0: raise RuntimeError('Invalid target identity')
            return value
        except (OSError,http.client.HTTPException,ValueError) as error: raise RuntimeError('Input Target is unavailable or returned invalid telemetry') from error
        finally:c.close()
class Journal:
    def __init__(self,root,kind):
        self.folder=root/'evidence/workbench'/(kind+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]);self.folder.mkdir(parents=True)
        self.report={'kind':kind,'started_utc':utc(),'result':'pending','events':[],'hardware_evidence':'only current device observations; host fixtures are reported separately'}
    def save(self):
        p=self.folder/'report.json';temp=self.folder/'report.tmp';temp.write_text(json.dumps(self.report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        # Windows readers can briefly deny replacement of an open report.
        # Retry only this local commit; device operations are never replayed.
        for attempt in range(8):
            try:
                os.replace(temp,p);break
            except PermissionError:
                if attempt==7:raise
                time.sleep(.05*(attempt+1))
    def event(self,kind,fields):
        event={'utc':utc(),'kind':kind,**fields}
        with (self.folder/'journal.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(event,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())
        self.report['events'].append(event);self.save();return event
    def mutation(self,operation,fields,call):
        self.event('mutation_intent',{'operation':operation,**fields})
        try:result=call()
        except Exception as error:
            self.event('mutation_unconfirmed',{'operation':operation,'failure_type':type(error).__name__,'replayed':False});raise
        self.event('mutation_receipt',{'operation':operation,'receipt':result});return result
def check_identity(control,expected):
    if not re.fullmatch('[0-9a-f]{64}',expected) or control['build_id']!=expected: raise RuntimeError('Control build differs from the pinned trial build')
    if control.get('lease_remaining_ms')!=0: raise RuntimeError('Another synthetic input lease is active')
def predicates(checks,metrics):
    out=[]
    for c in checks:
        v=metrics.get(c['metric']);passed=type(v) in (int,float) and math.isfinite(v)
        if passed:passed=('min' not in c or v>=c['min']) and ('max' not in c or v<=c['max']) and ('equals' not in c or v==c['equals'])
        out.append({**c,'actual':v if type(v) in (int,float) and math.isfinite(v) else None,'passed':bool(passed)})
    return out
def run_trial(relative,expected_profile_sha256,expected_control_build,device=None,root=WORKDIR):
    p,source,identity=profile(relative,expected_profile_sha256,root);d=device or Device()
    with exclusive():
        j=Journal(root,'trial');j.report.update(identity);j.report['control_build']=expected_control_build;j.save()
        owned_revision=None;mutation_started=False;initial=None;original=None;keeper=WorkKeeper(d.control,j.folder)
        try:
            control=d.control_status();check_identity(control,expected_control_build)
            initial=d.status();original=d.script();j.report['initial']=initial;j.report['original_script']=original;j.save()
            if initial.get('app')!='Vita DevLoop' or initial.get('version') not in ('01.02','01.03') or not initial.get('paused') or original.get('faulted') or original['revision']!=initial['revision']: raise RuntimeError('Trial requires healthy paused DevLoop 01.02 or 01.03')
            keeper.start(control)
            png,screen=d.screen();(j.folder/'before.png').write_bytes(png);pid=screen['target_pid'];j.report['target_pid']=pid
            mutation_started=True
            owned_revision=initial['revision']+1
            loaded=j.mutation('load_script',{'name':p['name'],'sha256':identity['source_sha256'],'expected_revision':initial['revision']},lambda:d.load(p['name'],source,initial['revision']))
            if loaded['revision']!=owned_revision:raise RuntimeError('Load revision differs')
            if loaded.get('sha256')!=identity['source_sha256'] or not loaded.get('paused') or not loaded.get('active'): raise RuntimeError('Uploaded script receipt differs')
            previous_revision=owned_revision;owned_revision+=1
            resumed=j.mutation('resume',{'expected_revision':previous_revision},lambda:d.resume(previous_revision))
            if resumed['revision']!=owned_revision:raise RuntimeError('Resume revision differs')
            time.sleep(p.get('warmup_s',.5));start=time.monotonic();deadline=start+p.get('duration_s',5);index=0;last_frame=initial['frame'];samples=[]
            while True:
                state=d.script();current=d.control_status()
                if current['build_id']!=expected_control_build or state['revision']!=owned_revision or state.get('sha256')!=identity['source_sha256'] or not state.get('active') or state.get('paused') or state.get('faulted') or state['frame']<=last_frame: raise RuntimeError('Trial lost identity, revision, progress or healthy execution')
                last_frame=state['frame'];samples.append(state);j.report['samples']=samples;j.save()
                elapsed=time.monotonic()-start
                if index<len(p.get('steps',[])) and elapsed>=p['steps'][index]['at_s']:
                    step=p['steps'][index];values={k:v for k,v in step.items() if k!='at_s'}
                    j.mutation('input',{'index':index,'target_pid':pid,'requested':values},lambda:d.input(pid,values));index+=1
                if time.monotonic()>=deadline:break
                time.sleep(.25)
            if index!=len(p.get('steps',[])): raise RuntimeError('Device latency prevented all scheduled inputs')
            time.sleep(1.05) # Observe expiry without an explicit release.
            state=d.script();current=d.control_status();j.report['expiry_observation']=current
            if state['revision']!=owned_revision or state.get('faulted') or current['build_id']!=expected_control_build or current.get('lease_remaining_ms')!=0: raise RuntimeError('Trial final identity or input expiry failed')
            png,screen=d.screen();(j.folder/'after.png').write_bytes(png);j.report['final_screen']=screen
            if screen['target_pid']!=pid:raise RuntimeError('Foreground changed during the trial')
            checks=predicates(p['checks'],state.get('metrics',{}));j.report['checks']=checks
            j.report['result']='passed' if all(c['passed'] for c in checks) else 'failed metric predicates'
        except Exception as error:
            j.report['result']='failed';j.report['failure_type']=type(error).__name__;j.report['failure']=str(error)[:240]
        finally:
            if mutation_started:
                try:j.report['final_release']=j.mutation('release',{},d.release)
                except Exception:j.report['final_release']='unconfirmed; kernel lease bounds remain in force'
                try:
                    state=d.script()
                    # Ownership must survive revision/hash inspection, including a lost load reply.
                    expected_revisions={owned_revision}
                    if state.get('faulted') and state.get('paused'):expected_revisions.add(owned_revision+1)
                    if state.get('sha256')!=identity['source_sha256'] or state['revision'] not in expected_revisions:raise RuntimeError('Restoration skipped because experiment ownership changed')
                    action='rollback' if original.get('loaded') else 'native'
                    restored=j.mutation('restore_'+action,{'expected_revision':state['revision']},lambda:d.restore(action,state['revision']))
                    if original.get('loaded') and restored.get('sha256')!=original.get('sha256'):raise RuntimeError('Rollback hash differs')
                    if not original.get('active') and action=='rollback':restored=j.mutation('restore_native',{'expected_revision':restored['revision']},lambda:d.restore('native',restored['revision']))
                    final=d.status();j.report['restored']=final
                    if not final.get('paused') or final.get('parameters')!=initial.get('parameters') or final.get('ball')!=initial.get('ball') or final.get('added_obstacles')!=initial.get('added_obstacles') or final.get('score')!=initial.get('score'):raise RuntimeError('Native scene or physics restoration differs')
                    j.report['restoration']='passed; previous mode paused'
                except Exception as error:j.report['restoration']='unconfirmed: '+str(error)[:200];j.report['result']='failed'
            j.report['work_power']=keeper.stop();j.report['finished_utc']=utc();j.save()
        return {**j.report,'evidence_directory':str(j.folder)}
