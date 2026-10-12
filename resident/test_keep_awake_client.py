"""HTTP/host lease decisions. These tests do not qualify Vita sleep or power ticks."""
from __future__ import annotations

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
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from resident.keep_awake_client import (APP, PORT, KeepAwakeClient, KeepAwakeLost, KeepAwakeRejected,
                                       KeepAwakeUnknown, ResidentKeeper, pack, register, run_command, validate)

TOKEN, BUILD, INSTANCE, LEASE, JOB = 'a' * 32, 'b' * 64, 'c' * 32, 'd' * 32, 'e' * 32


class Fixture:
    def __init__(self):
        self.started = time.monotonic()
        self.offset = 10000
        self.revision = 0
        self.instance = INSTANCE
        self.build = BUILD
        self.deadline = self.ceiling = 0
        self.lease = self.job = None
        self.calls = []
        self.packets = []
        self.drop = False
        self.malformed = False
        self.tick_result = 0
        self.lock = threading.RLock()
        self.reason = 'boot'

    def now(self):
        return self.offset + int((time.monotonic() - self.started) * 1000)

    def state(self):
        now = self.now()
        if self.lease and now >= min(self.deadline, self.ceiling):
            self.lease = self.job = None
            self.deadline = self.ceiling = 0
            self.revision += 1
            self.reason = 'expired'
        active = self.lease is not None
        return {'app': APP, 'protocol': 1, 'status': 200, 'error': None, 'port': PORT, 'resident_build_id': self.build,
                'instance_id': self.instance, 'clock_ms': now, 'revision': self.revision,
                'active': active, 'lease_id': self.lease, 'job_id': self.job,
                'remaining_ms': max(0, min(self.deadline, self.ceiling) - now) if active else 0,
                'session_remaining_ms': max(0, self.ceiling - now) if active else 0,
                'last_tick_ms': now if active else 0, 'tick_count': int(active),
                'tick_result': self.tick_result, 'reason': self.reason}

    def handler(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, value, code=200):
                raw = json.dumps(value, separators=(',', ':')).encode()
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def auth(self):
                owner.calls.append((self.command, self.path))
                if self.headers.get('Authorization') != 'Bearer ' + TOKEN:
                    self.reply({'error': 'authorization'}, 401)
                    return False
                return True

            def do_GET(self):
                with owner.lock:
                    if self.auth():
                        self.reply(owner.state())

            def do_POST(self):
                with owner.lock:
                    if not self.auth():
                        return
                    raw = self.rfile.read(int(self.headers['Content-Length']))
                    owner.packets.append(raw)
                    words = struct.unpack('<8I32s32s32s', raw)
                    magic, protocol, revision, ttl, duration, r0, r1, r2, instance, lease, job = words
                    instance, lease, job = (value.decode('ascii') for value in (instance, lease, job))
                    before = owner.state()
                    if revision != before['revision'] or instance != owner.instance:
                        return self.reply({'error': 'cas'}, 409)
                    if duration and owner.lease or not duration and (owner.lease != lease or owner.job != job):
                        return self.reply({'error': 'owner'}, 409)
                    now = owner.now()
                    if duration:
                        owner.ceiling = now + duration
                    owner.lease, owner.job = (lease, job) if ttl else (None, None)
                    owner.deadline = min(now + ttl, owner.ceiling) if ttl else 0
                    if not ttl:
                        owner.ceiling = 0
                    owner.reason = 'active' if ttl else 'ended'
                    owner.revision += 1
                    value = owner.state()
                    if owner.drop:
                        owner.drop = False
                        self.close_connection = True
                        return
                    if owner.malformed:
                        value['revision'] = True
                    self.reply(value, 503 if owner.tick_result < 0 else 200)

        return Handler


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), self.fixture.handler())
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.config = {'host': '127.0.0.1', 'port': 17866, 'token': TOKEN}
        self.client = KeepAwakeClient(lambda: dict(self.config), port=self.server.server_port, timeout=0.2)
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.keepers = []

    def tearDown(self):
        for keeper in self.keepers:
            keeper.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)
        self.temp.cleanup()

    def begin(self):
        status = self.client.status()
        return self.client.mutate(status['revision'], 30000, 60000, INSTANCE, LEASE, JOB, BUILD)

    def keeper(self, interval=0.03):
        value = ResidentKeeper(self.client, self.folder, JOB, max_duration_ms=60000, interval=interval)
        self.keepers.append(value)
        return value

    def wait_for(self, predicate, timeout=2):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            if predicate():
                return
            time.sleep(0.01)
        self.fail('Bounded condition did not become true')

    def test_binary_contract_and_invalid_inputs_fail_before_network(self):
        raw = pack(9, 30000, 60000, INSTANCE, LEASE, JOB)
        self.assertEqual(len(raw), 128)
        self.assertEqual(struct.unpack('<8I', raw[:32]), (0x31414b52, 1, 9, 30000, 60000, 0, 0, 0))
        for revision, ttl, duration in ((True, 30000, 60000), (-1, 30000, 60000), (0xffffffff, 30000, 60000),
                                        (0, 4999, 0), (0, 30001, 0), (0, 0, 60000), (0, 30000, 1800001)):
            with self.subTest(values=(revision, ttl, duration)), self.assertRaises(ValueError):
                self.client.mutate(revision, ttl, duration, INSTANCE, LEASE, JOB, BUILD)
        self.assertEqual(self.fixture.calls, [])

    def test_status_does_not_renew_or_mutate(self):
        self.begin()
        deadline, ceiling, revision = self.fixture.deadline, self.fixture.ceiling, self.fixture.revision
        for _ in range(3):
            self.client.status()
        self.assertEqual((deadline, ceiling, revision), (self.fixture.deadline, self.fixture.ceiling, self.fixture.revision))
        self.assertEqual(len(self.fixture.packets), 1)

    def test_start_renew_end_and_absolute_ceiling(self):
        first = self.begin()
        ceiling = self.fixture.ceiling
        second = self.client.mutate(first['revision'], 30000, 0, INSTANCE, LEASE, JOB, BUILD)
        self.assertEqual(second['revision'], first['revision'] + 1)
        self.assertEqual(self.fixture.ceiling, ceiling)
        final = self.client.mutate(second['revision'], 0, 0, INSTANCE, LEASE, JOB, BUILD)
        self.assertFalse(final['active'])
        self.assertIsNone(final['lease_id'])
        self.assertEqual(len(self.fixture.packets), 3)

    def test_stale_revision_owner_build_or_instance_refuses_before_post(self):
        value = self.begin()
        count = len(self.fixture.packets)
        for revision, instance, lease, job, build in ((0, INSTANCE, LEASE, JOB, BUILD),
                (value['revision'], '0' * 32, LEASE, JOB, BUILD),
                (value['revision'], INSTANCE, '0' * 32, JOB, BUILD),
                (value['revision'], INSTANCE, LEASE, '0' * 32, BUILD),
                (value['revision'], INSTANCE, LEASE, JOB, '0' * 64)):
            with self.subTest(pins=(revision, instance, lease, job, build)), self.assertRaises(KeepAwakeLost):
                self.client.mutate(revision, 30000, 0, instance, lease, job, build)
        self.assertEqual(len(self.fixture.packets), count)

    def test_admin_token_required(self):
        self.config['token'] = 'f' * 32
        client = KeepAwakeClient(lambda: dict(self.config), port=self.server.server_port)
        with self.assertRaises(KeepAwakeRejected):
            client.status()
        self.assertEqual(self.fixture.packets, [])

    def test_unknown_begin_is_not_replayed_and_cleanup_can_end_exact_owner(self):
        keeper = self.keeper()
        self.fixture.drop = True
        with self.assertRaises(KeepAwakeUnknown):
            keeper.start(BUILD, INSTANCE)
        self.assertEqual(len(self.fixture.packets), 1)
        self.assertIsNone(keeper.thread)
        self.assertEqual(keeper.stop()['end'], 'ended')
        self.assertEqual(len(self.fixture.packets), 2)
        self.assertFalse(self.fixture.state()['active'])
        self.assertEqual([struct.unpack('<8I', raw[:32])[3] for raw in self.fixture.packets], [30000, 0])

    def test_unknown_renewal_stops_thread_no_retry_and_fresh_cas_cleanup(self):
        keeper = self.keeper()
        keeper.start(BUILD, INSTANCE)
        self.fixture.drop = True
        self.wait_for(lambda: keeper.failed is not None)
        self.assertEqual(len(self.fixture.packets), 2)
        time.sleep(0.1)
        self.assertEqual(len(self.fixture.packets), 2)
        with self.assertRaises(KeepAwakeLost):
            keeper.check()
        self.assertEqual(keeper.stop()['end'], 'ended')
        self.assertEqual(len(self.fixture.packets), 3)
        self.assertEqual(struct.unpack('<8I', self.fixture.packets[-1][:32])[2], 2)

    def test_invalid_accepted_reply_is_unknown_not_success_or_replayed(self):
        self.fixture.malformed = True
        with self.assertRaises(KeepAwakeUnknown):
            self.begin()
        self.assertEqual(len(self.fixture.packets), 1)

    def test_keeper_thread_renews_during_silent_or_blocked_work_then_ends(self):
        keeper = self.keeper()
        keeper.start(BUILD, INSTANCE)
        # The main work thread makes no calls while waiting for this result.
        self.wait_for(lambda: keeper.result['renewals'] >= 2)
        keeper.check(fresh=True)
        result = keeper.stop()
        self.assertEqual(result['end'], 'ended')
        self.assertFalse(self.fixture.state()['active'])
        events = [json.loads(line) for line in (self.folder / 'resident-keep-awake.jsonl').read_text().splitlines()]
        intents = [i for i, event in enumerate(events) if event['kind'] == 'lease_intent']
        receipts = [i for i, event in enumerate(events) if event['kind'] == 'lease_receipt']
        self.assertEqual(len(intents), len(self.fixture.packets))
        self.assertEqual(len(intents), len(receipts))
        self.assertTrue(all(a < b for a, b in zip(intents, receipts)))
        self.assertNotIn(TOKEN, json.dumps(events))

    def test_stopped_or_dead_renewal_thread_rejects_further_work(self):
        keeper = self.keeper(interval=10)
        keeper.start(BUILD, INSTANCE)
        keeper.end.set()
        keeper.thread.join(timeout=1)
        with self.assertRaises(KeepAwakeLost):
            keeper.check()
        self.assertEqual(len(self.fixture.packets), 1)

    def test_stop_during_durable_renewal_intent_cancels_before_post(self):
        keeper = self.keeper(interval=10)
        keeper.start(BUILD, INSTANCE)
        original = keeper.record
        def record(kind, **fields):
            original(kind, **fields)
            if kind == 'lease_intent' and fields.get('ttl_ms'):
                keeper.end.set()
        with patch.object(keeper, 'record', side_effect=record), self.assertRaises(KeepAwakeLost):
            keeper._send(30000)
        self.assertEqual(len(self.fixture.packets), 1)
        self.assertEqual(keeper.stop()['end'], 'ended')

    def test_expiry_after_client_loss_and_read_only_observation_never_restarts(self):
        keeper = self.keeper(interval=10)
        keeper.start(BUILD, INSTANCE)
        keeper.end.set()
        keeper.thread.join(timeout=1)
        self.fixture.offset += 30001
        status = self.client.status()
        self.assertFalse(status['active'])
        self.assertEqual(status['reason'], 'expired')
        self.assertEqual(keeper.stop()['end'], 'already_inactive')
        self.assertEqual(len(self.fixture.packets), 1)

    def test_owner_and_instance_drift_do_not_authorize_cleanup(self):
        keeper = self.keeper(interval=10)
        keeper.start(BUILD, INSTANCE)
        self.fixture.lease = 'f' * 32
        with self.assertRaises(KeepAwakeLost):
            keeper.check(fresh=True)
        self.assertEqual(keeper.stop()['end'], 'owner_changed; no mutation')
        self.assertEqual(len(self.fixture.packets), 1)
        self.fixture.instance = '0' * 32
        result = keeper.stop()
        self.assertIn('unconfirmed', result['end'])
        self.assertEqual(len(self.fixture.packets), 1)

    def test_clock_regression_local_expiry_and_revision_drift_fail_closed(self):
        for mode in ('clock', 'local', 'revision'):
            self.fixture.lease = self.fixture.job = None
            keeper = self.keeper(interval=10)
            keeper.start(BUILD, INSTANCE)
            if mode == 'clock':
                self.fixture.offset -= 1
                keeper.value['clock_ms'] = self.fixture.now() + 10000
            elif mode == 'local':
                keeper.observed -= 31
            else:
                self.fixture.revision += 1
            with self.subTest(mode=mode), self.assertRaises(KeepAwakeLost):
                keeper.check(fresh=True)
            keeper.stop()

    def test_endpoint_drift_stops_work_and_does_not_contact_new_device(self):
        keeper = self.keeper(interval=10)
        keeper.start(BUILD, INSTANCE)
        self.config['host'] = '127.0.0.2'
        with self.assertRaises(KeepAwakeLost):
            keeper.check(fresh=True)
        result = keeper.stop()
        self.assertIn('unconfirmed', result['end'])
        self.assertEqual(len(self.fixture.packets), 1)

    def test_durable_intent_failure_prevents_first_effect(self):
        keeper = self.keeper()
        with patch('resident.keep_awake_client.os.fsync', side_effect=OSError('fixture')):
            with self.assertRaises(OSError):
                keeper.start(BUILD, INSTANCE)
        self.assertEqual(self.fixture.packets, [])

    def test_tick_rejection_stops_work(self):
        keeper = self.keeper()
        self.fixture.tick_result = -1
        with self.assertRaises(KeepAwakeRejected):
            keeper.start(BUILD, INSTANCE)
        self.assertEqual(len(self.fixture.packets), 1)
        self.assertIsNone(keeper.thread)

    def test_silent_host_command_is_covered_and_finished_lease_is_ended(self):
        def factory(*args, **kwargs):
            return self.keeper()
        with patch('resident.keep_awake_client.ResidentKeeper', side_effect=factory):
            result = run_command([sys.executable, '-c', 'import time; time.sleep(0.16)'], self.folder,
                                 client=self.client, max_duration_ms=60000)
        self.assertEqual(result['returncode'], 0)
        self.assertGreaterEqual(self.keepers[-1].result['renewals'], 2)
        self.assertEqual(self.keepers[-1].result['end'], 'ended')

    def test_delayed_receipt_does_not_extend_locally_confirmed_lifetime(self):
        keeper = self.keeper(interval=10)
        original = self.client.mutate
        def delayed(*args, **kwargs):
            value = original(*args, **kwargs)
            time.sleep(0.12)
            return value
        with patch.object(self.client, 'mutate', side_effect=delayed):
            keeper.start(BUILD, INSTANCE)
        self.assertGreaterEqual(time.monotonic() - keeper.observed, 0.1)

    def test_host_command_success_does_not_hide_unconfirmed_lease_release(self):
        keeper = self.keeper(interval=10)
        with patch('resident.keep_awake_client.ResidentKeeper', return_value=keeper):
            original = keeper.stop
            def stop():
                value = original()
                return {**value, 'end': 'unconfirmed; fixture'}
            with patch.object(keeper, 'stop', side_effect=stop), self.assertRaises(KeepAwakeLost):
                run_command([sys.executable, '-c', 'pass'], self.folder, client=self.client,
                            max_duration_ms=60000)
        self.assertFalse(self.fixture.state()['active'])

    def test_host_command_is_stopped_when_lease_health_fails(self):
        keeper = self.keeper()
        command = [sys.executable, '-c', 'import time; time.sleep(20)']
        with patch('resident.keep_awake_client.ResidentKeeper', return_value=keeper):
            original = keeper.check
            calls = []
            def check(**kwargs):
                calls.append(1)
                if len(calls) > 2:
                    raise KeepAwakeLost('fixture loss')
                return original(**kwargs)
            with patch.object(keeper, 'check', side_effect=check), self.assertRaises(KeepAwakeLost):
                run_command(command, self.folder, client=self.client, max_duration_ms=60000)
        self.assertEqual(keeper.result['end'], 'ended')

    def test_host_command_owned_compiler_child_is_cancelled_after_lease_loss(self):
        keeper = self.keeper(interval=10)
        pidfile = self.folder / 'owned-child.pid'
        script = ('import subprocess,sys,time; from pathlib import Path; '
                  'child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); '
                  'Path(sys.argv[1]).write_text(str(child.pid)); time.sleep(60)')
        original = keeper.check
        def check(**kwargs):
            if pidfile.exists():
                raise KeepAwakeLost('fixture loss after compiler child spawn')
            return original(**kwargs)
        with patch('resident.keep_awake_client.ResidentKeeper', return_value=keeper):
            with patch.object(keeper, 'check', side_effect=check), self.assertRaises(KeepAwakeLost):
                run_command([sys.executable, '-c', script, str(pidfile)], self.folder, client=self.client,
                            max_duration_ms=60000)
        self.assertTrue(pidfile.exists())
        pid = int(pidfile.read_text())
        def alive():
            if os.name == 'nt':
                import ctypes
                from ctypes import wintypes
                kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                kernel.OpenProcess.restype = wintypes.HANDLE
                kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
                kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                handle = kernel.OpenProcess(0x1000, False, pid)
                if not handle:
                    return False
                try:
                    code = wintypes.DWORD()
                    return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
                finally:
                    kernel.CloseHandle(handle)
            stat = Path('/proc') / str(pid) / 'stat'
            return stat.exists() and stat.read_text().split(') ')[1][0] != 'Z'
        try:
            self.wait_for(lambda: not alive(), timeout=5)
        finally:
            if alive():
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(pid), '/F'], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, check=False, timeout=5)
                else:
                    import signal
                    os.kill(pid, signal.SIGKILL)
        self.assertEqual(keeper.result['end'], 'ended')

    def test_failed_command_termination_still_attempts_lease_release(self):
        keeper = self.keeper(interval=10)
        process = unittest.mock.Mock()
        process.poll.return_value = None
        with patch('resident.keep_awake_client.ResidentKeeper', return_value=keeper), \
                patch('subprocess.Popen', return_value=process), \
                patch.object(keeper, 'check', side_effect=[self.fixture.state(), KeepAwakeLost('fixture')]), \
                patch('resident.keep_awake_client._stop_command_tree', side_effect=OSError('fixture cleanup')):
            with self.assertRaises(OSError):
                run_command(['fixture'], self.folder, client=self.client, max_duration_ms=60000)
        self.assertEqual(keeper.result['end'], 'ended')

    def test_strict_reply_types_and_inactive_owner(self):
        value = self.client.status()
        for key, changed in (('status', 409), ('status', True), ('error', 'failure'),
                             ('revision', True), ('clock_ms', -1), ('protocol', True), ('port', 1),
                             ('lease_id', LEASE), ('remaining_ms', 1), ('tick_result', False),
                             ('active', 0), ('resident_build_id', 'bad')):
            invalid = copy.deepcopy(value)
            invalid[key] = changed
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                validate(invalid)

    def test_registration_exposes_only_explicit_bounded_tools(self):
        functions = {}
        class MCP:
            def tool(self, **kwargs):
                def decorate(function):
                    functions[function.__name__] = function
                    return function
                return decorate
        register(MCP(), lambda: self.config, {}, {})
        self.assertEqual(set(functions), {'vita_resident_keep_awake_' + suffix
                                         for suffix in ('status', 'begin', 'renew', 'end')})
        with self.assertRaises(ValueError):
            functions['vita_resident_keep_awake_begin'](0, BUILD, INSTANCE, LEASE, JOB, 0)
        with self.assertRaises(ValueError):
            functions['vita_resident_keep_awake_renew'](0, BUILD, INSTANCE, LEASE, JOB, 0)
        self.assertEqual(self.fixture.calls, [])


if __name__ == '__main__':
    unittest.main()
