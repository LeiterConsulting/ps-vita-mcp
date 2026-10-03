import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests'))
from ftp_fixture import Fixture
from stage_control import proposal,stage_control
BEFORE=b'*main\r\nux0:data/vita-resident/existing.suprx\r\n*KERNEL\r\nur0:tai/yamt_helper.skprx\r\nur0:tai/PSVshell.skprx\r\n'
SHA=hashlib.sha256(BEFORE).hexdigest()

class StageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.ftp=Fixture()
        for path in ['.devloop-private','dist/control','resident/control']: (self.root/path).mkdir(parents=True)
        (self.root/'resident/control/LICENSE.vitacompanion').write_text('Fixture license')
        modules={}
        for name,leaf in [('vita_control','vita_control.suprx'),('vita_control_kernel','vita_control_kernel.skprx')]:
            data=b'SCE\0'+name.encode()*100;(self.root/'dist/control'/leaf).write_bytes(data);modules[name]={'file':leaf,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        report={'version':'0.2.2','build_id':'1'*64,'modules':modules,'source_hashes':{},'accepted_artifacts_preserved':{}}
        (self.root/'dist/control/build-report.json').write_text(json.dumps(report))
        (self.root/'.devloop-private/resident.json').write_text(json.dumps({'token':'a'*32}))
        (self.root/'.devloop-private/ftp.json').write_text(json.dumps({'host':'127.0.0.1','port':self.ftp.port}))
        self.ftp.directories.update(['/ur0:','/ur0:/tai','/ux0:/data/vita-resident']);self.ftp.files['/ur0:/tai/config.txt']=BEFORE;self.ftp.files['/ux0:/data/vita-resident/bridge.cfg']=b'a'*32+b'\n'
    def tearDown(self): self.ftp.close();self.temp.cleanup()
    def test_matched_pair_staged_and_config_pairing_untouched(self):
        result=stage_control(self.root,SHA)
        self.assertEqual(self.ftp.files['/ur0:/tai/config.txt'],BEFORE);self.assertEqual(self.ftp.files['/ux0:/data/vita-resident/bridge.cfg'],b'a'*32+b'\n')
        self.assertTrue(all(v['read_back_checks']==2 for v in result['files'].values()))
        after=self.ftp.files['/ux0:/data/vita-control/'+result['attempt']+'/config.txt'];self.assertTrue(after.startswith(BEFORE))
        self.assertIn(b'*KERNEL\r\n'+result['kernel_plugin'].encode(),after);self.assertIn(b'*main\r\n'+result['user_plugin'].encode(),after)
        self.assertFalse(any(c in ('DELE','RMD') for c,p in self.ftp.commands))
    def test_changed_config_refuses_before_mutation(self):
        with self.assertRaises(RuntimeError): stage_control(self.root,'0'*64)
        self.assertFalse(any(c in ('STOR','MKD','RNTO') for c,p in self.ftp.commands))
    def test_existing_root_refuses_before_mutation(self):
        self.ftp.directories.add('/ur0:/tai/vita-control')
        with self.assertRaises(RuntimeError): stage_control(self.root,SHA)
        self.assertFalse(any(c in ('STOR','MKD','RNTO') for c,p in self.ftp.commands))
    def test_corrupt_part_never_activates_or_replays(self):
        self.ftp.fault='corrupt_part'
        with self.assertRaises(RuntimeError): stage_control(self.root,SHA)
        self.assertEqual(sum(c=='STOR' for c,p in self.ftp.commands),1);self.assertFalse(any(c=='RNTO' for c,p in self.ftp.commands));self.assertEqual(self.ftp.files['/ur0:/tai/config.txt'],BEFORE)
    def test_lost_rename_has_receipt_and_no_replay(self):
        self.ftp.fault='drop_rename'
        with self.assertRaises(RuntimeError): stage_control(self.root,SHA)
        self.assertEqual(sum(c=='STOR' for c,p in self.ftp.commands),1)
        plan=json.loads(next((self.root/'evidence/control').glob('*/deployment.json')).read_text());self.assertIn('uncertain',plan['state']);self.assertEqual(self.ftp.files['/ur0:/tai/config.txt'],BEFORE)
    def test_duplicate_config_control_and_invalid_paths_refused(self):
        user='ux0:data/vita-control/setup-'+'1'*12+'-'+'2'*32+'/vita_control.suprx';kernel='ur0:tai/vita-control/setup-'+'1'*12+'-'+'2'*32+'/vita_control_kernel.skprx'
        for config,u,k in [(BEFORE+b'vita_control.suprx\n',user,kernel),(BEFORE,user,'ux0:wrong'),(BEFORE.rstrip(),user,kernel)]:
            with self.assertRaises(ValueError):proposal(config,u,k)

if __name__=='__main__':unittest.main(verbosity=2)
