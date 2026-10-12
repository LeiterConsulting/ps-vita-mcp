"""Real local HTTP/foreground client fixtures; no physical Vita acceptance."""
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs
from unittest.mock import patch

from workbench import script_session as session
from workbench.session import exclusive

BUILD = 'a' * 64
RUN = 'b' * 32
TOKEN = 'c' * 32
PIN = {'app': 'Vita DevLoop', 'protocol': 1, 'version': '01.04', 'title_id': 'CHRS00003',
       'pid': 77, 'run': RUN, 'build_id': BUILD}
WORLD = {'parameters': {'gravity': 500, 'drag': 1}, 'ball': {'x': 20, 'y': 30},
         'score': 4, 'added_obstacles': 2, 'mode': 'tilt+stick'}


def candidate(name='one', value=2, **extra):
    source = ('-- score=%s\nlocal n=0\nreturn {update=function(dt,input) n=n+1;'
              'vita.metric("score",%s); vita.metric("ticks",n) end,draw=function() end}') % (value, value)
    return {'name': name, 'source': source, 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'duration_s': .25, 'warmup_s': 0, 'checks': [{'metric': 'score', 'min': 1}], **extra}


def replace_source(item, source):
    return {**item, 'source': source, 'source_sha256': hashlib.sha256(source.encode()).hexdigest()}


