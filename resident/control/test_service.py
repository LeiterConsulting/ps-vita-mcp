"""Exercise the real control HTTP parser/storage; hardware adapters are simulated."""
import hashlib
import http.client
import json
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time
import unittest

TOKEN='b'*32
ID='1'*32
NAME='script.lua'

class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); (self.root/'workspace').mkdir()
        with socket.socket() as s: s.bind(('127.0.0.1',0)); self.port=s.getsockname()[1]
        self.log=(self.root/'server.log').open('wb')
        self.process=subprocess.Popen(['build/resident/control/host-server',str(self.root),str(self.port),TOKEN],stdout=self.log,stderr=self.log)
        for _ in range(100):
            try: self.request('GET','/status'); break
            except OSError: time.sleep(.02)
        else: raise RuntimeError('Control host fixture failed to start')
    def tearDown(self):
        self.process.terminate(); self.process.wait(timeout=10); self.log.close()
        text=(self.root/'server.log').read_text()
        self.assertNotIn('ERROR: AddressSanitizer',text); self.assertNotIn('runtime error:',text); self.temp.cleanup()
    def request(self,method,path,body=None,digest=None,token=TOKEN):
        c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=8)
        headers={'Authorization':'Bearer '+token}
        if digest: headers['X-SHA256']=digest
        c.request(method,path,body,headers); r=c.getresponse(); data=r.read(); c.close(); return r.status,data
    def input(self,ttl=100,pid=77,buttons=0x4000,flags=0):
        return struct.pack('<13Ii',0x31495256,2,ttl,buttons,flags,128,128,128,128,0,0,0,0,pid)
    def test_lease_expires_without_release_and_focus_change_cancels(self):
        status,data=self.request('POST','/input',self.input()); self.assertEqual(status,200); self.assertGreater(json.loads(data)['lease_remaining_ms'],0)
        time.sleep(.13); self.assertEqual(json.loads(self.request('GET','/status')[1])['lease_remaining_ms'],0)
        expired=json.loads(self.request('GET','/status')[1]);self.assertEqual(expired['last_release_reason'],1);self.assertGreater(expired['last_release_ms'],0)
        self.request('POST','/input',self.input(1000)); (self.root/'fault-focus').touch()
        result=json.loads(self.request('GET','/status')[1]); self.assertEqual(result['lease_buttons'],0); self.assertEqual(result['lease_flags'],0)
        self.assertEqual(result['last_release_reason'],2)
        self.assertEqual(self.request('POST','/input',self.input(pid=77))[0],409)
    def test_input_bounds_auth_and_explicit_release(self):
        for payload in [self.input(1001),self.input(15),self.input(buttons=0x10000),self.input(flags=16),b'x',self.input(pid=-1)]:
            self.assertEqual(self.request('POST','/input',payload)[0],400)
        self.assertEqual(self.request('POST','/input',self.input(),token='c'*32)[0],401)
        self.request('POST','/input',self.input(1000)); self.assertEqual(self.request('POST','/release',b'')[0],200)
        self.assertEqual(json.loads(self.request('GET','/status')[1])['lease_buttons'],0)
    def test_frame_bounds_metadata_rgb_and_failure(self):
        for route,w,h in [('preview',240,136),('detail',480,272)]:
            status,body=self.request('GET','/screen/'+route); self.assertEqual(status,200)
            header=struct.unpack('<6Ii5I2Q',body[:64]); self.assertEqual(header[0],0x31465256); self.assertEqual(header[3:6],(w,h,w*h*3)); self.assertEqual(header[6],77)
            self.assertEqual(len(body),64+w*h*3); self.assertEqual(body[64:67],bytes([0,1,2]))
        (self.root/'fault-capture').touch(); self.assertEqual(self.request('GET','/screen/preview')[0],503)
    def test_real_server_compressed_frame_roundtrip(self):
        from rgb_codec import decode_rle
        for route in ['preview','detail']:
            raw=self.request('GET','/screen/'+route)[1][64:]
            code,body=self.request('GET','/screen/'+route+'/rle');self.assertEqual(code,200)
            tag,size,elapsed=struct.unpack('<3I',body[64:76]);self.assertEqual(tag,0x31454c52);self.assertEqual(size,len(body)-76)
            self.assertEqual(decode_rle(body[76:],len(raw)),raw)
    def test_workspace_write_read_stat_listing_and_hash_guarded_removal(self):
        payload=b'function update(dt) return dt end\0'; digest=hashlib.sha256(payload).hexdigest()
        status,data=self.request('POST',f'/workspace/write/{ID}/{NAME}',payload,digest); self.assertEqual(status,201)
        self.assertEqual(self.request('GET',f'/workspace/read/{ID}/{NAME}')[1],payload)
        info=json.loads(self.request('GET',f'/workspace/stat/{ID}/{NAME}')[1]); self.assertEqual(info['sha256'],digest)
        listing=json.loads(self.request('GET',f'/workspace/list/0/{ID}')[1]); self.assertEqual(listing['entries'][0]['name'],NAME)
        self.assertEqual(self.request('POST',f'/workspace/delete/{ID}/{NAME}',b'','0'*64)[0],409)
        self.assertEqual(self.request('POST',f'/workspace/delete/{ID}/{NAME}',b'',digest)[0],200)
        self.assertEqual(self.request('GET',f'/workspace/read/{ID}/{NAME}')[0],404)
    def test_workspace_traversal_and_overwrite_refused(self):
        payload=b'hello'; digest=hashlib.sha256(payload).hexdigest()
        for path in [f'/workspace/write/{ID}/../config.txt',f'/workspace/write/{ID}/x/y',f'/workspace/write/{ID}/..','/workspace/write/not-an-id/file']:
            self.assertEqual(self.request('POST',path,payload,digest)[0],400)
        self.request('POST',f'/workspace/write/{ID}/{NAME}',payload,digest)
        self.assertEqual(self.request('POST',f'/workspace/write/{ID}/{NAME}',b'other',hashlib.sha256(b'other').hexdigest())[0],409)
        self.assertEqual((self.root/'workspace'/ID/NAME).read_bytes(),payload)
    def test_storage_fault_never_publishes(self):
        for n,fault in enumerate(['write','read','corrupt-read','close','rename']):
            (self.root/('fault-'+fault)).touch(); attempt=f'{n+2:032x}'; payload=b'probe'
            code,_=self.request('POST',f'/workspace/write/{attempt}/{NAME}',payload,hashlib.sha256(payload).hexdigest())
            self.assertNotEqual(code,201); self.assertFalse((self.root/'workspace'/attempt/NAME).exists())
    def test_app_allowlist_and_observation_is_pending(self):
        self.assertEqual(self.request('POST','/app/launch/NPXS10015',b'')[0],403)
        result=json.loads(self.request('POST','/app/launch/CHRS00003',b'')[1]); self.assertEqual(result['native_result'],0); self.assertEqual(result['runtime_observation'],'pending')
    def test_work_lease_bounds_auth_status_and_end(self):
        def pack(ttl=30000,idle=30000,percent=20,abi=2):
            return struct.pack('<5I',0x31505756,abi,ttl,idle,percent)
        for payload in [pack(4999),pack(30001),pack(idle=4999),pack(idle=120001),pack(percent=0),pack(percent=51),pack(abi=1),b'x']:
            self.assertEqual(self.request('POST','/power/lease',payload)[0],400)
        self.assertEqual(self.request('POST','/power/lease',pack(),token='c'*32)[0],401)
        self.assertEqual(self.request('POST','/power/lease',pack())[0],200)
        status=json.loads(self.request('GET','/status')[1])
        self.assertTrue(status['keep_awake']);self.assertEqual(status['power_protocol'],1)
        self.assertGreater(status['work_remaining_ms'],0)
        work=json.loads(self.request('GET','/power/status')[1])
        self.assertEqual(work['dim_percent'],20);self.assertIn('motion_fresh',work)
        self.assertEqual(len(work['touch_diagnostics']),2)
        for panel in work['touch_diagnostics']:
            self.assertEqual(set(panel),{'reader_pid','last_reader_pid','native_contacts','reads','advances','hook_reads','source_ticks','received_ms','changed_ms'})
            self.assertTrue(all(type(v) is int for v in panel.values()))
        self.assertEqual(self.request('POST','/power/lease',pack(ttl=0))[0],200)
        self.assertFalse(json.loads(self.request('GET','/status')[1])['keep_awake'])

if __name__=='__main__': unittest.main(verbosity=2)
