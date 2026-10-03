import hashlib,io,json,shutil,sys,tempfile,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tests'))
from ftp_fixture import Fixture
from stage_starter import stage_starter
CONFIG=b'*KERNEL\n# Local fixture only\n*main\nux0:data/vita-resident/existing.suprx\n'
class StarterStageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.ftp=Fixture()
        for name in ['dist/control','.devloop-private']:(self.root/name).mkdir(parents=True)
        shutil.copy2(ROOT/'dist/control/control_starter.vpk',self.root/'dist/control/control_starter.vpk')
        self.report=json.loads((ROOT/'dist/control/build-report.json').read_text());self.report['source_hashes']={};self.report['accepted_artifacts_preserved']={}
        self.sha=self.report['starter_package']['sha256'];self.config_sha=hashlib.sha256(CONFIG).hexdigest();self.save_report()
        (self.root/'.devloop-private/ftp.json').write_text(json.dumps({'host':'127.0.0.1','port':self.ftp.port}))
        (self.root/'.devloop-private/resident.json').write_text(json.dumps({'host':'127.0.0.1','token':'a'*32}))
        self.ftp.directories.update(['/ur0:','/ur0:/tai','/ux0:/app','/ux0:/data/vita-resident','/ux0:/data/vita-control'])
        self.ftp.files['/ur0:/tai/config.txt']=CONFIG;self.ftp.files['/ux0:/data/vita-resident/bridge.cfg']=b'a'*32+b'\n'
        self.before=dict(self.ftp.files)
    def save_report(self):(self.root/'dist/control/build-report.json').write_text(json.dumps(self.report))
    def tearDown(self):self.ftp.close();self.temp.cleanup()
    def no_writes(self):self.assertFalse(any(c in ('STOR','MKD','RNTO','DELE','RMD') for c,p in self.ftp.commands))
    def stage(self):return stage_starter(self.root,self.sha,self.config_sha)
    def test_fresh_package_two_readbacks_no_activation(self):
        result=self.stage();self.assertEqual(result['read_back_checks'],2);self.assertTrue(result['active_config_unchanged'] and result['pairing_unchanged'])
        self.assertTrue(all(self.ftp.files[p]==data for p,data in self.before.items()))
        self.assertTrue(all(p.startswith('/ux0:/data/vita-control/inbox/') for p in set(self.ftp.files)-set(self.before)))
        self.assertFalse(any(c in ('DELE','RMD') for c,p in self.ftp.commands))
    def test_wrong_package_refused_before_connection(self):
        with self.assertRaises(ValueError):stage_starter(self.root,'0'*64,self.config_sha)
        self.assertFalse(self.ftp.commands)
    def test_changed_recorded_source_refused_before_connection(self):
        (self.root/'fixture.c').write_text('changed');self.report['source_hashes']={'fixture.c':hashlib.sha256(b'original').hexdigest()};self.save_report()
        with self.assertRaises(ValueError):self.stage()
        self.assertFalse(self.ftp.commands)
    def test_accepted_artifact_drift_refused_before_connection(self):
        (self.root/'accepted.vpk').write_bytes(b'changed');self.report['accepted_artifacts_preserved']={'accepted.vpk':hashlib.sha256(b'original').hexdigest()};self.save_report()
        with self.assertRaises(ValueError):self.stage()
        self.assertFalse(self.ftp.commands)
    def test_config_drift_refused_before_writes(self):
        self.ftp.files['/ur0:/tai/config.txt']+=b'changed\n'
        with self.assertRaises(RuntimeError):self.stage()
        self.no_writes()
    def test_pairing_drift_refused_before_writes(self):
        self.ftp.files['/ux0:/data/vita-resident/bridge.cfg']=b'b'*32+b'\n'
        with self.assertRaises(RuntimeError):self.stage()
        self.no_writes()
    def test_active_session_guard_refused_and_preserved(self):
        path='/ux0:/data/vita-control/control-session.lock';self.ftp.files[path]=b'prior session'
        with self.assertRaises(RuntimeError):self.stage()
        self.no_writes();self.assertEqual(self.ftp.files[path],b'prior session')
    def test_unknown_installed_starter_refused(self):
        self.ftp.directories.add('/ux0:/app/CHRS00011');self.ftp.files['/ux0:/app/CHRS00011/eboot.bin']=b'unknown'
        with self.assertRaises(RuntimeError):self.stage()
        self.no_writes()
    def test_exact_current_installed_starter_read_back(self):
        self.ftp.directories.add('/ux0:/app/CHRS00011')
        with zipfile.ZipFile(self.root/'dist/control/control_starter.vpk') as archive:
            for name in ['eboot.bin','vita_control_kernel.skprx','vita_control.suprx','control_bootstrap_probe.suprx','sce_sys/param.sfo']:self.ftp.files['/ux0:/app/CHRS00011/'+name]=archive.read(name)
        result=self.stage();self.assertEqual(len(result['previous_installed']),5)
    def test_corrupt_part_not_published(self):
        self.ftp.fault='corrupt_part'
        with self.assertRaises(RuntimeError):self.stage()
        self.assertEqual(sum(c=='STOR' for c,p in self.ftp.commands),1);self.assertFalse(any(c=='RNTO' for c,p in self.ftp.commands))
    def test_lost_rename_not_replayed(self):
        self.ftp.fault='drop_rename'
        with self.assertRaises(RuntimeError):self.stage()
        self.assertEqual(sum(c=='STOR' for c,p in self.ftp.commands),1)
        result=json.loads(next((self.root/'evidence/control').glob('*/deployment.json')).read_text());self.assertIn('uncertain',result['state'])
if __name__=='__main__':unittest.main(verbosity=2)