class Clock:
    def __init__(self): self.now = 0
    def monotonic(self): return self.now
    def sleep(self, seconds): self.now += seconds


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'VITA_WORKBENCH_LOCK': str(self.root / 'lock')})
        self.env.start()
        self.config = {}
        self.clock = Clock()
        self.posts = []
        self.gets = []
        self.intent_counts = []
        self.rev = 10
        self.frame = 100
        self.ms = 1000
        self.paused = True
        self.identity = dict(PIN)
        self.world = copy.deepcopy(WORLD)
        self.current = None
        self.previous = None
        self.drop_operation = None
        self.drop_before = False
        self.dropped = False
        self.edit_after = None
        self.edited = False
        self.drift_after = None
        self.auth_ok = True
        self.stall = False
        self.stall_updates = False
        self.runtime_drift_after = None
        self.bad_receipt = False
        self.fault_on_get_after = None
        self.forced_fault = False
        self.fault_revision_delta = 1
        self.incoming = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass

            def authorized(self):
                owner.incoming.append(self.headers.get('Authorization'))
                if not owner.auth_ok or self.headers.get('Authorization') != 'Bearer ' + TOKEN:
                    self.reply({'error': 'private device supplied text ' + TOKEN}, 401)
                    return False
                return True

            def do_GET(self):
                if not self.authorized(): return
                owner.gets.append(self.path)
                if (owner.fault_on_get_after is not None and len(owner.posts) >= owner.fault_on_get_after and
                        owner.current and owner.current['active'] and not owner.forced_fault):
                    owner.current['faulted'] = True
                    owner.paused = True
                    owner.rev += owner.fault_revision_delta
                    owner.forced_fault = True
                if owner.edit_after is not None and len(owner.posts) >= owner.edit_after and not owner.edited:
                    owner.rev += 7
                    owner.current = owner.vm('other_editor', b'other editor source', 99)
                    owner.paused = True
                    owner.edited = True
                if owner.runtime_drift_after is not None and len(owner.posts) >= owner.runtime_drift_after:
                    owner.identity['run'] = 'e' * 32
                self.reply(owner.snapshot(self.path == '/script'))

            def do_POST(self):
                if not self.authorized(): return
                raw = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                fields = parse_qs(raw.decode()) if self.path == '/control' else {}
                action = fields.get('action', ['load'])[0]
                owner.posts.append((self.path, action, raw))
                events = []
                for path in owner.root.glob('evidence/workbench/*/journal.jsonl'):
                    events.extend(json.loads(line) for line in path.read_text().splitlines())
                owner.intent_counts.append(sum(e['kind'] == 'mutation_intent' for e in events))
                if owner.drop_operation == action and owner.drop_before and not owner.dropped:
                    return self.drop()
                revision = int(self.headers['X-DevLoop-Revision']) if self.path == '/script' else int(fields['expected_revision'][0])
                if revision != owner.rev: return self.reply({'error': 'revision conflict'}, 409)
                if self.path == '/script':
                    if raw.startswith(b'bad syntax'): return self.reply({'error': 'compile rejected ' + TOKEN}, 422)
                    score = float(raw.split(b'score=', 1)[1].splitlines()[0]) if b'score=' in raw else 2
                    owner.previous = owner.current
                    owner.current = owner.vm(self.headers['X-DevLoop-Script-Name'], raw, score)
                    owner.paused = True
                elif action == 'resume': owner.paused = False
                elif action == 'pause': owner.paused = True
                elif action == 'native':
                    if owner.current: owner.current['active'] = False
                    owner.paused = True
                elif action == 'script_rollback':
                    if not owner.previous or owner.previous['faulted']:
                        return self.reply({'error': 'no healthy rollback'}, 409)
                    owner.current, owner.previous = owner.previous, owner.current
                    owner.current['active'] = True
                    owner.paused = True
                else: return self.reply({'error': 'unknown action'}, 400)
                owner.rev += 1
                if owner.drift_after is not None and len(owner.posts) >= owner.drift_after:
                    owner.config.update(host='127.0.0.2', port=1, token='f' * 32)
                if owner.drop_operation == action and not owner.dropped: return self.drop()
                result = owner.snapshot(action in ('load', 'native', 'script_rollback'))
                if owner.bad_receipt: result['revision'] += 10
                self.reply(result)

            def drop(self):
                owner.dropped = True
                self.close_connection = True
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()

            def reply(self, value, code=200):
                raw = json.dumps(value).encode()
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.config.update(host='127.0.0.1', port=self.http.server_port, token=TOKEN)
        self.device = session.ForegroundDevice()
        self.device.foreground.configuration = lambda: dict(self.config)

    def tearDown(self):
        self.device.close_endpoint()
        self.http.shutdown()
        self.http.server_close()
        self.env.stop()
        self.temp.cleanup()

    def vm(self, name, raw, score):
        return {'loaded': True, 'active': True, 'faulted': False, 'name': name,
                'sha256': hashlib.sha256(raw).hexdigest(), 'source_bytes': len(raw),
                'updates': 0, 'metrics': {'score': score, 'ticks': 0}, '_source': raw}

    def baseline_lua(self, active=True):
        self.current = self.vm('original', b'original VM source', 123)
        self.current.update(active=active, updates=432, metrics={'score': 123, 'ticks': 432})

    def snapshot(self, script=False):
        if not self.stall:
            self.frame += 1
            self.ms += 16
        if self.current and self.current['active'] and not self.paused and not self.stall_updates:
            self.current['updates'] += 1
            self.current['metrics']['ticks'] = self.current['updates']
            if b'runtime fault' in self.current['_source'] and self.current['updates'] >= 4:
                self.current['faulted'] = True
                self.paused = True
                self.rev += 1
        state = {**self.identity, **self.world, 'revision': self.rev, 'frame': self.frame,
                 'sampled_ms': self.ms, 'paused': self.paused,
                 'experiment': 'lua' if self.current and self.current['active'] else 'tilt_playground'}
        if not script: return state
        current = {k: v for k, v in self.current.items() if not k.startswith('_')} if self.current else {
            'loaded': False, 'active': False, 'faulted': False, 'name': '', 'sha256': '', 'source_bytes': 0,
            'updates': 0, 'metrics': {}}
        return {**state, **current, 'rollback_available': bool(self.previous and not self.previous['faulted']),
                'previous_sha256': self.previous['sha256'] if self.previous else '',
                'previous_name': self.previous['name'] if self.previous else ''}

    def run_job(self, candidates=None, **kwargs):
        with patch.object(session, 'time', self.clock):
            report = session.run_session(candidates or [candidate()], BUILD, 77, RUN,
                                         kwargs.pop('expected_revision', 10), device=self.device, root=self.root, **kwargs)
        folder = Path(report['evidence_directory'])
        self.events = [json.loads(line) for line in (folder / 'journal.jsonl').read_text().splitlines()] if (folder / 'journal.jsonl').exists() else []
        self.assertEqual(json.loads((folder / 'report.json').read_text())['result'], report['result'])
        self.assertNotIn(TOKEN, json.dumps(report))
        self.assertNotIn('127.0.0.1', json.dumps(report))
        self.assertNotIn('source"', json.dumps(report))
        self.assertTrue(all(count >= index for index, count in enumerate(self.intent_counts, 1)))
        return report

    def test_iterate_rank_and_restore_original_lua_state_between_candidates(self):
        self.baseline_lua()
        original = copy.deepcopy(self.current)
        result = self.run_job([candidate('low', 2), candidate('high', 7)], selection={'metric': 'score', 'direction': 'max'})
        self.assertEqual(result['result'], 'passed', result)
        self.assertEqual(result['best']['name'], 'high')
        self.assertEqual([i['result'] for i in result['iterations']], ['accepted', 'accepted'])
        self.assertEqual(self.current, original)
        self.assertTrue(self.paused)
        self.assertEqual(sum(action == 'script_rollback' for _, action, _ in self.posts), 2)
        self.assertEqual(result['restoration'], 'original_scene_paused_verified')
        self.assertTrue(all(i['last_frame'] > i['first_frame'] and i['last_updates'] > i['first_updates'] for i in result['iterations']))

    def test_native_scene_restored_world_unchanged_last_lua_inactive(self):
        result = self.run_job([candidate('first'), candidate('second')])
        self.assertEqual(result['result'], 'passed', result)
        self.assertEqual(result['best']['name'], 'first')
        self.assertFalse(self.current['active'])
        self.assertTrue(self.paused)
        self.assertEqual(self.world, WORLD)
        self.assertEqual(result['input_actions'], 0)
        self.assertEqual(result['control_actions'], 0)

    def test_inactive_original_lua_restored_inactive_with_original_state(self):
        self.baseline_lua(active=False)
        original = copy.deepcopy(self.current)
        result = self.run_job([candidate('first'), candidate('second')])
        self.assertEqual(result['result'], 'passed', result)
        self.assertEqual(self.current, original)
        self.assertTrue(self.paused)

    def test_identical_source_and_name_still_restores_original_vm_not_fresh_copy(self):
        self.baseline_lua()
        original = copy.deepcopy(self.current)
        identical = replace_source(candidate('original'), self.current['_source'].decode())
        result = self.run_job([identical])
        self.assertEqual(result['result'], 'passed', result)
        self.assertEqual(self.current, original)
        self.assertEqual(sum(action == 'script_rollback' for _, action, _ in self.posts), 1)

    def test_explicit_retain_best_fresh_vm_paused_not_remeasured(self):
        self.baseline_lua()
        result = self.run_job([candidate('high', 7), candidate('low', 2)], retain_best=True,
                              selection={'metric': 'score', 'direction': 'min'})
        self.assertEqual(result['result'], 'passed', result)
        self.assertEqual(result['best']['name'], 'low')
        self.assertEqual(self.current['name'], 'low')
        self.assertEqual(self.current['updates'], 0)
        self.assertTrue(self.paused)
        self.assertEqual(self.previous['name'], 'original')
        self.assertEqual(result['restoration'], 'best_source_retained_fresh_vm_paused')

    def test_metric_failure_and_missing_metric_never_pass(self):
        result = self.run_job([candidate('fails', checks=[{'metric': 'score', 'min': 99}]),
                               candidate('absent', checks=[{'metric': 'not_present', 'equals': 0}])])
        self.assertEqual(result['result'], 'failed_checks')
        self.assertIsNone(result['best'])
        self.assertFalse(self.current['active'])
        self.assertIsNone(result['iterations'][1]['checks'][0]['actual'])

    def test_selection_missing_metric_does_not_retain_candidate(self):
        result = self.run_job(retain_best=True, selection={'metric': 'missing', 'direction': 'max'})
        self.assertEqual(result['result'], 'failed_checks')
        self.assertEqual(result['iterations'][0]['result'], 'selection_metric_missing')
        self.assertFalse(self.current['active'])

    def test_syntax_rejected_without_revision_change_then_next_candidate_runs(self):
        self.baseline_lua()
        original = copy.deepcopy(self.current)
        bad = replace_source(candidate('bad'), 'bad syntax')
        result = self.run_job([bad, candidate('valid')])
        self.assertEqual(result['result'], 'passed', result)
        self.assertEqual(result['iterations'][0]['result'], 'syntax_or_preflight_rejected')
        self.assertEqual(result['iterations'][1]['result'], 'accepted')
        self.assertEqual(self.current, original)
        self.assertEqual(sum(action == 'load' for _, action, _ in self.posts), 2)

    def test_runtime_fault_owned_single_revision_restores_then_next_candidate(self):
        self.baseline_lua()
        original = copy.deepcopy(self.current)
        bad = replace_source(candidate('fault'), candidate('fault')['source'] + '\n-- runtime fault')
        result = self.run_job([bad, candidate('valid')])
        self.assertEqual(result['result'], 'passed', result)
        self.assertEqual(result['iterations'][0]['result'], 'runtime_fault')
        self.assertEqual(result['iterations'][1]['result'], 'accepted')
        self.assertEqual(self.current, original)

    def test_runtime_fault_with_native_baseline_restores_native_even_with_faulted_inactive_vm(self):
        bad = replace_source(candidate('fault'), candidate('fault')['source'] + '\n-- runtime fault')
        result = self.run_job([bad])
        self.assertEqual(result['result'], 'failed_checks', result)
        self.assertEqual(result['iterations'][0]['result'], 'runtime_fault')
        self.assertEqual(result['restoration'], 'original_scene_paused_verified')
        self.assertFalse(self.current['active'])
        self.assertTrue(self.current['faulted'])
        self.assertTrue(self.paused)

    def test_fault_after_load_before_resume_recovers_without_stale_resume(self):
        self.fault_on_get_after = 1
        result = self.run_job()
        self.assertEqual(result['result'], 'failed_checks', result)
        self.assertEqual(result['iterations'][0]['result'], 'runtime_fault')
        self.assertEqual([action for _, action, _ in self.posts], ['load', 'native'])
        self.assertFalse(self.current['active'])

    def test_fault_without_native_revision_increment_is_not_adopted(self):
        self.fault_on_get_after = 1
        self.fault_revision_delta = 0
        result = self.run_job()
        self.assertEqual(result['failure_code'], 'scene_ownership_changed')
        self.assertEqual(len(self.posts), 1)

    def test_lost_load_response_reconciles_get_only_no_replay_or_cleanup(self):
        self.drop_operation = 'load'
        result = self.run_job([candidate('first'), candidate('second')])
        self.assertEqual(result['result'], 'unconfirmed', result)
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(result['reconciliation'], 'expected_post_state_observed')
        self.assertEqual(result['restoration'], 'skipped_unconfirmed_or_drifted_no_further_mutation')
        self.assertTrue(self.current['active'])
        self.assertTrue(self.paused)
        self.assertFalse(next(e for e in self.events if e['kind'] == 'read_only_reconciliation')['ownership_adopted'])

    def test_disconnect_before_load_application_never_retries(self):
        self.drop_operation = 'load'
        self.drop_before = True
        result = self.run_job()
        self.assertEqual(result['result'], 'unconfirmed')
        self.assertEqual(result['reconciliation'], 'different_state_observed')
        self.assertEqual(len(self.posts), 1)
        self.assertIsNone(self.current)

    def test_lost_resume_reply_never_pause_or_rollback_running_scene(self):
        self.drop_operation = 'resume'
        result = self.run_job()
        self.assertEqual(result['result'], 'unconfirmed', result)
        self.assertEqual([action for _, action, _ in self.posts], ['load', 'resume'])
        self.assertFalse(self.paused)
        self.assertEqual(result['reconciliation'], 'expected_post_state_observed')

    def test_lost_restore_reply_is_not_replayed(self):
        self.drop_operation = 'native'
        result = self.run_job()
        self.assertEqual(result['result'], 'unconfirmed', result)
        self.assertEqual([action for _, action, _ in self.posts], ['load', 'resume', 'pause', 'native'])
        self.assertFalse(self.current['active'])

    def test_invalid_mutation_acknowledgement_get_only_and_stop(self):
        self.bad_receipt = True
        result = self.run_job()
        self.assertEqual(result['result'], 'unconfirmed', result)
        self.assertEqual(len(self.posts), 1)

    def test_concurrent_editor_revision_and_source_never_overwritten(self):
        self.edit_after = 2
        result = self.run_job()
        self.assertEqual(result['result'], 'blocked', result)
        self.assertEqual(result['failure_code'], 'scene_ownership_changed')
        self.assertEqual(self.current['name'], 'other_editor')
        self.assertEqual(len(self.posts), 2)
        self.assertIn('skipped', result['restoration'])

    def test_other_editor_same_source_new_revision_never_rolled_back(self):
        actual = self.device.script
        changed = False
        def script():
            nonlocal changed
            if len(self.posts) >= 2 and not changed:
                self.rev += 2
                changed = True
            return actual()
        self.device.script = script
        result = self.run_job()
        self.assertEqual(result['failure_code'], 'script_snapshot_invalid')
        self.assertEqual(len(self.posts), 2)
        self.assertTrue(self.current['active'])

    def test_endpoint_changes_after_mutation_stops_on_frozen_host(self):
        self.drift_after = 1
        result = self.run_job()
        self.assertEqual(result['result'], 'blocked', result)
        self.assertEqual(result['failure_code'], 'endpoint_configuration_changed')
        self.assertEqual(len(self.posts), 1)
        self.assertTrue(all(v == 'Bearer ' + TOKEN for v in self.incoming))

    def test_endpoint_changes_inside_send_cannot_redirect_mutation(self):
        actual = self.device.load
        def load(*args):
            self.config.update(host='127.0.0.2', port=1, token='f' * 32)
            return actual(*args)
        self.device.load = load
        result = self.run_job()
        self.assertEqual(result['result'], 'blocked', result)
        self.assertEqual(len(self.posts), 1)
        self.assertTrue(all(v == 'Bearer ' + TOKEN for v in self.incoming))

    def test_prefrozen_foreground_device_is_reusable_and_checks_drift(self):
        frozen = self.device.freeze_endpoint()
        self.assertEqual(frozen['port'], self.http.server_port)
        result = self.run_job()
        self.assertEqual(result['result'], 'passed', result)
        self.config['token'] = 'f' * 32
        with self.assertRaisesRegex(session.SessionStopped, 'endpoint_configuration_changed'):
            self.device.status()
        self.device.close_endpoint()

    def test_invalid_endpoint_rejects_before_any_network(self):
        self.config['port'] = 0
        result = self.run_job()
        self.assertEqual(result['failure_code'], 'endpoint_configuration_invalid')
        self.assertEqual(self.gets, [])
        self.assertEqual(self.posts, [])

    def test_intent_journal_failure_cannot_send_mutation(self):
        actual = session.Journal.event
        def event(journal, kind, fields):
            if kind == 'mutation_intent': raise OSError(TOKEN)
            return actual(journal, kind, fields)
        with patch.object(session.Journal, 'event', event): result = self.run_job()
        self.assertEqual(result['result'], 'blocked')
        self.assertEqual(self.posts, [])

    def test_receipt_journal_failure_reconciles_get_only_without_resubmit(self):
        actual = session.Journal.event
        failed = False
        def event(journal, kind, fields):
            nonlocal failed
            if kind == 'mutation_receipt' and not failed:
                failed = True
                raise OSError(TOKEN)
            return actual(journal, kind, fields)
        with patch.object(session.Journal, 'event', event): result = self.run_job()
        self.assertEqual(result['result'], 'unconfirmed', result)
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(result['reconciliation'], 'expected_post_state_observed')

    def test_runtime_restart_stops_without_cleanup_to_new_run(self):
        self.runtime_drift_after = 1
        result = self.run_job()
        self.assertEqual(result['failure_code'], 'runtime_identity_changed_or_invalid')
        self.assertEqual(len(self.posts), 1)

    def test_running_baseline_and_wrong_revision_do_not_mutate(self):
        self.paused = False
        result = self.run_job()
        self.assertEqual(result['failure_code'], 'baseline_revision_changed_running_or_faulted')
        self.assertEqual(self.posts, [])
        self.paused = True
        result = self.run_job(expected_revision=11)
        self.assertEqual(result['failure_code'], 'baseline_revision_changed_running_or_faulted')
        self.assertEqual(self.posts, [])

    def test_wrong_pin_and_auth_errors_do_not_mutate_or_disclose_remote_text(self):
        self.identity['build_id'] = 'd' * 64
        result = self.run_job()
        self.assertEqual(result['failure_code'], 'runtime_identity_changed_or_invalid')
        self.assertEqual(self.posts, [])
        self.auth_ok = False
        result = self.run_job()
        self.assertEqual(result['failure_code'], 'transport_or_local_failure')
        self.assertNotIn('private device', json.dumps(result))
        self.assertEqual(self.posts, [])

    def test_stalled_frame_before_load_refuses(self):
        self.stall = True
        result = self.run_job()
        self.assertEqual(result['failure_code'], 'baseline_frame_not_advancing')
        self.assertEqual(self.posts, [])

    def test_stalled_updates_fail_without_fabricating_metrics_acceptance(self):
        self.stall_updates = True
        result = self.run_job()
        self.assertEqual(result['failure_code'], 'candidate_execution_not_advancing')
        self.assertEqual(result['result'], 'blocked')
        self.assertIsNone(result['best'])

    def test_existing_local_editor_lock_refuses_before_configuration_or_network(self):
        held = threading.Event()
        release = threading.Event()
        def editor():
            with exclusive():
                held.set()
                release.wait(5)
        thread = threading.Thread(target=editor)
        thread.start()
        self.assertTrue(held.wait(2))
        try:
            with self.assertRaisesRegex(RuntimeError, 'operation is in progress'):
                self.run_job()
        finally:
            release.set()
            thread.join(2)
        self.assertEqual(self.gets, [])
        self.assertEqual(self.posts, [])

    def test_invalid_plans_reject_before_any_network(self):
        bad_plans = [[], [candidate(extra=True)], [candidate(source_sha256='0' * 64)],
                     [candidate(duration_s=float('nan'))], [candidate(duration_s=True)],
                     [candidate(warmup_s=4)], [candidate(checks=[])],
                     [candidate(checks=[{'metric': 'score', 'min': True}])],
                     [candidate(checks=[{'metric': 'score', 'min': 2, 'max': 1}])],
                     [candidate(checks=[{'metric': 'score', 'min': 0, 'unknown': 1}])],
                     [candidate('same'), candidate('same')],
                     [candidate(str(i), duration_s=30, warmup_s=1) for i in range(4)]]
        for items in bad_plans:
            with self.subTest(items=[i.get('name') for i in items]):
                with self.assertRaises(ValueError):
                    session.run_session(items, BUILD, 77, RUN, 10, device=self.device, root=self.root)
        for kwargs in ({'expected_pid': True}, {'expected_run': 'bad'}, {'expected_devloop_build': 'bad'},
                       {'expected_revision': True}, {'retain_best': 1},
                       {'selection': {'metric': 'score', 'direction': 'max', 'extra': True}}):
            fields = dict(candidates=[candidate()], expected_devloop_build=BUILD, expected_pid=77,
                          expected_run=RUN, expected_revision=10, device=self.device, root=self.root)
            fields.update(kwargs)
            with self.assertRaises(ValueError): session.run_session(**fields)
        self.assertEqual(self.gets, [])
        self.assertEqual(self.posts, [])


if __name__ == '__main__': unittest.main(verbosity=2)
