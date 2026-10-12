"""Preparation decisions use simulated adapters; no Vita is contacted."""
import http.client
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from workbench import prepare as p

BUILD = 'a' * 64


def unavailable():
    try:
        raise ConnectionRefusedError('fixture transport unavailable')
    except ConnectionRefusedError as error:
        raise RuntimeError('fixture endpoint unavailable') from error


class Clock:
    def __init__(self): self.now = 0
    def monotonic(self): return self.now
    def sleep(self, seconds): self.now += seconds


class Keeper:
    def __init__(self, client, folder): self.client = client; self.enabled = False
    def start(self, identity): self.enabled = True; self.client.calls.append('power_start')
    def stop(self):
        if self.enabled: self.client.calls.append('power_end')
        return {'enabled': self.enabled, 'end': 'fixture cleanup'}


class Device:
    def __init__(self, mode=''):
        self.mode = mode; self.control = self; self.calls = []; self.started = mode not in (
            'absent', 'lost_launch', 'rejected_launch', 'invalid_launch', 'launch_http_rejection', 'never_ready', 'slow_start')
        self.frame = 100; self.sequence = 0; self.status_reads = 0; self.control_reads = 0
        self.version='01.04' if mode in ('mapped','background_pid') or mode.startswith('native_') else '01.03'
    def identity(self):
        if self.version!='01.04':return {}
        return {'protocol':1,'title_id':'CHRS00003','pid':99 if self.mode=='background_pid' else 77,
                'run':('e' if self.mode=='native_run_change' and self.status_reads>2 else 'd')*32,
                'build_id':('e' if self.mode=='native_build_change' and self.status_reads>2 else 'c')*64}
    def control_status(self):
        self.calls.append('control_status'); self.control_reads += 1
        return {'app': 'Vita Control', 'abi': 2, 'build_id': 'b'*64 if self.mode == 'wrong_build' else BUILD,
                'uptime_ms': 0 if self.mode == 'control_restart' and self.control_reads > 3 else 1000+self.control_reads,
                'lease_remaining_ms': 1 if self.mode == 'active_input' or self.mode == 'late_input' and self.control_reads > 3 else 0,
                'work_remaining_ms': 1 if self.mode == 'active_work' else 0}
    def validate_devloop_endpoint(self):
        if self.mode == 'wrong_endpoint' or self.mode == 'endpoint_change' and self.status_reads > 1:
            raise RuntimeError('fixture endpoint mismatch or change')
    def status(self):
        self.calls.append('status'); self.status_reads += 1
        if self.mode == 'unauthorized': raise RuntimeError('Vita HTTP 401')
        if self.mode == 'malformed_http':
            try: raise http.client.BadStatusLine('fixture protocol failure')
            except http.client.BadStatusLine as error: raise RuntimeError('fixture bad protocol') from error
        if not self.started or self.mode == 'never_ready' or self.mode == 'slow_start' and self.status_reads < 4:
            unavailable()
        if self.mode != 'stalled': self.frame += 1
        if self.mode == 'app_restart' and self.status_reads > 2: self.frame = 1
        value = {'app': 'Wrong App' if self.mode == 'wrong_app' else 'Vita DevLoop', 'protocol': 1,
                'version': '01.99' if self.mode == 'wrong_version' else self.version, 'frame': self.frame,
                'revision': 2 if self.mode == 'revision_change' and self.status_reads > 2 else 1,
                'paused': self.mode != 'running'}
        value.update(self.identity())
        if self.mode=='native_bad_run':value['run']='bad'
        if self.mode=='native_bad_pid':value['pid']=True
        return value
    def script(self):
        self.calls.append('script')
        state = {'app': 'Vita DevLoop', 'version': self.version, 'revision': 2 if self.mode == 'revision_change' and self.status_reads > 2 else 1,
                 'paused': self.mode != 'running', 'faulted': self.mode == 'faulted', 'sha256': 'c'*64}
        state.update(self.identity())
        if self.mode=='legacy_script':state.pop('app');state.pop('version')
        if self.mode=='native_script_run':state['run']='e'*32
        return state
    def screen(self):
        self.calls.append('screen'); self.sequence += 1
        return b'fixture image, not device pixels', {'target_pid': 88 if self.mode == 'focus_change' and self.sequence > 1 else 77,
                'sequence': 1 if self.mode == 'stale_capture' else self.sequence}
    def launch_devloop(self):
        self.calls.append('launch'); self.started = True
        if self.mode == 'lost_launch': unavailable()
        if self.mode == 'launch_http_rejection': raise RuntimeError('Control operation rejected with HTTP 403')
        if self.mode == 'invalid_launch': return {'native_result': 0}
        return {'title_id': 'CHRS00003', 'action': 'launch', 'native_result': -1 if self.mode == 'rejected_launch' else 0}


