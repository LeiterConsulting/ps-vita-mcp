"""Actual Workbench MCP/HTTP flow; Vita adapters are simulated, never hardware acceptance."""
import asyncio,hashlib,json,os,struct,sys,tempfile,threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import parse_qs
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1];TOKEN='d'*32;BUILD='a'*64
FILE=bytes(range(256))*4096;FILE_ID='c'*32+'/probe.bin';FILE_HASH=hashlib.sha256(FILE).hexdigest()
state={};script={};previous={};calls=[];fault='';frames=100;sequence=0;work_ttl=0
def reset(mode=''):
    global state,script,previous,calls,fault,frames,work_ttl
    state={'protocol':1,'app':'Vita DevLoop','version':'01.02','revision':1,'frame':100,'sampled_ms':1234,'paused':True,'parameters':{'gravity':620},'ball':{'x':100,'y':200},'added_obstacles':2,'score':0}
    script={'loaded':False,'active':False,'faulted':False,'name':'','sha256':'','source_bytes':0,'metrics':{}}
    previous={};calls=[];fault=mode;frames=100;work_ttl=0
def power_value():return {'app':'Vita Work Power','abi':2,'lease_remaining_ms':work_ttl,'dimmed':False,'brightness':50000,'motion_fresh':True}
class Fixture(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,code,value,mime='application/json'):
        raw=value if isinstance(value,bytes) else json.dumps(value).encode();self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        global frames,sequence
        calls.append(('GET',self.path));frames+=1;state['frame']=frames
        if self.headers.get('Authorization')!='Bearer '+TOKEN:return self.reply(401,{})
        if self.path=='/status' and self.server.role=='control':return self.reply(200,{'app':'Vita Control','version':'0.3.3','abi':2,'build_id':'b'*64 if fault=='wrong_build' else BUILD,'capture_codecs':['rgb'],'uptime_ms':frames*10,'lease_remaining_ms':0,'power_protocol':1})
        if self.path=='/power/status':return self.reply(200,power_value())
        if self.path=='/workspace/stat/'+FILE_ID:return self.reply(200,{'vita_path':'ux0:data/vita-control/workspace/'+FILE_ID,'bytes':len(FILE),'sha256':'0'*64 if fault=='file_native_hash' else FILE_HASH})
        if self.path=='/workspace/read/'+FILE_ID:return self.reply(200,FILE[:-1] if fault=='file_readback' else FILE,'application/octet-stream')
        if self.path.startswith('/screen/'):
            sequence+=1;pid=88 if fault=='focus' and script['loaded'] else 77
            raw=bytes([20,40,60])*240*136;header=struct.pack('<6Ii5I2Q',0x31465256,2,sequence,240,136,len(raw),pid,frames,960,544,1,0,100,200)
            return self.reply(200,header+raw,'application/x-vita-rgb')
        if self.path=='/script':
            if fault=='revision' and script['loaded'] and not state['paused']:state['revision']+=10
            if script['loaded']:script['metrics']={'frames':0 if fault=='metric' else 120,'seconds':3}
            return self.reply(200,{**state,**script})
        return self.reply(200,state)
    def do_POST(self):
        global previous,work_ttl
        data=self.rfile.read(int(self.headers.get('Content-Length',0)));calls.append(('POST',self.path))
        if self.path=='/power/lease':
            magic,abi,ttl,idle,percent=struct.unpack('<5I',data)
            if magic!=0x31505756 or abi!=2 or ttl!=0 and not 5000<=ttl<=30000 or not 5000<=idle<=120000 or not 5<=percent<=50:return self.reply(400,{})
            work_ttl=ttl
            if fault=='lost_power':self.close_connection=True;return
            return self.reply(200,power_value())
        if self.server.role=='control':return self.reply(200,{'lease_remaining_ms':0,'build_id':BUILD})
        if self.path=='/script':
            if int(self.headers['X-DevLoop-Revision'])!=state['revision']:return self.reply(409,{})
            previous=dict(script);script.update(loaded=True,active=True,name=self.headers['X-DevLoop-Script-Name'],sha256=hashlib.sha256(data).hexdigest(),source_bytes=len(data));state['paused']=True;state['revision']+=1
            if fault=='lost_load':self.close_connection=True;return
            return self.reply(200,{**state,**script})
        form=parse_qs(data.decode());action=form['action'][0]
        if int(form['expected_revision'][0])!=state['revision']:return self.reply(409,{})
        if fault=='restore' and action=='native':return self.reply(409,{})
        if action=='native':script['active']=False
        if action=='script_rollback':script.update(previous)
        state['paused']=action!='resume';state['revision']+=1
        if fault=='lost_resume' and action=='resume':self.close_connection=True;return
        return self.reply(200,{**state,**script} if action=='native' or action.startswith('script_') else state)
