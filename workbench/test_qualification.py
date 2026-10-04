"""Qualification decisions against simulated telemetry, separate from device proof."""
import tempfile,unittest,sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import workbench.qualify_target as q
BUILD='a'*64;TARGET='b'*64
class Device:
    def __init__(self,fault=''):
        self.control=SimpleNamespace();self.now=10000;self.end=0;self.reason=0;self.releases=0;self.released=0;self.exited=False;self.fault=fault;self.inputs=[];self.focus_at=0;self.manual_releases=0;self.focus_screen_manual_releases=None
        self.t={'app':'Vita Input Target','title_id':'CHRS00012','version':'01.00','protocol':1,'build_id':TARGET,'run':'c'*32,'pid':77,'frame':100,'buttons':0,'sticks':[128]*4,'last_buttons':0,'last_sticks':[128]*4,'front_seen':0,'rear_seen':0,'active_frames':0,'neutral_frames':0,'front':[0,0],'rear':[0,0]}
    def advance(self,seconds):self.now+=int(seconds*1000)
    def update(self):
        if self.focus_at and self.now>=self.focus_at:
            self.focus_at=0;self.exited=True;self.end=0;self.reason=2;self.releases+=1;self.released=self.now
        if self.end and self.now>=self.end:
            self.end=0;self.reason=1;self.releases+=1;self.released=self.now;self.t['buttons']=0;self.t['sticks']=[128]*4;self.t['neutral_frames']+=5
    def control_status(self):
        self.update();return {'app':'Vita Control','version':'0.3.0','abi':2,'build_id':BUILD,'lease_remaining_ms':max(0,self.end-self.now),'sample_ms':self.now,'release_count':self.releases,'last_release_reason':self.reason,'last_release_ms':self.released}
    def target(self):self.update();self.t['frame']+=1;return dict(self.t)
    def screen(self):
        if self.exited:self.focus_screen_manual_releases=self.manual_releases
        return b'fixture image; not actual PNG',{'target_pid':77 if not self.exited or self.fault=='same_pid' else 88}
    def input(self,pid,values):
        self.inputs.append(values);self.end=self.now+values['ttl_ms'];self.t['last_buttons']=sum(qbit for name,qbit in [('select',1),('start',8),('up',16),('right',32),('down',64),('left',128),('l',256),('r',512),('triangle',4096),('circle',8192),('cross',16384),('square',32768)] if name in values['buttons'])
        self.t['buttons']=self.t['last_buttons'];self.t['active_frames']+=10
        if self.fault=='shoulders_missing':self.t['last_buttons']&=~0x300;self.t['buttons']&=~0x300
        if 'left_stick' in values:
            self.t['last_sticks']=values['left_stick']+values['right_stick'];self.t['sticks']=self.t['last_sticks']
            self.t['front_seen']+=1;self.t['rear_seen']+=0 if self.fault=='rear_missing' else 1;self.t['front']=values['front_touch'];self.t['rear']=values['rear_touch']
        if set(values['buttons'])=={'start','select'}:
            if self.fault=='delayed_focus':self.focus_at=self.now+175
            elif self.fault=='no_focus':pass
            else:
                self.exited=True;self.end=0;self.reason=3 if self.fault=='manual_release' else 1 if self.fault=='expired' else 2;self.releases+=1;self.released=self.now
        return self.control_status()
    def release(self):self.manual_releases+=1;self.end=0;return {'lease_remaining_ms':0}
class Tests(unittest.TestCase):
    def run_case(self,fault=''):
        d=Device(fault)
        with tempfile.TemporaryDirectory() as folder,patch.object(q,'time',SimpleNamespace(sleep=d.advance,monotonic=lambda:d.now/1000)):
            result=q.qualify(BUILD,TARGET,d,Path(folder))
        return result,d
    def test_all_channels_and_independent_focus(self):
        result,d=self.run_case();self.assertEqual(result['result'],'passed');self.assertEqual(len(result['checks']),7);self.assertEqual(len(d.inputs),7)
    def test_manual_release_does_not_prove_focus(self):self.assertEqual(self.run_case('manual_release')[0]['result'],'failed')
    def test_expiry_does_not_prove_focus(self):self.assertEqual(self.run_case('expired')[0]['result'],'failed')
    def test_delayed_kernel_cancellation_is_observed_before_cleanup(self):
        result,d=self.run_case('delayed_focus');self.assertEqual(result['result'],'passed')
        observations=result['focus_observations'];self.assertGreater(len(observations),1)
        self.assertGreater(observations[0]['lease_remaining_ms'],0);self.assertEqual(observations[-1]['last_release_reason'],2)
        self.assertEqual(d.focus_screen_manual_releases,0);self.assertEqual(d.manual_releases,1)
    def test_waiting_for_exit_cannot_turn_expiry_into_focus_proof(self):
        result,d=self.run_case('no_focus');self.assertEqual(result['result'],'failed')
        self.assertGreater(len(result['focus_observations']),1);self.assertEqual(result['focus_observations'][-1]['last_release_reason'],1)
    def test_same_display_pid_does_not_prove_focus(self):self.assertEqual(self.run_case('same_pid')[0]['result'],'failed')
    def test_missing_rear_channel_fails_before_self_exit(self):
        result,d=self.run_case('rear_missing');self.assertEqual(result['result'],'failed');self.assertFalse(result['focus_self_exit_submitted']);self.assertEqual(len(d.inputs),1)
    def test_failed_shoulders_do_not_hide_or_pass_focus(self):
        result,d=self.run_case('shoulders_missing');self.assertEqual(result['result'],'failed');self.assertTrue(result['focus_self_exit_submitted']);self.assertFalse(result['checks'][1]['passed']);self.assertTrue(result['checks'][-1]['passed'])
if __name__=='__main__':unittest.main(verbosity=2)
