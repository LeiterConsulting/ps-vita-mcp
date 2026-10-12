"""Real HTTP lifecycle decisions against an explicit simulated native adapter.

This does not qualify Vita promotion, launching, idle policy or filesystem
durability. Fixtures apply mutations once and can lose replies afterwards.
"""
from __future__ import annotations

import asyncio
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workbench.native_package import FILES, PROJECT, TITLE, canonical, load_candidate, make_head, sha, validate_head
from resident.lifecycle_client import LifecycleClient, LifecycleTransport
from workbench.native_lifecycle import preview, execute, reconcile

TOKEN, BUILD, INSTANCE, LAB_BUILD = 'd' * 32, 'a' * 64, 'b' * 32, 'c' * 64


def sfo():
    values = [('TITLE_ID', TITLE), ('APP_VER', '01.00'), ('CATEGORY', 'gd'),
              ('PSP2_SYSTEM_VER', 0x03650000)]
    keys, data, entries = bytearray(), bytearray(), []
    for name, value in values:
        key_offset = len(keys)
        keys.extend(name.encode() + b'\0')
        offset = len(data)
        raw = struct.pack('<I', value) if type(value) is int else value.encode() + b'\0'
        data.extend(raw)
        entries.append(struct.pack('<HHIII', key_offset, 0x404 if type(value) is int else 0x204,
                                   len(raw), len(raw), offset))
    start = 20 + 16 * len(values)
    return struct.pack('<5I', 0x46535000, 0x101, start, start + len(keys), len(values)) + b''.join(entries) + keys + data


