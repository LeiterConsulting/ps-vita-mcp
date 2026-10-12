"""Real local HTTP proves job endpoint binding; no physical Vita acceptance."""
import asyncio
import hashlib
import json
import os
import struct
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from resident.control.bridge_tools import ControlClient
from workbench.runner import Device,freeze_device_endpoints
from workbench import server,qualify_target,verify_file
from workbench.power import lease
from bridge.prove_scripts import restore_owned_native

BUILD='a'*64
TARGET='b'*64
TOKEN='d'*32
FILE=b'endpoint-pinned readback\x00\xff'*512
ATTEMPT='c'*32
NAME='pinned.bin'
FILE_HASH=hashlib.sha256(FILE).hexdigest()


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'VITA_WORKBENCH_LOCK':str(self.folder/'lock')});self.env.start()
        self.calls=[];self.sequence=0;self.drift=False;self.config={}
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def record(self):
                owner.calls.append((self.command,self.path,self.headers.get('Authorization')))
                if self.headers.get('Authorization')!='Bearer '+TOKEN:
                    self.send({},code=403);return False
                return True
            def do_GET(self):
                if not self.record():return
                if self.path=='/status':
                    if owner.drift:
                        owner.config.update(host='127.0.0.2',port=1,token='f'*32)
                        os.environ['VITA_CONTROL_PORT']='0';os.environ['VITA_TARGET_PORT']='0'
                    return self.send({'app':'Vita Control','version':'0.3.4','abi':2,'build_id':BUILD,'power_protocol':1,'capture_codecs':['rgb'],'lease_remaining_ms':0,'uptime_ms':len(owner.calls)})
                if self.path=='/workspace/stat/'+ATTEMPT+'/'+NAME:
                    return self.send({'vita_path':'ux0:data/vita-control/workspace/'+ATTEMPT+'/'+NAME,'bytes':len(FILE),'sha256':FILE_HASH})
                if self.path=='/workspace/read/'+ATTEMPT+'/'+NAME:return self.send(FILE,'application/octet-stream')
                if self.path=='/screen/preview':
                    owner.sequence+=1;raw=bytes([20,40,60])*240*136
                    header=struct.pack('<6Ii5I2Q',0x31465256,2,owner.sequence,240,136,len(raw),77,owner.sequence,960,544,1,0,100,200)
                    return self.send(header+raw,'application/x-vita-rgb')
                self.send({},code=404)
            def do_POST(self):
                if not self.record():return
                body=self.rfile.read(int(self.headers.get('Content-Length','0')))
                if self.path=='/power/lease':
                    ttl=struct.unpack('<5I',body)[2]
                    return self.send({'app':'Vita Work Power','abi':2,'lease_remaining_ms':ttl,'dimmed':False})
                self.send({},code=404)
            def send(self,value,mime='application/json',code=200):
                raw=json.dumps(value).encode() if mime=='application/json' else value
                self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        self.http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=self.http.serve_forever,daemon=True).start()
        self.target_calls=[]
        class TargetHandler(Handler):
            def do_GET(self):
                owner.target_calls.append(self.headers.get('Authorization'))
                self.send({'app':'Vita Input Target','title_id':'CHRS00012','protocol':1,'version':'01.00','build_id':TARGET,'run':'e'*32,'pid':77,'frame':len(owner.target_calls)})
        self.target_http=ThreadingHTTPServer(('127.0.0.1',0),TargetHandler);threading.Thread(target=self.target_http.serve_forever,daemon=True).start()
        os.environ['VITA_CONTROL_PORT']=str(self.http.server_port);os.environ['VITA_TARGET_PORT']=str(self.target_http.server_port)
        self.config.update(host='127.0.0.1',port=self.http.server_port-1,token=TOKEN)
        self.device=Device.__new__(Device);self.device.control=ControlClient(lambda:dict(self.config))
        self.device.resident=SimpleNamespace(configuration=lambda:dict(self.config))

    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.target_http.shutdown();self.target_http.server_close();self.env.stop();self.temp.cleanup()

    def test_file_job_freezes_before_baseline_and_reads_and_cleanup(self):
        self.drift=True
        result=verify_file.verify(ATTEMPT,NAME,len(FILE),FILE_HASH,BUILD,self.device,self.folder)
        self.assertEqual(result['result'],'passed',result)
        self.assertEqual(result['read_back_checks'],2)
        self.assertEqual(Path(result['local_artifact']).read_bytes(),FILE)
        self.assertEqual(sum(path.startswith('/workspace/read/') for _,path,_ in self.calls),2)
        self.assertEqual(self.calls[-1][:2],('POST','/power/lease'))
        self.assertTrue(all(auth=='Bearer '+TOKEN for _,_,auth in self.calls))
        evidence=''.join(path.read_text() for path in Path(result['evidence_directory']).glob('*.json*'))
        self.assertNotIn(TOKEN,evidence);self.assertNotIn('f'*32,evidence)

    def test_soak_status_captures_and_cleanup_stay_on_baseline_endpoint(self):
        self.drift=True;clock=SimpleNamespace(now=0)
        def advance(seconds):clock.now+=seconds
        with patch.object(server,'time',SimpleNamespace(monotonic=lambda:clock.now,sleep=advance)):
            result=server.soak(10,BUILD,self.device,self.folder)
        self.assertEqual(result['result'],'passed',result)
        self.assertEqual(self.sequence,10)
        self.assertTrue(result['work_power']['enabled'])
        self.assertEqual(self.calls[-1][:2],('POST','/power/lease'))
        self.assertTrue(all(auth=='Bearer '+TOKEN for _,_,auth in self.calls))

    def test_target_host_token_and_separate_port_pin_before_baseline(self):
        freeze_device_endpoints(self.device,with_target=True);self.drift=True
        self.device.control_status()
        for _ in range(2):self.assertEqual(self.device.target()['pid'],77)
        self.assertEqual(self.target_calls,['Bearer '+TOKEN]*2)
        self.assertNotEqual(self.device._target_endpoint['port'],self.device.control.endpoint()['port'])

    def test_qualification_freezes_target_before_first_status(self):
        self.drift=True
        # Target has no input telemetry: fail before mutation, after observing its pinned endpoint.
        result=qualify_target.qualify(BUILD,TARGET,self.device,self.folder)
        self.assertEqual(result['result'],'failed')
        self.assertEqual(self.target_calls,['Bearer '+TOKEN])
        self.assertFalse(any(path in ('/input','/release') for _,path,_ in self.calls))

    def test_invalid_target_override_rejected_before_any_network(self):
        os.environ['VITA_TARGET_PORT']='0'
        result=qualify_target.qualify(BUILD,TARGET,self.device,self.folder)
        self.assertEqual(result['result'],'failed');self.assertEqual(self.calls,[]);self.assertEqual(self.target_calls,[])

    def test_standalone_work_lease_freezes_before_status(self):
        self.drift=True
        result=lease(self.device.control,5000)
        self.assertEqual(result['lease_remaining_ms'],5000)
        self.assertEqual([path for _,path,_ in self.calls],['/status','/power/lease'])
        self.assertTrue(all(auth=='Bearer '+TOKEN for _,_,auth in self.calls))