class PrepareTests(unittest.TestCase):
    def run_case(self, mode='', **kwargs):
        d = Device(mode); clock = Clock()
        kwargs.setdefault('expected_devloop_version',d.version)
        if d.version=='01.04':kwargs.setdefault('expected_devloop_build','c'*64)
        with tempfile.TemporaryDirectory() as folder, patch.object(p, 'time', clock), patch.object(p, 'WorkKeeper', Keeper):
            report = p.prepare(BUILD, timeout_s=2, device=d, root=Path(folder), **kwargs)
            journal = Path(report['evidence_directory'])/'journal.jsonl'
            events = [json.loads(line) for line in journal.read_text(encoding='utf-8').splitlines()] if journal.exists() else []
            self.assertEqual(json.loads((Path(report['evidence_directory'])/'report.json').read_text(encoding='utf-8'))['result'], report['result'])
        return report, d, events

    def test_already_ready_never_launches_or_changes_scene(self):
        report, d, events = self.run_case()
        self.assertEqual(report['result'], 'runtime_ready_target_unverified'); self.assertTrue(report['ready_for_script_reload'])
        self.assertFalse(report['ready_for_lua_trial']); self.assertFalse(report['ready_for_input_trial'])
        self.assertEqual(report['launch_submissions'], 0); self.assertNotIn('launch', d.calls)
        self.assertEqual(d.calls.count('power_start'), 1); self.assertEqual(d.calls.count('power_end'), 1)
        self.assertEqual(len([event for event in events if event['kind'] == 'runtime_observation']), 2)

    def test_absent_runtime_launches_once_and_requires_observation(self):
        report, d, events = self.run_case('absent')
        self.assertEqual(report['result'], 'runtime_ready_target_unverified'); self.assertEqual(d.calls.count('launch'), 1)
        kinds = [event['kind'] for event in events]
        self.assertLess(kinds.index('mutation_intent'), kinds.index('mutation_receipt'))
        self.assertIn('launch_screen', report)

    def test_lost_launch_reply_reconciles_without_replay(self):
        report, d, events = self.run_case('lost_launch')
        self.assertEqual(report['result'], 'runtime_ready_target_unverified'); self.assertEqual(d.calls.count('launch'), 1)
        self.assertIn('unconfirmed', report['launch_outcome'])
        self.assertEqual(len([event for event in events if event['kind'] == 'mutation_unconfirmed']), 1)
        self.assertFalse(next(event for event in events if event['kind'] == 'mutation_unconfirmed')['replayed'])

    def test_rejected_or_invalid_launch_remains_blocked_despite_runtime(self):
        for mode in ('rejected_launch', 'invalid_launch', 'launch_http_rejection'):
            with self.subTest(mode=mode):
                report, d, _ = self.run_case(mode)
                self.assertEqual(report['result'], 'blocked'); self.assertFalse(report['ready_for_lua_trial'])
                self.assertEqual(d.calls.count('launch'), 1); self.assertIn('runtime', report)
                self.assertIn('power_end', d.calls)

    def test_slow_runtime_is_polled_without_repeated_launch(self):
        report, d, events = self.run_case('slow_start')
        self.assertEqual(report['result'], 'runtime_ready_target_unverified'); self.assertEqual(d.calls.count('launch'), 1)
        self.assertGreater(len([event for event in events if event['kind'] == 'runtime_wait']), 0)

    def test_livearea_dialog_or_unavailable_runtime_times_out(self):
        report, d, _ = self.run_case('never_ready')
        self.assertEqual(report['result'], 'blocked'); self.assertEqual(d.calls.count('launch'), 1)
        self.assertIn('Timed out', report['failure']); self.assertIn('power_end', d.calls)

    def test_auth_or_protocol_errors_never_trigger_launch(self):
        for mode in ('unauthorized', 'malformed_http', 'wrong_app', 'wrong_version', 'running', 'faulted'):
            with self.subTest(mode=mode):
                report, d, _ = self.run_case(mode)
                self.assertEqual(report['result'], 'blocked'); self.assertNotIn('launch', d.calls)
                self.assertNotIn('power_start', d.calls)

    def test_wrong_build_or_existing_leases_refuse_before_runtime(self):
        for mode in ('wrong_build', 'active_input', 'active_work'):
            with self.subTest(mode=mode):
                report, d, _ = self.run_case(mode)
                self.assertEqual(report['result'], 'blocked'); self.assertEqual(d.calls, ['control_status'])

    def test_foreground_and_ownership_changes_fail_closed(self):
        for mode in ('focus_change', 'revision_change', 'stalled', 'stale_capture', 'app_restart', 'control_restart', 'late_input', 'endpoint_change'):
            with self.subTest(mode=mode):
                report, d, _ = self.run_case(mode)
                self.assertEqual(report['result'], 'blocked'); self.assertNotIn('launch', d.calls)
                self.assertIn('power_end', d.calls)

    def test_different_vita_endpoints_refuse_before_device_requests(self):
        report, d, _ = self.run_case('wrong_endpoint')
        self.assertEqual(report['result'], 'blocked'); self.assertEqual(d.calls, [])

    def test_real_device_endpoint_pin_rejects_host_or_config_changes(self):
        from types import SimpleNamespace
        from workbench.runner import Device as ActualDevice
        from resident.control.bridge_tools import ControlClient
        d = ActualDevice.__new__(ActualDevice)
        fg = {'host': '127.0.0.1', 'port': 17865, 'token': 'd'*32}
        control = {'host': '127.0.0.1', 'port': 17866, 'token': 'e'*32}
        d.foreground = SimpleNamespace(configuration=lambda: dict(fg))
        d.control = ControlClient(lambda: dict(control))
        d.validate_devloop_endpoint()
        fg['host'] = '127.0.0.2'
        with self.assertRaisesRegex(RuntimeError, 'same Vita'): d.validate_devloop_endpoint()
        fg['host'] = control['host']; fg['token'] = 'f'*32
        with self.assertRaisesRegex(RuntimeError, 'changed'): d.validate_devloop_endpoint()

    def test_native_target_mapping_is_required_for_input_readiness(self):
        report, _, _ = self.run_case('background_pid')
        self.assertEqual(report['result'], 'runtime_ready_target_unverified')
        self.assertTrue(report['ready_for_script_reload']); self.assertFalse(report['ready_for_input_trial'])
        self.assertFalse(report['ready_for_lua_trial'])
        report, _, _ = self.run_case('mapped')
        self.assertEqual(report['result'], 'ready'); self.assertTrue(report['ready_for_input_trial'])
        self.assertTrue(report['ready_for_lua_trial'])
        self.assertEqual(report['runtime_identity']['build_id'],'c'*64)

    def test_native_run_build_and_candidate_pin_are_rechecked(self):
        for mode in ('native_run_change','native_build_change','native_bad_run','native_bad_pid','native_script_run'):
            with self.subTest(mode=mode):
                report,d,_=self.run_case(mode)
                self.assertEqual(report['result'],'blocked');self.assertFalse(report['ready_for_input_trial'])
                self.assertNotIn('launch',d.calls)
        report,d,_=self.run_case('mapped',expected_devloop_build='b'*64)
        self.assertEqual(report['result'],'blocked');self.assertNotIn('power_start',d.calls)
        report,_,_=self.run_case('mapped',expected_devloop_build='c'*64)
        self.assertEqual(report['result'],'ready')
        report,_,_=self.run_case('mapped',expected_devloop_build=None)
        self.assertEqual(report['result'],'runtime_ready_build_unpinned');self.assertTrue(report['ready_for_script_reload'])
        self.assertFalse(report['ready_for_input_trial']);self.assertFalse(report['native_candidate_pin_verified'])
        report,_,_=self.run_case('legacy_script')
        self.assertTrue(report['ready_for_script_reload']);self.assertFalse(report['ready_for_input_trial'])

    def test_native_target_mapping_rejects_missing_wrong_or_boolean_pid(self):
        from workbench.runner import require_input_target
        state={'app':'Vita DevLoop','version':'01.04','title_id':'CHRS00003','pid':77}
        self.assertEqual(require_input_target(state,{'target_pid':77}),77)
        for changed in ({'pid':None},{'pid':True},{'pid':-1},{'title_id':'OTHERAPP'},{'pid':88},{'version':'01.03'}):
                with self.subTest(changed=changed),self.assertRaises(RuntimeError):require_input_target({**state,**changed},{'target_pid':77})

    def test_frozen_endpoint_used_for_launch_heartbeat_and_cleanup_after_drift(self):
        from types import SimpleNamespace
        from workbench.runner import Device as ActualDevice
        from workbench.power import WorkKeeper as ActualKeeper
        from resident.control.bridge_tools import ControlClient
        foreground={'host':'127.0.0.1','port':17865,'token':'d'*32}
        control={'host':'127.0.0.1','port':17866,'token':'e'*32}
        d=ActualDevice.__new__(ActualDevice)
        d.foreground=SimpleNamespace(configuration=lambda:dict(foreground))
        d.control=ControlClient(lambda:dict(control));d.control.abi=2;sent=[]
        class Connection:
            def __init__(self,host,port,timeout):self.host=host;self.port=port
            def request(self,method,path,body=None,headers=None):
                self.path=path;self.body=body;sent.append((self.host,self.port,method,path,headers['Authorization']))
            def getresponse(self):return self
            status=200
            def getheader(self,name,default=''):return 'application/json'
            def read(self,limit):
                if self.path.startswith('/app/'):
                    return json.dumps({'title_id':'CHRS00003','action':'launch','native_result':0}).encode()
                import struct
                ttl=struct.unpack('<5I',self.body)[2]
                return json.dumps({'app':'Vita Work Power','abi':2,'lease_remaining_ms':ttl,'dimmed':False}).encode()
            def close(self):pass
        with patch.dict(os.environ,{'VITA_CONTROL_PORT':'17867'}),tempfile.TemporaryDirectory() as folder:
            d.validate_devloop_endpoint()
            foreground.update(host='127.0.0.2',token='f'*32);control.update(host='127.0.0.2',token='a'*32)
            os.environ['VITA_CONTROL_PORT']='19999'
            self.assertEqual(d.foreground.configuration()['host'],'127.0.0.1')
            with patch('http.client.HTTPConnection',Connection):
                d.launch_devloop();keeper=ActualKeeper(d.control,Path(folder));keeper.send(30000);keeper.send(0)
            self.assertTrue(all(row[0:2]==('127.0.0.1',17867) and row[4]=='Bearer '+'e'*32 for row in sent))
            self.assertEqual(len(sent),3)
            self.assertNotIn('e'*32,(Path(folder)/'power.jsonl').read_text(encoding='utf-8'))
            with self.assertRaisesRegex(RuntimeError,'changed'):d.validate_devloop_endpoint()

    def test_invalid_effective_port_refused_before_network(self):
        from types import SimpleNamespace
        from workbench.runner import Device as ActualDevice
        from resident.control.bridge_tools import ControlClient
        d=ActualDevice.__new__(ActualDevice)
        d.foreground=SimpleNamespace(configuration=lambda:{'host':'127.0.0.1','port':17865,'token':'d'*32})
        d.control=ControlClient(lambda:{'host':'127.0.0.1','port':17866,'token':'e'*32})
        with patch.dict(os.environ,{'VITA_CONTROL_PORT':'65536'}),patch('http.client.HTTPConnection') as connection:
            with self.assertRaises(ValueError):d.validate_devloop_endpoint()
            connection.assert_not_called()

    def test_invalid_pins_or_bounds_are_refused_before_device_construction(self):
        for kwargs in ({'expected_control_build': 'bad'}, {'expected_devloop_version': '01.99'}, {'expected_devloop_build':'bad'}, {'timeout_s': True}, {'timeout_s': 61}):
            with self.subTest(kwargs=kwargs), patch.object(p, 'Device') as constructor:
                args = {'expected_control_build': BUILD, **kwargs}
                with self.assertRaises(ValueError): p.prepare(**args)
                constructor.assert_not_called()

    def test_competing_session_refuses_before_device_construction(self):
        with patch.object(p, 'Device') as constructor, patch.object(p, 'exclusive', side_effect=RuntimeError('fixture session owned')):
            with self.assertRaises(RuntimeError): p.prepare(BUILD)
            constructor.assert_not_called()

    def test_intent_commit_failure_does_not_submit_launch(self):
        d = Device('absent'); clock = Clock()
        actual_event = p.Journal.event
        def event(journal, kind, fields):
            if kind == 'mutation_intent': raise PermissionError('fixture journal intent failure')
            return actual_event(journal, kind, fields)
        with tempfile.TemporaryDirectory() as folder, patch.object(p, 'time', clock), patch.object(p, 'WorkKeeper', Keeper), patch.object(p.Journal, 'event', event):
            report = p.prepare(BUILD,expected_devloop_version='01.03', timeout_s=2, device=d, root=Path(folder))
        self.assertEqual(report['result'], 'blocked'); self.assertEqual(report['launch_submissions'], 0)
        self.assertNotIn('launch', d.calls)

    def test_cli_prepare_arguments_and_blocked_exit(self):
        from workbench import cli
        for result, script_ready, input_ready, script_only, code in (('ready',True,True,False,0),('blocked',False,False,False,1),('runtime_ready_target_unverified',True,False,False,1),('runtime_ready_target_unverified',True,False,True,0)):
            argv=['workbench.cli','prepare',BUILD,'--version','01.02','--timeout','2']+(['--script-only'] if script_only else [])
            with self.subTest(result=result,script_only=script_only), patch('sys.argv',argv), patch.object(cli, 'prepare', return_value={'result':result,'ready_for_script_reload':script_ready,'ready_for_input_trial':input_ready}) as call, redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(), code)
                call.assert_called_once_with(BUILD, '01.02', 2,expected_devloop_build=None)


if __name__ == '__main__': unittest.main(verbosity=2)