def candidate(root):
    base = root / 'dist/native-lab'
    base.mkdir(parents=True, exist_ok=True)
    source = root / 'lab.c'
    source.write_bytes(b'/* explicitly simulated compiled input */\n')
    executable = bytearray(512)
    executable[:4] = b'SCE\0'
    struct.pack_into('<Q', executable, 0x38, 0x80)
    struct.pack_into('<Q', executable, 0x40, 0xa0)
    struct.pack_into('<Q', executable, 0x58, 0x140)
    struct.pack_into('<Q', executable, 0x80, 0x2f00000000000001)
    executable[0xa0:0xa7] = b'\x7fELF\x01\x01\x01'
    struct.pack_into('<H', executable, 0xa0 + 18, 40)
    struct.pack_into('<HH', executable, 0xa0 + 42, 32, 1)
    marker = ('VITA_NATIVE_LIFECYCLE_LAB:' + LAB_BUILD).encode('ascii')
    struct.pack_into('<QQQQ', executable, 0x140, 0x180, len(marker), 1, 2)
    executable[0x180:0x180 + len(marker)] = marker
    files = [bytes(executable), sfo(), (ROOT / 'assets/vita_devloop/icon0.png').read_bytes(),
             (ROOT / 'assets/vita_devloop/bg.png').read_bytes(), (ROOT / 'assets/vita_devloop/startup.png').read_bytes(),
             (ROOT / 'assets/template.xml').read_bytes(), b'Simulated fixture license\n']
    with zipfile.ZipFile(base / 'native_lab.vpk', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in zip(FILES, files):
            archive.writestr(name, data)
    payload = (base / 'native_lab.vpk').read_bytes()
    report = {'project': PROJECT, 'title_id': TITLE, 'version': '01.00', 'native_build_id': LAB_BUILD,
              'package': {'file': 'native_lab.vpk', 'bytes': len(payload), 'sha256': sha(payload)},
              'native_source_hashes': {'lab.c': sha(source.read_bytes())}}
    (base / 'build-report.json').write_bytes(canonical(report))
    return report['package']['sha256']


class Fixture:
    def __init__(self):
        self.calls = []
        self.stage = None
        self.files = {}
        self.operations = {}
        self.clock = 1000
        self.running = False
        self.frame = 1
        self.run_counter = 0
        self.revision = 1
        self.exit_expected_revision = 0
        self.instance = INSTANCE
        self.mode = ''
        self.dropped = set()
        self.idle = True
        self.checksum = 42

    def guard(self):
        return {'ready': self.idle and not self.running, 'result': 0, 'enumeration_result': 0,
                'occupied_slots': int(self.running), 'state_result': 0, 'system_events': 0,
                'app_events': 0, 'overlay': 0, 'state_samples_required': 2,
                'snapshot_atomic': False, 'foreground_verified': False,
                'protected_ui_verified': False, 'policy': 'idle_shell_only'}

    def status(self):
        self.clock += 10
        return {'app': 'Vita Native Lifecycle', 'protocol': 1, 'resident_build_id': BUILD,
                'instance_id': self.instance, 'project': PROJECT, 'title_id': TITLE,
                'clock_ms': self.clock, 'blocked': False, 'active_attempt': None,
                'policy': 'conservative_idle_only', 'max_file_bytes': 8 * 1024 * 1024,
                'max_total_bytes': 16 * 1024 * 1024, 'guard': self.guard(),
                'installer': {'paf_result': 0, 'promoter_result': 0, 'ready': True}}

    def staged(self):
        manifest = copy.deepcopy(self.stage)
        return {'app': 'Vita Native Lifecycle', 'protocol': 1, 'stage_attempt': manifest['attempt'],
                'manifest_sha256': sha(canonical(manifest)), 'manifest': manifest,
                'files': [{'index': index, 'published': index in self.files, 'verified': index in self.files}
                          for index in range(8)], 'complete': len(self.files) == 8, 'snapshot_atomic': False}

    def lab(self):
        self.frame += 1
        return {'app': 'Vita Native Lifecycle Lab', 'protocol': 1, 'title_id': TITLE, 'version': '01.00',
                'native_build_id': LAB_BUILD, 'pid': 100 + self.run_counter, 'run': f'{self.run_counter:032x}',
                'revision': self.revision, 'frame': self.frame, 'sampled_ms': self.frame * 16,
                'paused': True, 'selftest_passed': self.mode != 'selftest_failure',
                'checksum': self.checksum, 'exiting': False, 'variant': 1,
                'exit_expected_revision': self.exit_expected_revision, 'exit_response_complete': False}

    def handler(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, value, code=200, drop=''):
                if drop and owner.mode == drop and drop not in owner.dropped:
                    owner.dropped.add(drop)
                    self.close_connection = True
                    return
                data = canonical(value)
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def auth(self):
                owner.calls.append((self.command, self.path))
                if self.headers.get('Authorization') != 'Bearer ' + TOKEN:
                    self.reply({'error': TOKEN}, 403)
                    return False
                return True

            def do_GET(self):
                if not self.auth():
                    return
                if self.path == '/native-lifecycle/status':
                    return self.reply(owner.status())
                if self.path == '/devloop-launch/inventory':
                    owner.clock += 1
                    entries = [{'app_id': 10, 'pid': 100 + owner.run_counter, 'title_id': TITLE, 'resolved': True}]
                    if owner.mode == 'inventory_mismatch':
                        entries[0]['pid'] += 1
                    if owner.mode == 'inventory_unresolved':
                        entries[0].update(title_id=None, resolved=False)
                    if owner.mode == 'inventory_other_app':
                        entries.append({'app_id': 11, 'pid': 999, 'title_id': 'OTHER0001', 'resolved': True})
                    return self.reply({'app': 'Vita Resident Launch Inventory', 'protocol': 1,
                                       'sampled_ms': owner.clock, 'available': True, 'enumeration_result': 0,
                                       'capacity': 16, 'snapshot_atomic': False, 'foreground_verified': False,
                                       'protected_ui_verified': False, 'native_submission_enabled': False,
                                       'entries': entries, 'entries_reported': len(entries), 'capacity_limited': True,
                                       'launch_policy': 'unqualified_disabled'})
                if self.path == '/status':
                    if not owner.running or owner.mode == 'runtime_unavailable':
                        self.close_connection = True
                        return
                    result = owner.lab()
                    if owner.mode == 'wrong_build':
                        result['native_build_id'] = '9' * 64
                    if owner.mode == 'runtime_drift' and owner.frame > 4:
                        result['run'] = '8' * 32
                    return self.reply(result)
                if self.path.startswith('/native-lifecycle/stage/'):
                    if owner.stage is None:
                        return self.reply({}, 404)
                    return self.reply(owner.staged())
                if self.path.startswith('/native-lifecycle/attempt/'):
                    value = owner.operations.get(self.path.rsplit('/', 1)[1])
                    return self.reply(value or {}, 200 if value else 404)
                return self.reply({}, 404)

            def do_POST(self):
                if not self.auth():
                    return
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if self.path == '/native-lifecycle/stage':
                    owner.stage = request
                    return self.reply(owner.staged(), 201, 'drop_stage')
                if self.path == '/exit':
                    if owner.mode == 'exit_not_applied':
                        self.close_connection = True
                        return
                    owner.revision += 1
                    owner.exit_expected_revision = request['expected_revision']
                    result = owner.lab()
                    result.update(exiting=True, exit_response='acknowledged')
                    owner.running = False
                    return self.reply(result, 200, 'drop_exit')
                if self.path.endswith(('/install', '/launch')):
                    operation = self.path.rsplit('/', 1)[1]
                    state = 'installed_verified' if operation == 'install' else 'submitted'
                    result = {'app': 'Vita Native Lifecycle', 'protocol': 1, **request,
                              'stage_attempt': owner.stage['attempt'], 'operation': operation,
                              'expires_ms': request['issued_ms'] + request['ttl_ms'], 'state': state,
                              'dispatch_count': 1, 'native_result': 0, 'operation_result': 0,
                              'cleanup_result': 0, 'installed_verified': operation == 'install', 'native_invoked': True,
                              'may_have_effects': True}
                    result.pop('ttl_ms')
                    if operation == 'install':
                        if owner.mode == 'unknown_install':
                            result.update(state='unknown', installed_verified=False)
                        if owner.mode == 'pending_install':
                            result.update(state='running', installed_verified=False)
                        if owner.mode == 'restart_after_install':
                            owner.instance = '7' * 32
                    else:
                        owner.running = True
                        owner.run_counter += 1
                        owner.revision = 1
                        owner.exit_expected_revision = 0
                        owner.frame = 1
                    owner.operations[request['attempt']] = copy.deepcopy(result)
                    if owner.mode == 'bad_receipt':
                        result['attempt'] = '0' * 32
                    return self.reply(result, 202, 'drop_' + operation)
                return self.reply({}, 404)

            def do_PUT(self):
                if not self.auth():
                    return
                index = int(self.path.rsplit('/', 1)[1])
                data = self.rfile.read(int(self.headers['Content-Length']))
                info = owner.stage['files'][index]
                if len(data) != info['bytes'] or sha(data) != info['sha256'] or self.headers.get('X-SHA256') != info['sha256']:
                    return self.reply({}, 422)
                owner.files[index] = data
                return self.reply(owner.staged(), 201, 'drop_put')

        return Handler


class NativeLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.expected = candidate(self.root)
        self.fixture = Fixture()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), self.fixture.handler())
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.endpoint = {'host': '127.0.0.1', 'port': self.server.server_port, 'token': TOKEN}
        self.client = LifecycleClient(lambda: dict(self.endpoint))
        actual = self.client.request
        # Lab remains fixed port17868 in production. The test adapter redirects
        # only its own explicit lab connection to this OS-assigned fixture port.
        def request(method, path, raw=None, *, digest=None, lab=False):
            return actual(method, path, raw, digest=digest, lab=False)
        self.client.request = request
        self.env = patch.dict(os.environ, {'VITA_WORKBENCH_LOCK': str(self.root / 'lock')})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def plan(self, **kwargs):
        return preview(self.expected, client=self.client, root=self.root, **kwargs)

    def run_job(self, mode='', cycles=1):
        self.fixture.mode = mode
        prepared = self.plan(cycles=cycles, measurement_s=0.25, timeout_s=10)
        result = execute(prepared['plan'], prepared['plan_sha256'], client=self.client, root=self.root)
        self.assertNotIn(TOKEN, json.dumps(result))
        return result

    def writes(self):
        return [item for item in self.fixture.calls if item[0] != 'GET']

    def test_preview_has_no_device_writes(self):
        value = self.plan()
        self.assertTrue(value['ready'])
        self.assertEqual(value['plan_sha256'], sha(canonical(value['plan'])))
        self.assertEqual(self.writes(), [])

    def power_identity(self, **overrides):
        original = self.fixture.status
        def status():
            value = original()
            value.update(resident_version='0.1.6', keep_awake_protocol=1, keep_awake_port=17869)
            value.update(overrides)
            return value
        return patch.object(self.fixture, 'status', side_effect=status)

    def fake_keeper(self, *, fail_start=False, fail_fresh=None, fail_pending=False,
                    fail_after_exit=False, end='ended'):
        owner = self
        class Keeper:
            def __init__(self, *args, **kwargs):
                self.result = {'enabled': False, 'renewals': 0, 'errors': []}
                self.checks = self.fresh = self.stops = 0
                owner.power_keeper = self
            def start(self, *pins):
                # The lease worker's own instance is independent from the
                # native lifecycle instance. Only the shared build is passed.
                owner.assertEqual(pins, (BUILD,))
                owner.assertEqual(owner.writes(), [])
                if fail_start:
                    raise RuntimeError('fixture lease unavailable')
                self.result['enabled'] = True
            def check(self, *, fresh=False):
                self.checks += 1
                self.fresh += int(fresh)
                if fresh and self.fresh == fail_fresh:
                    raise RuntimeError('fixture heartbeat lost')
                if fail_pending and any(value['state'] in ('queued', 'dispatch_intent', 'running')
                                        for value in owner.fixture.operations.values()):
                    raise RuntimeError('fixture heartbeat lost during native dispatch')
                if fail_after_exit and ('POST', '/exit') in owner.fixture.calls:
                    raise RuntimeError('fixture heartbeat lost before native exit absence was confirmed')
            def stop(self):
                self.stops += 1
                self.result['end'] = end
                return self.result
        return patch('workbench.native_lifecycle.ResidentKeeper', Keeper)

    def test_resident016_requires_owned_lease_before_native_writes_and_ends_after_work(self):
        with self.power_identity(), self.fake_keeper():
            result = self.run_job()
        self.assertEqual(result['result'], 'passed')
        self.assertTrue(result['keep_awake']['enabled'])
        self.assertEqual(result['keep_awake']['end'], 'ended')
        self.assertEqual(self.power_keeper.stops, 1)
        self.assertEqual(self.power_keeper.fresh, len(self.writes()) + 1)

    def test_resident016_missing_lease_capability_refuses_without_native_writes(self):
        with self.power_identity(keep_awake_protocol=None), self.fake_keeper():
            result = self.run_job()
        self.assertEqual(result['result'], 'blocked')
        self.assertEqual(result['failure_code'], 'resident_keep_awake_capability_missing_or_invalid')
        self.assertEqual(self.writes(), [])
        self.assertFalse(hasattr(self, 'power_keeper'))

    def test_lease_start_failure_stops_native_effects_and_always_attempts_owned_end(self):
        with self.power_identity(), self.fake_keeper(fail_start=True):
            result = self.run_job()
        self.assertEqual(result['result'], 'blocked')
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.power_keeper.stops, 1)

    def test_lease_health_checkpoint_stops_before_next_native_effect(self):
        with self.power_identity(), self.fake_keeper(fail_fresh=3):
            result = self.run_job()
        self.assertEqual(result['result'], 'blocked')
        self.assertEqual(result['failure_code'], 'resident_keep_awake_no_longer_confirmed')
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(self.writes()[0], ('POST', '/native-lifecycle/stage'))
        self.assertEqual(self.power_keeper.stops, 1)

    def test_lease_release_uncertainty_is_reported_separately_from_completed_native_cycle(self):
        with self.power_identity(), self.fake_keeper(end='unconfirmed; fixture'):
            result = self.run_job()
        self.assertEqual(result['result'], 'unconfirmed')
        self.assertEqual(result['failure_code'], 'resident_keep_awake_end_unconfirmed')
        self.assertEqual(result['cycles'][0]['result'], 'passed')
        self.assertFalse(self.fixture.running)

    def test_lease_loss_during_async_native_install_retains_unknown_effect_without_replay(self):
        with self.power_identity(), self.fake_keeper(fail_pending=True):
            result = self.run_job('pending_install')
        self.assertEqual(result['result'], 'unconfirmed')
        self.assertEqual(result['failure_code'], 'install_pending_when_keep_awake_lost')
        self.assertIsNone(result['native_lab_left_running'])
        self.assertEqual(len([path for method, path in self.writes() if path.endswith('/install')]), 1)
        self.assertFalse(any(path.endswith('/launch') or path == '/exit' for method, path in self.writes()))
        self.assertEqual(self.power_keeper.stops, 1)

    def test_lease_loss_after_exit_ack_before_absence_is_unconfirmed_without_replay(self):
        with self.power_identity(), self.fake_keeper(fail_after_exit=True):
            result = self.run_job()
        self.assertEqual(result['result'], 'unconfirmed')
        self.assertEqual(result['failure_code'], 'resident_keep_awake_lost_during_native_effect')
        self.assertIsNone(result['native_lab_left_running'])
        self.assertEqual(len([path for method, path in self.writes() if path == '/exit']), 1)
        self.assertEqual(self.power_keeper.stops, 1)

    def test_two_complete_cycles_install_launch_evaluate_exit_and_redeploy(self):
        result = self.run_job(cycles=2)
        self.assertEqual(result['result'], 'passed')
        self.assertEqual([item['result'] for item in result['cycles']], ['passed', 'passed'])
        self.assertFalse(self.fixture.running)
        self.assertEqual(len([p for m, p in self.writes() if p.endswith('/install')]), 2)
        self.assertEqual(len([p for m, p in self.writes() if p.endswith('/launch')]), 2)
        self.assertEqual(len([p for m, p in self.writes() if p == '/exit']), 2)
        self.assertEqual(len(self.fixture.files), 8)
        self.assertNotEqual(result['cycles'][0]['evaluation']['runtime_identity']['run'],
                            result['cycles'][1]['evaluation']['runtime_identity']['run'])

    def test_lost_stage_file_install_launch_and_exit_replies_are_get_reconciled(self):
        for mode in ('drop_stage', 'drop_put', 'drop_install', 'drop_launch', 'drop_exit'):
            with self.subTest(mode=mode):
                self.fixture.mode = mode
                self.fixture.stage = None
                self.fixture.files.clear()
                self.fixture.calls.clear()
                result = self.run_job(mode)
                self.assertEqual(result['result'], 'passed')
                self.assertEqual(len(self.writes()), 12)
                self.assertIn('read_only_reconciliation', [event['kind'] for event in
                              json.loads((Path(result['evidence_directory']) / 'report.json').read_text())['events']])

    def test_unknown_install_stops_without_launch_exit_or_replay(self):
        result = self.run_job('unknown_install')
        self.assertEqual(result['result'], 'unconfirmed')
        self.assertEqual(len([p for m, p in self.writes() if p.endswith('/install')]), 1)
        self.assertFalse(any(p.endswith('/launch') or p == '/exit' for m, p in self.writes()))
        before = len(self.writes())
        observed = reconcile(result['plan']['job_id'], client=self.client, root=self.root)
        self.assertEqual(observed['operation_observations'][0]['state'], 'unknown')
        self.assertEqual(len(self.writes()), before)

    def test_reconcile_recovers_newer_fsynced_intents_than_stale_report(self):
        result = self.run_job()
        folder = Path(result['evidence_directory'])
        report = json.loads((folder / 'report.json').read_text())
        report.update(result='pending', events=[])
        for field in ('stage_attempt', 'manifest', 'manifest_sha256'):
            report.pop(field, None)
        (folder / 'report.json').write_bytes(canonical(report))
        # A crash can also leave an uncommitted partial trailing record. It must
        # not hide earlier complete durable operation identities or be adopted.
        with (folder / 'journal.jsonl').open('ab') as output:
            output.write(b'{"kind":"mutation_intent","operation":')
            output.flush()
            os.fsync(output.fileno())
        self.fixture.calls.clear()
        observed = reconcile(result['plan']['job_id'], client=self.client, root=self.root)
        self.assertEqual(observed['intent_source'], 'fsynced_journal_jsonl')
        self.assertTrue(observed['torn_final_record_ignored'])
        self.assertEqual(observed['durable_mutation_intents'], 12)
        self.assertEqual({item['attempt'] for item in observed['operation_observations']},
                         set(self.fixture.operations))
        self.assertEqual({path for method, path in self.fixture.calls if '/attempt/' in path},
                         {'/native-lifecycle/attempt/' + key for key in self.fixture.operations})
        self.assertEqual(self.writes(), [])

    def test_reconcile_refuses_changed_durable_operation_before_network(self):
        result = self.run_job()
        path = Path(result['evidence_directory']) / 'journal.jsonl'
        events = [json.loads(line) for line in path.read_text().splitlines()]
        intent = next(event for event in events if event['kind'] == 'mutation_intent'
                      and event['operation'] == 'install')
        intent['request']['manifest_sha256'] = '0' * 64
        path.write_bytes(b''.join(canonical(event) + b'\n' for event in events))
        self.fixture.calls.clear()
        with self.assertRaisesRegex(ValueError, 'durable operation'):
            reconcile(result['plan']['job_id'], client=self.client, root=self.root)
        self.assertEqual(self.fixture.calls, [])

    def test_actual_lab_fields_and_terminal_receipt_operation_are_strict(self):
        self.fixture.running = True
        self.fixture.run_counter = 1
        state = self.client.lab_status(LAB_BUILD, '01.00')
        self.assertEqual(state['variant'], 1)
        self.assertEqual(state['exit_expected_revision'], 0)
        self.assertFalse(state['exit_response_complete'])
        for field in ('variant', 'exit_expected_revision', 'exit_response_complete'):
            invalid = copy.deepcopy(state)
            invalid.pop(field)
            with self.subTest(missing=field), self.assertRaises(RuntimeError):
                self.client._lab(invalid, LAB_BUILD, '01.00')
        ack = self.client.lab_exit(state)
        self.assertEqual(ack['exit_expected_revision'], state['revision'])
        self.assertEqual(ack['revision'], state['revision'] + 1)
        self.assertFalse(ack['exit_response_complete'])
        self.fixture.calls.clear()
        result = self.run_job()
        install, launch = (result['cycles'][0][name + '_receipt'] for name in ('install', 'launch'))
        self.assertTrue(install['installed_verified'])
        self.assertFalse(launch['installed_verified'])
        for receipt in (install, launch):
            self.client._operation(receipt, None, None, None)
            for field, changed in (('operation', 'launch' if receipt['operation'] == 'install' else 'install'),
                                   ('installed_verified', not receipt['installed_verified'])):
                invalid = copy.deepcopy(receipt)
                invalid[field] = changed
                with self.subTest(state=receipt['state'], field=field), self.assertRaises(RuntimeError):
                    self.client._operation(invalid, None, None, None)

    def test_bad_receipt_never_adopts_or_replays(self):
        result = self.run_job('bad_receipt')
        self.assertEqual(result['result'], 'unconfirmed')
        self.assertEqual(len([p for m, p in self.writes() if p.endswith('/install')]), 1)
        self.assertFalse(any(p.endswith('/launch') for m, p in self.writes()))

    def test_resident_restart_stops_before_launch(self):
        result = self.run_job('restart_after_install')
        self.assertEqual(result['result'], 'blocked')
        self.assertFalse(any(p.endswith('/launch') for m, p in self.writes()))

    def test_wrong_runtime_build_never_exits_unowned_app(self):
        result = self.run_job('wrong_build')
        self.assertEqual(result['result'], 'blocked')
        self.assertTrue(self.fixture.running)
        self.assertIsNone(result['native_lab_left_running'])
        self.assertFalse(any(p == '/exit' for m, p in self.writes()))

    def test_submitted_launch_without_runtime_response_reports_unknown_no_exit_or_redeploy(self):
        result = self.run_job('runtime_unavailable', cycles=2)
        self.assertEqual(result['result'], 'unconfirmed')
        self.assertIsNone(result['native_lab_left_running'])
        self.assertIsNone(result['last_verified_runtime'])
        self.assertEqual(len([p for m, p in self.writes() if p.endswith('/launch')]), 1)
        self.assertEqual(len([p for m, p in self.writes() if p.endswith('/install')]), 1)
        self.assertFalse(any(p == '/exit' for m, p in self.writes()))

    def test_inventory_mismatch_unresolved_or_other_app_stops_before_exit(self):
        for mode in ('inventory_mismatch', 'inventory_unresolved', 'inventory_other_app'):
            with self.subTest(mode=mode):
                self.fixture.stage = None
                self.fixture.files.clear()
                self.fixture.calls.clear()
                self.fixture.running = False
                result = self.run_job(mode)
                self.assertEqual(result['result'], 'blocked')
                self.assertFalse(any(p == '/exit' for m, p in self.writes()))

    def test_selftest_failure_stops_without_fabricated_evaluation(self):
        result = self.run_job('selftest_failure')
        self.assertEqual(result['result'], 'failed_checks')
        self.assertNotIn('evaluation', result['cycles'][0])
        self.assertEqual(result['failed_test_cleanup']['result'], 'owned_runtime_exited')
        self.assertFalse(self.fixture.running)
        self.assertEqual(len([p for m, p in self.writes() if p == '/exit']), 1)
        self.assertEqual(len([p for m, p in self.writes() if p.endswith('/install')]), 1)

    def test_runtime_identity_drift_never_exits_an_unowned_runtime(self):
        result = self.run_job('runtime_drift')
        self.assertEqual(result['result'], 'blocked')
        self.assertTrue(self.fixture.running)
        self.assertFalse(any(p == '/exit' for m, p in self.writes()))

    def test_execute_plan_is_consumed_once_even_after_success(self):
        prepared = self.plan(measurement_s=0.25, timeout_s=10)
        result = execute(prepared['plan'], prepared['plan_sha256'], client=self.client, root=self.root)
        self.assertEqual(result['result'], 'passed')
        before = len(self.writes())
        with self.assertRaises(FileExistsError):
            execute(prepared['plan'], prepared['plan_sha256'], client=self.client, root=self.root)
        self.assertEqual(len(self.writes()), before)

    def test_invalid_hash_and_candidate_drift_refuse_before_network(self):
        prepared = self.plan()
        self.fixture.calls.clear()
        with self.assertRaises(ValueError):
            execute(prepared['plan'], '0' * 64, client=self.client, root=self.root)
        (self.root / 'lab.c').write_bytes(b'changed compiled source')
        with self.assertRaises(ValueError):
            execute(prepared['plan'], prepared['plan_sha256'], client=self.client, root=self.root)
        self.assertEqual(self.fixture.calls, [])

    def test_idle_policy_refuses_before_any_write(self):
        prepared = self.plan()
        self.fixture.idle = False
        result = execute(prepared['plan'], prepared['plan_sha256'], client=self.client, root=self.root)
        self.assertEqual(result['result'], 'blocked')
        self.assertEqual(self.writes(), [])

    def test_endpoint_drift_refuses_before_any_write(self):
        prepared = self.plan()
        self.endpoint['token'] = 'e' * 32
        result = execute(prepared['plan'], prepared['plan_sha256'], client=self.client, root=self.root)
        self.assertEqual(result['result'], 'blocked')
        self.assertEqual(self.writes(), [])

    def test_journal_intent_failure_cannot_submit_native_mutation(self):
        prepared = self.plan()
        with patch('workbench.native_lifecycle.Journal.event', side_effect=OSError('fixture journal unavailable')):
            result = execute(prepared['plan'], prepared['plan_sha256'], client=self.client, root=self.root)
        self.assertEqual(result['result'], 'blocked')
        self.assertEqual(self.writes(), [])

    def test_unknown_exit_reply_never_replays_exit(self):
        result = self.run_job('exit_not_applied')
        self.assertEqual(result['result'], 'unconfirmed')
        self.assertEqual(len([p for m, p in self.writes() if p == '/exit']), 1)

    def test_pending_native_install_timeout_never_reposts_or_launches(self):
        result = self.run_job('pending_install')
        self.assertEqual(result['result'], 'unconfirmed')
        self.assertEqual(result['failure_code'], 'install_polling_deadline_no_replay')
        self.assertEqual(len([p for m, p in self.writes() if p.endswith('/install')]), 1)
        self.assertFalse(any(p.endswith('/launch') for m, p in self.writes()))
        self.assertGreater(len([p for m, p in self.fixture.calls if p.startswith('/native-lifecycle/attempt/')]), 1)

    def test_receipt_journal_failure_cannot_resubmit_or_continue(self):
        prepared = self.plan()
        from workbench.runner import Journal
        actual = Journal.event
        def event(journal, kind, fields):
            if kind == 'mutation_receipt' and fields['operation'] == 'install':
                raise OSError('simulated local receipt commit failure')
            return actual(journal, kind, fields)
        with patch.object(Journal, 'event', event):
            result = execute(prepared['plan'], prepared['plan_sha256'], client=self.client, root=self.root)
        self.assertEqual(result['result'], 'unconfirmed')
        self.assertEqual(len([p for m, p in self.writes() if p.endswith('/install')]), 1)
        self.assertFalse(any(p.endswith('/launch') for m, p in self.writes()))

    def test_independent_header_is_deterministic_and_validates_its_auth_dependencies(self):
        a, b = make_head(package_bytes=100), make_head(package_bytes=101)
        self.assertEqual(len(a), 0x430)
        self.assertEqual(a[:4], b'\x7fPKG')
        self.assertEqual(a[0x30:0x54], b'EP9000-VMCP00001_00-0000000000000000')
        self.assertEqual(a[0x60:0xc0], bytes(0x60))
        self.assertNotEqual(a[0x100:0x110], b[0x100:0x110])
        self.assertNotEqual(a[0x410:0x420], b[0x410:0x420])
        self.assertNotEqual(a[0x420:], b[0x420:])
        validate_head(a, 100)
        with self.assertRaises(ValueError):
            validate_head(a[:-1] + bytes((a[-1] ^ 1,)), 100)

    def test_package_identity_bounds_zip_layout_and_source_pins(self):
        info, files = load_candidate(self.expected, root=self.root)
        self.assertEqual(info['title_id'], TITLE)
        self.assertEqual(len(files), 8)
        with self.assertRaises(ValueError):
            load_candidate('0' * 64, root=self.root)
        (self.root / 'lab.c').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            load_candidate(self.expected, root=self.root)

    def test_tampered_self_authority_native_build_arm_and_compression_are_refused(self):
        base = self.root / 'dist/native-lab'
        original = (base / 'native_lab.vpk').read_bytes()
        original_report = json.loads((base / 'build-report.json').read_bytes())
        import io
        for mode in ('authority', 'build', 'arm', 'compression', 'encryption', 'segment_bounds'):
            with self.subTest(mode=mode), zipfile.ZipFile(io.BytesIO(original)) as source:
                with zipfile.ZipFile(base / 'native_lab.vpk', 'w', zipfile.ZIP_DEFLATED) as out:
                    for name in source.namelist():
                        data = source.read(name)
                        if name == 'eboot.bin':
                            data = bytearray(data)
                            if mode == 'authority':
                                struct.pack_into('<Q', data, 0x80, 0x2f00000000000002)
                            elif mode == 'build':
                                data = data.replace(LAB_BUILD.encode(), b'9' * 64)
                            elif mode == 'arm':
                                struct.pack_into('<H', data, 0xa0 + 18, 3)
                            elif mode == 'compression':
                                struct.pack_into('<Q', data, 0x140 + 16, 2)
                            elif mode == 'encryption':
                                struct.pack_into('<Q', data, 0x140 + 24, 1)
                            else:
                                struct.pack_into('<Q', data, 0x140, len(data) + 1)
                            data = bytes(data)
                        out.writestr(name, data)
                payload = (base / 'native_lab.vpk').read_bytes()
                report = copy.deepcopy(original_report)
                report['package'].update(bytes=len(payload), sha256=sha(payload))
                (base / 'build-report.json').write_bytes(canonical(report))
                with self.assertRaises(ValueError):
                    load_candidate(sha(payload), root=self.root)

    def test_actual_stdio_catalog_preview_and_invalid_execute(self):
        async def proof():
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            config = self.root / 'resident.json'
            config.write_bytes(canonical(self.endpoint))
            env = {**os.environ, 'VITA_RESIDENT_CONFIG': str(config), 'VITA_WORKBENCH_ROOT': str(self.root),
                   'VITA_WORKBENCH_LOCK': str(self.root / 'lock')}
            params = StdioServerParameters(command=sys.executable, args=[str(ROOT / 'resident/bridge.py')], env=env, cwd=str(ROOT))
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = {item.name: item for item in (await session.list_tools()).tools}
                    for name in ('vita_workbench_native_preview', 'vita_workbench_native_execute', 'vita_workbench_native_reconcile'):
                        self.assertIn(name, tools)
                    self.assertTrue(tools['vita_workbench_native_preview'].annotations.readOnlyHint)
                    self.assertFalse(tools['vita_workbench_native_execute'].annotations.idempotentHint)
                    result = await session.call_tool('vita_workbench_native_preview', {'expected_sha256': self.expected, 'measurement_s': 0.25, 'timeout_s': 10})
                    self.assertFalse(result.isError)
                    value = result.structuredContent or json.loads(result.content[0].text)
                    self.assertTrue(value['ready'])
                    refused = await session.call_tool('vita_workbench_native_execute', {'plan': value['plan'], 'plan_sha256': '0' * 64})
                    self.assertTrue(refused.isError)
                    self.assertEqual(self.writes(), [])
        asyncio.run(proof())

    def test_actual_stdio_full_execute_lost_exit_and_readonly_reconcile(self):
        # The production lab port is fixed. This explicit localhost fixture is
        # the only listener on17868 during this test; no real Vita is contacted.
        lab = ThreadingHTTPServer(('127.0.0.1', 17868), self.fixture.handler())
        threading.Thread(target=lab.serve_forever, daemon=True).start()
        self.fixture.mode = 'drop_exit'
        async def proof():
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            config = self.root / 'resident.json'
            config.write_bytes(canonical(self.endpoint))
            env = {**os.environ, 'VITA_RESIDENT_CONFIG': str(config), 'VITA_WORKBENCH_ROOT': str(self.root),
                   'VITA_WORKBENCH_LOCK': str(self.root / 'lock')}
            params = StdioServerParameters(command=sys.executable, args=[str(ROOT / 'resident/bridge.py')], env=env, cwd=str(ROOT))
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    prepared = await session.call_tool('vita_workbench_native_preview',
                                                       {'expected_sha256': self.expected, 'measurement_s': 0.25, 'timeout_s': 10})
                    self.assertFalse(prepared.isError)
                    value = prepared.structuredContent or json.loads(prepared.content[0].text)
                    executed = await session.call_tool('vita_workbench_native_execute',
                                                       {'plan': value['plan'], 'plan_sha256': value['plan_sha256']})
                    self.assertFalse(executed.isError)
                    result = executed.structuredContent or json.loads(executed.content[0].text)
                    self.assertEqual(result['result'], 'passed')
                    before = len(self.writes())
                    observed = await session.call_tool('vita_workbench_native_reconcile', {'job_id': value['plan']['job_id']})
                    self.assertFalse(observed.isError)
                    observation = observed.structuredContent or json.loads(observed.content[0].text)
                    self.assertEqual(observation['device_mutations'], 0)
                    self.assertEqual(len(observation['operation_observations']), 2)
                    self.assertEqual(len(self.writes()), before)
                    self.assertEqual(len([p for m, p in self.writes() if p == '/exit']), 1)
        try:
            asyncio.run(proof())
        finally:
            lab.shutdown()
            lab.server_close()

    def test_cli_preview_and_invalid_execute(self):
        config = self.root / 'resident.json'
        config.write_bytes(canonical(self.endpoint))
        env = {**os.environ, 'VITA_RESIDENT_CONFIG': str(config), 'VITA_WORKBENCH_ROOT': str(self.root)}
        result = subprocess.run([sys.executable, '-m', 'workbench.native_lifecycle', 'preview', self.expected,
                                 '--measurement', '0.25', '--timeout', '10'], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        prepared = json.loads(result.stdout)
        plan_file = self.root / 'plan.json'
        plan_file.write_bytes(canonical(prepared['plan']))
        refused = subprocess.run([sys.executable, '-m', 'workbench.native_lifecycle', 'execute', str(plan_file), '0' * 64],
                                 cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual(self.writes(), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