class ProofCleanupTests(unittest.TestCase):
    def setUp(self):
        self.pin={'app':'Vita DevLoop','protocol':1,'version':'01.04','title_id':'CHRS00003','pid':77,'run':'a'*32,'build_id':'b'*64}
        self.owned={'revision':12,'sha256':'c'*64,'active':True}
        self.state={**self.pin,'revision':12,'experiment':'lua','paused':False}
        self.script={**self.pin,**self.owned,'paused':False,'faulted':False}
        self.calls=[]
    async def call(self,name,arguments=None):
        self.calls.append((name,arguments))
        value=self.state if name=='vita_status' else self.script if name=='vita_script_status' else {**self.pin,'revision':arguments['expected_revision']+1,'active':False,'paused':True}
        return dict(value),None
    def restore(self):return asyncio.run(restore_owned_native(self.call,self.owned,self.pin))
    def assert_no_mutation(self):self.assertEqual([name for name,_ in self.calls],['vita_status','vita_script_status'])
    def test_cleanup_sends_only_owned_revision(self):
        self.assertFalse(self.restore()['active'])
        self.assertEqual(self.calls[-1],('vita_script_control',{'action':'native','expected_revision':12}))
    def test_cleanup_refuses_other_revision_even_same_source(self):
        self.state['revision']=self.script['revision']=14
        with self.assertRaisesRegex(RuntimeError,'ownership changed'):self.restore()
        self.assert_no_mutation()
    def test_cleanup_refuses_other_source_even_same_revision(self):
        self.script['sha256']='d'*64
        with self.assertRaisesRegex(RuntimeError,'ownership changed'):self.restore()
        self.assert_no_mutation()
    def test_cleanup_refuses_native_run_drift(self):
        self.script['run']='d'*32
        with self.assertRaisesRegex(RuntimeError,'identity changed'):self.restore()
        self.assert_no_mutation()
    def test_own_runtime_fault_can_restore_at_single_advanced_revision(self):
        self.state['revision']=self.script['revision']=13;self.script.update(paused=True,faulted=True)
        self.restore();self.assertEqual(self.calls[-1][1]['expected_revision'],13)
    def test_lost_receipt_never_adopts_scene_for_cleanup(self):
        self.owned=None
        with self.assertRaisesRegex(RuntimeError,'ownership is unconfirmed'):self.restore()
        self.assert_no_mutation()


if __name__=='__main__':unittest.main(verbosity=2)
