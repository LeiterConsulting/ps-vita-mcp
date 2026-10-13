"""Actual C HTTP transport diagnostics: bounded, private and lease-neutral."""
import http.client
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
import errno

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
ADMIN = '1' * 32
BUILD = 'a' * 64
MISSING = 0xffffffff
STATUS_ROUTE = '/keep-awake/transport-status'
RECORD_ROUTE = '/keep-awake/transport-record/'
COMMON = {'app', 'protocol', 'resident_build_id', 'instance_id', 'status'}
RECORD_FIELDS = {
    'seq', 'listener_generation', 'accepted_ms', 'method', 'operation',
    'phase_ms', 'bytes', 'would_block', 'revision', 'apply_result',
    'http_status', 'outcome', 'io_stage', 'io_result', 'io_errno',
    'accept_result', 'accept_errno', 'close_result', 'close_errno',
    'tick_count', 'max_gap_ms', 'flags'}


class TransportHTTPTests(unittest.TestCase):
    """Use real sockets and the production parser/worker, never a JSON mock."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.start_process()

    def start_process(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.process = subprocess.Popen(
            [str(ROOT / 'build/resident-keep-awake/host-server'),
             str(self.root), str(self.port), ADMIN],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=1'})
        for _ in range(150):
            try:
                self.status()
                break
            except (OSError, http.client.HTTPException):
                if self.process.poll() is not None:
                    self.fail(self.process.communicate()[1].decode('utf-8'))
                time.sleep(.02)
        else:
            self.fail('native transport fixture did not start')

    def tearDown(self):
        self.stop_process()
        self.directory.cleanup()

    def stop_process(self):
        self.process.terminate()
        output, error = self.process.communicate(timeout=5)
        self.assertEqual(self.process.returncode, 0,
                         (output + error).decode('utf-8'))
        self.assertNotIn(b'ERROR: AddressSanitizer', error)
        self.assertNotIn(b'runtime error:', error)

    def request(self, method, path, body=None, token=ADMIN, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        fields = {'Authorization': 'Bearer ' + token}
        if body is not None:
            fields['Content-Type'] = 'application/octet-stream'
        fields.update(headers or {})
        try:
            connection.request(method, path, body=body, headers=fields)
            response = connection.getresponse()
            return response.status, response.getheaders(), response.read()
        finally:
            connection.close()

    def call(self, method, path, body=None, token=ADMIN, headers=None):
        code, _, raw = self.request(method, path, body, token, headers)
        return code, json.loads(raw)

    def status(self):
        code, status = self.call('GET', '/keep-awake/status')
        self.assertEqual(code, 200, status)
        self.assertEqual(status['resident_build_id'], BUILD)
        return status

    def command(self, status, ttl=5000, duration=30000, lease=None, job=None):
        return struct.pack('<8I32s32s32s', 0x31414b52, 1, status['revision'],
                           ttl, duration, 0, 0, 0,
                           status['instance_id'].encode(),
                           (lease or status['lease_id'] or uuid.uuid4().hex).encode(),
                           (job or status['job_id'] or uuid.uuid4().hex).encode())

    def diagnostic(self, path=STATUS_ROUTE, expected=200, token=ADMIN):
        code, headers, raw = self.request('GET', path, token=token)
        self.assertEqual(code, expected, raw)
        self.assertLessEqual(len(raw), 1399)
        fields = {key.lower(): value for key, value in headers}
        self.assertEqual(fields['content-length'], str(len(raw)))
        self.assertEqual(fields['cache-control'], 'no-store')
        result = json.loads(raw)
        if token == ADMIN:
            self.assertEqual(result['app'], 'Vita Resident Keep Awake Transport')
            self.assertEqual(result['protocol'], 1)
            self.assertEqual(result['resident_build_id'], BUILD)
            self.assertEqual(result['status'], code)
        return result

    def latest(self):
        summary = self.diagnostic()
        self.assertGreater(summary['count'], 0)
        return self.diagnostic(RECORD_ROUTE + summary['newest_seq'])

    def fault(self, name, value=1):
        (self.root / name).write_text(str(value), encoding='ascii')

    def wait_summary(self, predicate):
        deadline = time.monotonic() + 3
        last = None
        while time.monotonic() < deadline:
            try:
                last = self.diagnostic()
                if predicate(last):
                    return last
            except (OSError, http.client.HTTPException):
                pass
            time.sleep(.02)
        self.fail('native diagnostic condition not reached: ' + repr(last))

    def assert_record(self, record):
        self.assertEqual(set(record), COMMON | RECORD_FIELDS)
        for key, length in [('phase_ms', 8), ('bytes', 3), ('would_block', 2),
                            ('revision', 2), ('tick_count', 2)]:
            self.assertEqual(len(record[key]), length)
            self.assertTrue(all(type(value) is int for value in record[key]))
        # Order only reached phases; a missing phase cannot masquerade as time 0.
        present = [value for value in record['phase_ms'] if value != MISSING]
        self.assertEqual(present, sorted(present))
        self.assertRegex(record['seq'], r'^[0-9a-f]{16}$')

    def disconnected(self, method='GET', path='/keep-awake/status', body=None):
        with self.assertRaises((http.client.RemoteDisconnected,
                                ConnectionResetError, BrokenPipeError)):
            self.call(method, path, body)

    def test_ring_wrap_and_missing_vs_overwritten_sequence(self):
        initial = self.diagnostic()
        self.assertEqual(initial['capacity'], 16)
        self.assertGreater(initial['record_bytes'], 0)
        self.assertLessEqual(initial['record_bytes'], 192)
        self.assertIs(initial['resource_sampling'], False)
        self.assertIs(initial['sequence_exhausted'], False)
        first = initial['newest_seq']
        for _ in range(20):
            self.status()
        summary = self.diagnostic()
        self.assertEqual(summary['count'], 16)
        self.assertEqual(int(summary['newest_seq'], 16) -
                         int(summary['oldest_seq'], 16), 15)
        self.assertGreater(summary['overwritten'], initial['overwritten'])
        self.assertEqual(self.diagnostic(RECORD_ROUTE + first, 404)['error'], 2)
        self.assertEqual(self.diagnostic(RECORD_ROUTE + '0000000000000000', 404)['error'], 1)
        future = f"{int(summary['newest_seq'], 16) + 1:016x}"
        self.assertEqual(self.diagnostic(RECORD_ROUTE + future, 404)['error'], 1)
        record = self.diagnostic(RECORD_ROUTE + summary['oldest_seq'])
        self.assert_record(record)
        self.assertEqual(record['outcome'], 1)

    def test_administrator_required_and_diagnostic_reads_do_not_replace_ring(self):
        before = self.diagnostic()
        sequence = before['newest_seq']
        expected = self.diagnostic(RECORD_ROUTE + sequence)
        for path in (STATUS_ROUTE, RECORD_ROUTE + sequence):
            for token in ('2' * 32, ''):
                denied = self.diagnostic(path, 401, token)
                self.assertEqual(denied, {'error': 'administrator_required'})
            for _ in range(4):
                self.diagnostic(path)
        after = self.diagnostic()
        for key in ('count', 'oldest_seq', 'newest_seq', 'overwritten'):
            self.assertEqual(after[key], before[key], key)
        self.assertEqual(self.diagnostic(RECORD_ROUTE + sequence), expected)
        self.assertGreater(after['diagnostic_reads'], before['diagnostic_reads'])

    def test_diagnostics_never_admit_renew_or_release_a_lease(self):
        before = self.status()
        self.assertFalse(before['active'])
        for _ in range(5):
            self.diagnostic()
        inactive = self.status()
        self.assertEqual((inactive['revision'], inactive['tick_count']),
                         (before['revision'], before['tick_count']))
        code, active = self.call('POST', '/keep-awake/lease', self.command(inactive))
        self.assertEqual(code, 200)
        for _ in range(5):
            self.diagnostic()
            self.latest()
        observed = self.status()
        self.assertTrue(observed['active'])
        for key in ('revision', 'lease_id', 'job_id'):
            self.assertEqual(observed[key], active[key], key)
        self.assertLessEqual(observed['remaining_ms'], active['remaining_ms'])
        self.assertLessEqual(observed['session_remaining_ms'], active['session_remaining_ms'])

    def test_normal_get_and_post_phase_order_and_queued_bytes(self):
        code, _, raw = self.request('GET', '/keep-awake/status')
        self.assertEqual(code, 200)
        before = json.loads(raw)
        record = self.latest()
        self.assert_record(record)
        self.assertEqual((record['method'], record['operation'], record['outcome']), (1, 1, 1))
        self.assertEqual(record['bytes'][2], len(raw))
        self.assertGreater(record['bytes'][1], 0)
        self.assertEqual(record['revision'], [before['revision']] * 2)
        self.assertEqual(record['apply_result'], 0)
        self.assertEqual(record['phase_ms'][3:5], [MISSING, MISSING])
        self.assertTrue(record['flags'] & 8)
        for index in (0, 1, 5, 6, 7):
            self.assertNotEqual(record['phase_ms'][index], MISSING)
        code, _, raw = self.request('POST', '/keep-awake/lease', self.command(before))
        self.assertEqual(code, 200)
        active = json.loads(raw)
        record = self.latest()
        self.assert_record(record)
        self.assertEqual((record['method'], record['operation']), (2, 2))
        self.assertEqual(record['revision'], [before['revision'], active['revision']])
        self.assertEqual(record['apply_result'], 200)
        self.assertEqual(record['http_status'], 200)
        self.assertEqual(record['bytes'][2], len(raw))
        self.assertGreaterEqual(record['bytes'][0], 128)
        self.assertTrue(record['flags'] & 4)
        self.assertTrue(all(value != MISSING for value in record['phase_ms']))

    def test_transport_record_never_contains_token_or_owned_lease_ids(self):
        before = self.status()
        lease, job = 'd' * 32, 'e' * 32
        code, active = self.call('POST', '/keep-awake/lease',
                                 self.command(before, lease=lease, job=job))
        self.assertEqual(code, 200)
        self.assertEqual(active['lease_id'], lease)
        record = self.latest()
        self.assert_record(record)
        serialized = json.dumps(record)
        for private in (ADMIN, lease, job):
            self.assertNotIn(private, serialized)

    def test_partial_headers_deadline_and_body_eof_do_not_apply(self):
        before = self.status()
        with socket.create_connection(('127.0.0.1', self.port), timeout=3) as sock:
            data = b'POST /keep-awake/lease HTTP/1.1\r\nHost: fixture\r\n'
            sock.sendall(data)
            self.assertEqual(sock.recv(1), b'')
        record = self.latest()
        self.assert_record(record)
        self.assertEqual(record['outcome'], 2)
        self.assertEqual(record['bytes'], [len(data), 0, 0])
        self.assertGreater(record['would_block'][0], 0)
        self.assertEqual(record['apply_result'], 0)
        with socket.create_connection(('127.0.0.1', self.port), timeout=3) as sock:
            headers = ('POST /keep-awake/lease HTTP/1.1\r\nHost: fixture\r\n'
                       'Authorization: Bearer ' + ADMIN + '\r\n'
                       'Content-Type: application/octet-stream\r\nContent-Length: 128\r\n\r\n')
            sock.sendall(headers.encode() + self.command(before)[:-1])
            sock.shutdown(socket.SHUT_WR)
            self.assertEqual(sock.recv(1), b'')
        record = self.latest()
        self.assertEqual(record['outcome'], 4)
        self.assertEqual(record['phase_ms'][2:5], [MISSING] * 3)
        self.assertEqual(record['apply_result'], 0)
        self.assertEqual(self.status()['revision'], before['revision'])

    def test_receive_error_and_immediate_errno_are_retained(self):
        self.fault('keep-awake-fault-recv', errno.EIO)
        self.disconnected()
        record = self.latest()
        self.assertEqual((record['outcome'], record['io_stage']), (5, 8))
        self.assertEqual(record['io_result'], -1)
        self.assertEqual(record['io_errno'], errno.EIO)
        self.assertEqual(record['bytes'], [0, 0, 0])

    def test_send_error_retains_errno_even_after_clock_and_close_io(self):
        self.fault('keep-awake-fault-send', errno.EPIPE)
        self.disconnected()
        record = self.latest()
        self.assertEqual((record['outcome'], record['io_stage']), (6, 9))
        self.assertEqual(record['io_result'], -1)
        self.assertEqual(record['io_errno'], errno.EPIPE)
        self.assertEqual(record['bytes'][1:], [0, 0])
        self.assertEqual(record['phase_ms'][5:7], [MISSING] * 2)

    def test_send_would_block_deadline_and_partial_send_accounting(self):
        self.fault('keep-awake-send-would-block')
        try:
            self.disconnected()
        finally:
            (self.root / 'keep-awake-send-would-block').unlink()
        record = self.latest()
        self.assertEqual(record['outcome'], 3)
        self.assertGreater(record['would_block'][1], 0)
        self.assertEqual(record['bytes'][1:], [0, 0])
        self.fault('keep-awake-send-limit', 7)
        code, _, raw = self.request('GET', '/keep-awake/status')
        self.assertEqual(code, 200)
        record = self.latest()
        self.assertEqual(record['outcome'], 1)
        self.assertEqual(record['bytes'][2], len(raw))
        self.assertGreater(record['bytes'][1], 7)
        self.assertTrue(record['flags'] & 8)

    def test_close_failure_is_separate_from_successful_response(self):
        self.fault('keep-awake-fault-close', errno.EACCES)
        self.assertEqual(self.call('GET', '/keep-awake/status')[0], 200)
        record = self.latest()
        self.assertEqual(record['outcome'], 1)
        self.assertEqual(record['close_result'], -1)
        self.assertEqual(record['close_errno'], errno.EACCES)
        self.assertTrue(record['flags'] & 16)
        self.assertTrue(record['flags'] & 8)

    def test_accept_and_client_nbio_failures_preserve_raw_error_after_recovery(self):
        before = self.diagnostic()
        self.fault('keep-awake-fault-accept', errno.ECONNABORTED)
        after = self.wait_summary(lambda value:
                                  value['listener_generation'] > before['listener_generation'])
        self.assertGreater(after['accept_failures'], before['accept_failures'])
        self.assertEqual(after['listener']['stage'], 6)
        self.assertEqual(after['listener']['result'], -1)
        self.assertEqual(after['listener']['errno'], errno.ECONNABORTED)
        self.assertEqual(after['listener']['close_result'], 0)
        self.assertEqual(after['newest_seq'], before['newest_seq'])
        self.fault('keep-awake-fault-client-nbio', errno.EACCES)
        self.disconnected()
        rejected = self.diagnostic()
        self.assertGreater(rejected['accept_failures'], after['accept_failures'])
        self.assertEqual(rejected['listener']['stage'], 7)
        self.assertEqual(rejected['listener']['errno'], errno.EACCES)
        self.assertEqual(rejected['listener']['close_result'], 0)
        self.assertEqual(rejected['newest_seq'], after['newest_seq'])
        self.assertEqual(rejected['listener_generation'], after['listener_generation'])

    def test_listen_stage_errors_survive_successful_reopen(self):
        for name, stage in [('listen-create', 1),
                            ('listen-bind', 3), ('listen-listen', 4),
                            ('listener-nbio', 5)]:
            with self.subTest(stage=name):
                before = self.diagnostic()
                self.fault('keep-awake-fault-' + name, errno.EIO)
                self.fault('keep-awake-fault-accept', errno.ECONNABORTED)
                after = self.wait_summary(lambda value:
                                          value['listener_generation'] > before['listener_generation'])
                self.assertEqual(after['listener']['stage'], stage)
                self.assertEqual(after['listener']['result'], -1)
                self.assertEqual(after['listener']['errno'], errno.EIO)
                self.assertEqual(after['newest_seq'], before['newest_seq'])
                self.assertGreater(after['listen_failures'], before['listen_failures'])
                if stage in (3, 4, 5):
                    self.assertEqual(after['listener']['close_result'], 0)
                    self.assertEqual(after['listener']['close_errno'], 0)

    def test_reuse_error_is_best_effort_on_a_fresh_listener_address(self):
        # A same-port reopen without REUSEADDR may legitimately hit TIME_WAIT.
        # A fresh port isolates the intended historical best-effort behavior.
        self.stop_process()
        self.fault('keep-awake-fault-listen-reuse', errno.EIO)
        self.start_process()
        summary = self.diagnostic()
        self.assertEqual(summary['listener_generation'], 1)
        self.assertEqual(summary['listen_failures'], 0)
        self.assertEqual(summary['listener']['stage'], 2)
        self.assertEqual(summary['listener']['result'], -1)
        self.assertEqual(summary['listener']['errno'], errno.EIO)

    def test_raw_network_error_and_last_loss_remain_visible_after_reconnection(self):
        before = self.diagnostic()
        self.assertEqual(before['network']['result'], 0)
        self.assertEqual(before['network']['state'], 3)
        self.fault('keep-awake-network-result', -77)
        lost = self.wait_summary(lambda value: value['network']['result'] == -77)
        self.assertEqual(lost['network']['state'], 3)
        self.assertEqual(lost['network']['last_loss_result'], -77)
        self.assertEqual(lost['network']['last_loss_state'], 3)
        self.assertGreater(lost['network']['last_loss_ms'], 0)
        self.fault('keep-awake-network-result', 0)
        recovered = self.wait_summary(lambda value: value['network']['result'] == 0)
        self.assertEqual(recovered['network']['state'], 3)
        self.assertGreater(recovered['network']['changes'], lost['network']['changes'])
        for key in ('last_loss_result', 'last_loss_state', 'last_loss_ms'):
            self.assertEqual(recovered['network'][key], lost['network'][key])

    def test_accepted_apply_can_have_zero_queued_response_headers(self):
        before = self.status()
        wire = self.command(before)
        self.fault('keep-awake-after-apply-clock-advance', 2001)
        self.disconnected('POST', '/keep-awake/lease', wire)
        record = self.latest()
        self.assert_record(record)
        self.assertEqual((record['operation'], record['apply_result']), (2, 200))
        self.assertEqual(record['revision'], [before['revision'], before['revision'] + 1])
        self.assertEqual(record['outcome'], 3)
        self.assertEqual(record['bytes'][1:], [0, 0])
        self.assertNotEqual(record['phase_ms'][3], MISSING)
        self.assertNotEqual(record['phase_ms'][4], MISSING)
        self.assertEqual(record['phase_ms'][5:7], [MISSING] * 2)
        self.assertTrue(record['flags'] & 4)
        self.assertFalse(record['flags'] & 8)
        recovered = self.status()
        self.assertTrue(recovered['active'])
        self.assertEqual(recovered['revision'], before['revision'] + 1)


class TransportFormattingTests(unittest.TestCase):
    def test_full_width_numeric_replies_remain_complete_json_below_1400_bytes(self):
        completed = subprocess.run(
            [str(ROOT / 'build/resident-keep-awake/transport-test'), '--max-json'],
            check=True, capture_output=True, timeout=5,
            env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=1'})
        self.assertNotIn(b'ERROR: AddressSanitizer', completed.stderr)
        self.assertNotIn(b'runtime error:', completed.stderr)
        lines = completed.stdout.splitlines()
        self.assertEqual(len(lines), 2)
        status, record = [json.loads(line) for line in lines]
        for line in lines:
            self.assertLessEqual(len(line), 1399)
        self.assertEqual(status['newest_seq'], 'f' * 16)
        self.assertEqual(status['accepted'], 2**64 - 1)
        self.assertEqual(status['listener']['errno'], -(2**31))
        self.assertEqual(record['seq'], 'f' * 16)
        self.assertEqual(record['accepted_ms'], 2**64 - 1)
        self.assertEqual(record['io_errno'], -(2**31))
        self.assertEqual(record['phase_ms'], [2**32 - 1] * 8)


if __name__ == '__main__':
    unittest.main()