def value(result):return result.structuredContent or json.loads(next(x.text for x in result.content if x.type=='text'))
async def main():
    servers=[]
    for role in ['control','devloop']:
        s=ThreadingHTTPServer(('127.0.0.1',0),Fixture);s.role=role;threading.Thread(target=s.serve_forever,daemon=True).start();servers.append(s)
    with tempfile.TemporaryDirectory() as name:
        root=Path(name);project=root/'workbench/projects/probe';project.mkdir(parents=True)
        source=b'return {update=function() end,draw=function() end}'
        (project/'main.lua').write_bytes(source);p={'name':'probe','source':'main.lua','source_sha256':hashlib.sha256(source).hexdigest(),'duration_s':1,'warmup_s':.1,'steps':[],'checks':[{'metric':'frames','min':60}]};raw=json.dumps(p).encode();(project/'trial.json').write_bytes(raw)
        args={'relative_profile':'probe/trial.json','expected_profile_sha256':hashlib.sha256(raw).hexdigest(),'expected_control_build':BUILD}
        resident=root/'resident.json';devloop=root/'devloop.json'
        resident.write_text(json.dumps({'host':'127.0.0.1','port':servers[0].server_port-1,'token':TOKEN}));devloop.write_text(json.dumps({'host':'127.0.0.1','port':servers[1].server_port,'token':TOKEN}))
        env={**os.environ,'VITA_RESIDENT_CONFIG':str(resident),'VITA_CONTROL_PORT':str(servers[0].server_port),'VITA_DEVLOOP_CONFIG':str(devloop),'VITA_WORKBENCH_ROOT':str(root),'VITA_WORKBENCH_LOCK':str(root/'session.lock')}
        from workbench.prove_device import PROFILES
        from workbench.runner import profile
        for name,digest in PROFILES.items():profile(name+'/trial.json',digest,root=ROOT)
        checks=['checked-in-profile-and-source-hashes-match-public-helper'];reset()
        async with stdio_client(StdioServerParameters(command=sys.executable,args=[str(ROOT/'resident/bridge.py')],env=env)) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize();catalog=await session.list_tools();assert len([t for t in catalog.tools if t.name.startswith('vita_workbench_')])==10;checks.append('ten-workbench-tools-through-MCP')
                file_args={'attempt':'c'*32,'name':'probe.bin','expected_bytes':len(FILE),'expected_sha256':FILE_HASH,'expected_control_build':BUILD}
                for bad in [{'attempt':'../escape'},{'name':'../escape'},{'expected_bytes':8388609},{'expected_sha256':'0'}]:
                    reset();assert (await session.call_tool('vita_workbench_verify_file',{**file_args,**bad})).isError;assert not calls
                checks.append('file-observation-identity-bounds-refused-before-network')
                for mode in ['', 'file_native_hash','file_readback']:
                    reset(mode);r=await session.call_tool('vita_workbench_verify_file',file_args);assert not r.isError;r=value(r)
                    assert r['device_file_mutations']==0 and not any(m=='POST' and p!='/power/lease' for m,p in calls)
                    if not mode:
                        assert r['result']=='passed' and r['read_back_checks']==2 and Path(r['local_artifact']).read_bytes()==FILE and work_ttl==0
                        assert calls.count(('GET','/workspace/read/'+FILE_ID))==2
                    else:
                        assert r['result']=='failed';assert calls.count(('GET','/workspace/read/'+FILE_ID))==(1 if mode=='file_readback' else 0)
                    checks.append(mode or 'file-native-hash-two-readbacks-local-artifact-no-device-rewrite')
                for args_power in [{'ttl_ms':4999},{'dim_percent':0},{'idle_ms':120001}]:
                    reset();assert (await session.call_tool('vita_workbench_work_lease',args_power)).isError;assert not calls
                checks.append('power-policy-invalid-values-refused-before-network')
                reset();r=await session.call_tool('vita_workbench_work_lease',{});assert not r.isError and value(r)['lease_remaining_ms']==30000
                assert value(await session.call_tool('vita_workbench_power_status',{}))['lease_remaining_ms']==30000
                assert not (await session.call_tool('vita_workbench_work_lease',{'ttl_ms':0})).isError and work_ttl==0
                checks.append('power-start-read-end-through-MCP')
                reset('lost_power');r=await session.call_tool('vita_workbench_run_trial',args);report=value(r)
                assert report['result']=='failed' and calls.count(('POST','/power/lease'))==1 and not any(p=='/script' for m,p in calls if m=='POST')
                power_events=[json.loads(line) for line in (Path(report['evidence_directory'])/'power.jsonl').read_text().splitlines()]
                assert power_events[-1]['kind']=='lease_unconfirmed' and not power_events[-1]['replayed'];checks.append('uncertain-power-lease-never-replayed')
                for mode in ['', 'wrong_build','lost_load','lost_resume','metric','revision','focus','restore']:
                    reset(mode);r=await session.call_tool('vita_workbench_run_trial',args);assert not r.isError,r;report=value(r)
                    if not mode:assert report['result']=='passed' and report['restoration'].startswith('passed') and report['work_power']['enabled'] and work_ttl==0
                    else:assert report['result']!='passed',mode
                    assert calls.count(('POST','/script'))==(0 if mode=='wrong_build' else 1),(mode,calls)
                    if mode in ('lost_load','lost_resume'):assert report['restoration'].startswith('passed'),report
                    if mode=='revision':assert not any(e['operation'].startswith('restore_') for e in report['events'] if e['kind']=='mutation_intent')
                    if mode=='wrong_build':assert not any(m=='POST' for m,p in calls)
                    journal=Path(report['evidence_directory'])/'journal.jsonl'
                    if journal.exists():
                        events=[json.loads(x) for x in journal.read_text().splitlines()]
                        assert all(any(before['kind']=='mutation_intent' and before['operation']==e['operation'] for before in events[:i]) for i,e in enumerate(events) if e['kind']=='mutation_receipt')
                    checks.append(mode or 'successful-trial-metrics-screens-restoration')
                reset();state['version']='01.03'
                r=await session.call_tool('vita_workbench_run_trial',args);report=value(r)
                assert report['result']=='passed' and report['restoration'].startswith('passed') and work_ttl==0
                checks.append('public-devloop-01.03-contract-and-restoration')
                ready=value(await session.call_tool('vita_workbench_doctor',{'expected_control_build':BUILD}))
                assert ready['ready_for_lua_trial'] and ready['devloop']['version']=='01.03'
                checks.append('public-devloop-01.03-readiness-through-MCP')
                reset();state['version']='01.99'
                r=await session.call_tool('vita_workbench_run_trial',args);report=value(r)
                assert report['result']=='failed' and not any(m=='POST' for m,p in calls)
                checks.append('unexpected-devloop-version-refused-before-mutation')
                ready=value(await session.call_tool('vita_workbench_doctor',{'expected_control_build':BUILD}))
                assert not ready['ready_for_lua_trial']
                checks.append('unexpected-devloop-version-not-ready')
                reset();bad={**args,'expected_profile_sha256':'0'*64};assert (await session.call_tool('vita_workbench_run_trial',bad)).isError;assert not calls;checks.append('hash-refused-before-network')
                from workbench.session import exclusive
                os.environ['VITA_WORKBENCH_LOCK']=str(root/'session.lock')
                with exclusive():
                    blocked=await session.call_tool('vita_workbench_run_trial',args);assert blocked.isError;assert not calls
                checks.append('competing-process-refused-before-network')
                report_path=str(Path(report['evidence_directory']).relative_to(root/'evidence/workbench')/'report.json')
                read=await session.call_tool('vita_workbench_read_report',{'relative_report':report_path});assert not read.isError
                assert (await session.call_tool('vita_workbench_read_report',{'relative_report':'../../resident.json'})).isError;checks.append('report-read-and-traversal-refusal')
    for s in servers:s.shutdown();s.server_close()
    print(json.dumps({'fixture':'Actual MCP and HTTP; simulated Vita adapters','passed':len(checks),'checks':checks},indent=2))
if __name__=='__main__':
    sys.path.insert(0,str(ROOT));asyncio.run(main())
