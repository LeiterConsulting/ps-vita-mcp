"""Actual native HTTP parser, worker and policy with synthetic power/network."""
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

ADMIN = '1' * 32
BUILD = 'a' * 64
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from resident.keep_awake_client import KeepAwakeClient


class KeepAwakeHTTPTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
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
                    self.fail(self.process.communicate()[1].decode())
                time.sleep(.02)
        else:
            self.fail('keep-awake fixture did not start')

    def tearDown(self):
        self.process.terminate()
        output, error = self.process.communicate(timeout=5)
        self.assertEqual(self.process.returncode, 0, (output + error).decode())
        self.assertNotIn(b'ERROR: AddressSanitizer', error)
        self.assertNotIn(b'runtime error:', error)
        self.directory.cleanup()

    def call(self, method, path, body=None, token=ADMIN, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        fields = {'Authorization': 'Bearer ' + token}
        if body is not None:
            fields['Content-Type'] = 'application/octet-stream'
        fields.update(headers or {})
        connection.request(method, path, body=body, headers=fields)
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    def status(self):
        code, status = self.call('GET', '/keep-awake/status')
        self.assertEqual(code, 200, status)
        self.assertEqual(status['resident_build_id'], BUILD)
        self.assertLessEqual(status['last_tick_ms'], status['clock_ms'])
        return status

    def command(self, status, ttl=5000, duration=30000, lease=None, job=None,
                instance=None, revision=None):
        return struct.pack('<8I32s32s32s', 0x31414b52, 1,
                           status['revision'] if revision is None else revision,
                           ttl, duration, 0, 0, 0,
                           (instance or status['instance_id']).encode(),
                           (lease or status['lease_id'] or uuid.uuid4().hex).encode(),
                           (job or status['job_id'] or uuid.uuid4().hex).encode())

    def start(self, ttl=5000, duration=30000):
        before = self.status()
        code, after = self.call('POST', '/keep-awake/lease', self.command(before, ttl, duration))
        self.assertEqual(code, 200, after)
        self.assertTrue(after['active'])
        self.assertGreaterEqual(after['tick_count'], 1)
        return after

    def test_authorization_and_no_boot_activity(self):
        before = self.status()
        self.assertFalse(before['active'])
        time.sleep(.1)
        after = self.status()
        self.assertEqual(after['revision'], 0)
        self.assertEqual(after['tick_count'], 0)
        code, denied = self.call('GET', '/keep-awake/status', token='2' * 32)
        self.assertEqual(code, 401)
        self.assertEqual(set(denied), {'error'})
        self.assertEqual(self.call('POST', '/keep-awake/lease', bytes(128), token='2' * 32)[0], 401)
        self.assertEqual(self.status()['revision'], 0)

    def test_cas_owner_renew_and_explicit_end(self):
        before = self.status()
        wire = self.command(before)
        code, after = self.call('POST', '/keep-awake/lease', wire)
        self.assertEqual(code, 200)
        self.assertEqual(self.call('POST', '/keep-awake/lease', wire)[0], 409)
        wrong = self.command(after, duration=0, lease='4' * 32)
        self.assertEqual(self.call('POST', '/keep-awake/lease', wrong)[0], 409)
        wrong = self.command(after, duration=0, instance='5' * 32)
        self.assertEqual(self.call('POST', '/keep-awake/lease', wrong)[0], 409)
        self.assertEqual(self.status()['revision'], after['revision'])
        renewal = self.command(after, ttl=30000, duration=0)
        code, renewed = self.call('POST', '/keep-awake/lease', renewal)
        self.assertEqual(code, 200)
        self.assertLessEqual(renewed['session_remaining_ms'], after['session_remaining_ms'])
        self.assertLessEqual(renewed['remaining_ms'], renewed['session_remaining_ms'])
        code, ended = self.call('POST', '/keep-awake/lease', self.command(renewed, ttl=0, duration=0))
        self.assertEqual(code, 200)
        self.assertFalse(ended['active'])
        self.assertEqual(ended['reason'], 'released')
        self.assertIsNone(ended['lease_id'])
        ticks = ended['tick_count']
        time.sleep(1.05)
        self.assertEqual(self.status()['tick_count'], ticks)

    def test_status_reads_do_not_renew_and_ttl_expires(self):
        active = self.start()
        before = active['remaining_ms']
        deadline = time.monotonic() + 5.2
        last = active
        while time.monotonic() < deadline:
            last = self.status()
            time.sleep(.08)
        self.assertFalse(last['active'])
        self.assertEqual(last['reason'], 'lease_expired')
        self.assertEqual(last['revision'], active['revision'] + 1)
        self.assertGreater(before, last['remaining_ms'])

    def test_network_loss_clock_gap_and_regression_fail_closed(self):
        active = self.start()
        (self.root / 'keep-awake-network').write_text('0')
        time.sleep(.06)
        lost = self.status()
        self.assertFalse(lost['active'])
        self.assertEqual(lost['reason'], 'network_lost')
        self.assertEqual(self.call('POST', '/keep-awake/lease', self.command(lost))[0], 503)
        (self.root / 'keep-awake-network').write_text('1')
        time.sleep(.04)
        active = self.start()
        (self.root / 'keep-awake-clock-offset').write_text('7000')
        time.sleep(.06)
        gap = self.status()
        self.assertFalse(gap['active'])
        self.assertEqual(gap['reason'], 'worker_gap')
        self.assertEqual(gap['revision'], active['revision'] + 1)
        active = self.start()
        (self.root / 'keep-awake-clock-offset').write_text('0')
        time.sleep(.06)
        regression = self.status()
        self.assertFalse(regression['active'])
        self.assertEqual(regression['reason'], 'clock_regression')
        self.assertLessEqual(regression['last_tick_ms'], regression['clock_ms'])

    def test_tick_failure_is_immediate_and_fail_closed(self):
        (self.root / 'keep-awake-tick-result').write_text('-7')
        before = self.status()
        code, failed = self.call('POST', '/keep-awake/lease', self.command(before))
        self.assertEqual(code, 503, failed)
        self.assertFalse(failed['active'])
        self.assertEqual(failed['reason'], 'tick_failed')
        self.assertEqual(failed['tick_result'], -7)
        self.assertEqual(failed['revision'], before['revision'] + 2)

    def test_actual_pc_client_and_regressed_clock_status(self):
        client = KeepAwakeClient(provider=lambda: {'host': '127.0.0.1', 'port': 17866, 'token': ADMIN},
                                 port=self.port)
        before = client.status()
        lease, job = uuid.uuid4().hex, uuid.uuid4().hex
        active = client.mutate(before['revision'], 5000, 30000, before['instance_id'], lease, job, BUILD)
        self.assertTrue(active['active'])
        (self.root / 'keep-awake-clock-offset').write_text('-1000')
        time.sleep(.06)
        regressed = client.status()
        self.assertFalse(regressed['active'])
        self.assertEqual(regressed['reason'], 'clock_regression')
        self.assertLessEqual(regressed['last_tick_ms'], regressed['clock_ms'])

    def test_strict_framing_and_reserved_fields(self):
        before = self.status()
        wire = bytearray(self.command(before))
        wire[20] = 1
        self.assertEqual(self.call('POST', '/keep-awake/lease', wire)[0], 400)
        self.assertEqual(self.call('POST', '/keep-awake/lease', bytes(127))[0], 400)
        self.assertEqual(self.call('POST', '/keep-awake/lease', bytes(129))[0], 400)
        self.assertEqual(self.call('POST', '/keep-awake/lease', wire,
                                   headers={'Content-Type': 'text/plain'})[0], 400)
        self.assertEqual(self.call('GET', '/keep-awake/status', b'x')[0], 400)
        self.assertEqual(self.call('POST', '/keep-awake/lease', wire,
                                   headers={'Expect': '100-continue'})[0], 400)
        self.assertEqual(self.status()['revision'], before['revision'])

    def test_slow_client_cannot_starve_ticks_or_lease_admission(self):
        active = self.start(ttl=30000)
        sockets = []
        try:
            for _ in range(1):
                sock = socket.create_connection(('127.0.0.1', self.port), timeout=2)
                sock.sendall(b'GET /keep-awake/status HTTP/1.1\r\nHost: fixture\r\n')
                sockets.append(sock)
            begin = time.monotonic()
            current = self.status()
            self.assertLess(time.monotonic() - begin, 2.7)
            self.assertTrue(current['active'])
            time.sleep(.2)
            current = self.status()
            self.assertGreater(current['tick_count'], active['tick_count'])
            code, renewal = self.call('POST', '/keep-awake/lease', self.command(current, duration=0))
            self.assertEqual(code, 200, renewal)
        finally:
            for sock in sockets:
                sock.close()

    def test_fragmented_post_after_450ms_is_accepted(self):
        before = self.status()
        wire = self.command(before)
        with socket.create_connection(('127.0.0.1', self.port), timeout=3) as sock:
            headers = ('POST /keep-awake/lease HTTP/1.1\r\nHost: fixture\r\n'
                       'Authorization: Bearer ' + ADMIN + '\r\n'
                       'Content-Type: application/octet-stream\r\nContent-Length: 128\r\n\r\n')
            sock.sendall(headers.encode() + wire[:64])
            time.sleep(.45)
            sock.sendall(wire[64:])
            response = http.client.HTTPResponse(sock)
            response.begin()
            observed = json.loads(response.read())
            self.assertEqual(response.status, 200, observed)
            self.assertTrue(observed['active'])
            self.assertEqual(observed['revision'], before['revision'] + 1)

    def test_partial_client_does_not_delay_worker_shutdown(self):
        with socket.create_connection(('127.0.0.1', self.port), timeout=3) as sock:
            sock.sendall(b'GET /keep-awake/status HTTP/1.1\r\nHost: fixture\r\n')
            time.sleep(.05)
            begin = time.monotonic()
            self.process.terminate()
            output, error = self.process.communicate(timeout=1)
            self.assertLess(time.monotonic() - begin, .7)
            self.assertEqual(self.process.returncode, 0, (output + error).decode())


if __name__ == '__main__':
    unittest.main()
