"""Actual Resident C HTTP/storage integration; native submission is synthetic."""
import http.client
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest
import uuid

ADMIN = '1' * 32
BUILD = 'a' * 64
DEVBUILD = 'f' * 64


class LaunchServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'inbox').mkdir()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.process = None
        self.logs = []

    def start(self, enabled=False, successful=False):
        if enabled:
            (self.root / 'fixture-enable-launch').touch()
        if successful:
            (self.root / 'fixture-launch-success').touch()
        log = (self.root / ('server-' + str(len(self.logs)) + '.log')).open('wb')
        self.logs.append(log)
        self.process = subprocess.Popen(['build/resident/host-server', str(self.root), str(self.port), ADMIN],
                                        stdout=log, stderr=log)
        # Docker bind mounts on Windows can take longer than two seconds to
        # create the initial durable stores. Bound readiness by elapsed time.
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                if self.call('GET', '/status')[0] == 200:
                    return
            except OSError:
                pass
            if self.process.poll() is not None:
                raise RuntimeError('Host service exited before readiness')
            time.sleep(.02)
        raise RuntimeError('Host readiness deadline')

    def stop(self):
        if self.process is not None:
            self.process.terminate()
            self.assertEqual(self.process.wait(timeout=10), 0)
            self.process = None

    def tearDown(self):
        self.stop()
        for log in self.logs:
            log.close()
            text = Path(log.name).read_text()
            self.assertNotIn('AddressSanitizer', text)
            self.assertNotIn('runtime error:', text)
        self.temp.cleanup()

    def call(self, method, path, body=None, token=ADMIN, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        try:
            if isinstance(body, dict):
                body = json.dumps(body).encode()
            connection.request(method, path, body, {'Authorization': 'Bearer ' + token,
                               'Content-Type': 'application/json', **(headers or {})})
            response = connection.getresponse()
            data = response.read()
            return response.status, json.loads(data)
        finally:
            connection.close()

    def status(self):
        code, value = self.call('GET', '/devloop-launch/status')
        self.assertEqual(code, 200, value)
        return value

    def request(self, **changes):
        status = self.status()
        return {'attempt': uuid.uuid4().hex, 'title_id': 'CHRS00003', 'expected_devloop_build': DEVBUILD,
                'resident_build_id': BUILD, 'instance_id': status['instance_id'],
                'issued_ms': status['now_ms'], 'ttl_ms': 10000, **changes}

    def receipt(self, attempt, state=None):
        for _ in range(100):
            code, value = self.call('GET', '/devloop-launch/' + attempt)
            self.assertEqual(code, 200, value)
            if state is None or value['state'] == state:
                return value
            time.sleep(.01)
        self.fail(value)

    def records(self):
        return list((self.root / 'launch-v1').glob('record-*.bin'))

    def test_disabled_candidate_identity_and_inventory_are_inspection_only(self):
        self.start()
        before = self.status()
        after = self.status()
        self.assertEqual(len(before['instance_id']), 32)
        self.assertEqual(before['instance_id'], after['instance_id'])
        self.assertGreaterEqual(after['now_ms'], before['now_ms'])
        self.assertFalse(before['enabled'])
        self.assertFalse(before['blocked'])
        self.assertEqual(before['resident_build_id'], BUILD)
        code, value = self.call('GET', '/devloop-launch/inventory')
        self.assertEqual(code, 200)
        self.assertTrue(value['host_fixture'])
        for field in ['foreground_verified', 'protected_ui_verified', 'native_submission_enabled']:
            self.assertFalse(value[field])
        self.assertEqual(self.records(), [])
        self.assertFalse((self.root / 'fixture-launch-called').exists())
        self.assertEqual(self.call('GET', '/status')[1]['version'], '0.1.5')

    def test_disabled_valid_offer_does_not_claim_or_launch(self):
        self.start()
        self.assertEqual(self.call('POST', '/devloop-launch', self.request())[0], 403)
        self.assertEqual(self.records(), [])
        self.assertFalse((self.root / 'fixture-launch-called').exists())

    def test_namespace_is_admin_only_including_inventory_and_receipts(self):
        self.start(enabled=True, successful=True)
        for path in ['/devloop-launch/status', '/devloop-launch/inventory', '/devloop-launch/' + 'd' * 32]:
            self.assertEqual(self.call('GET', path, token='2' * 32)[0], 403)
        self.assertEqual(self.call('POST', '/devloop-launch', self.request(), token='2' * 32)[0], 403)
        self.assertEqual(self.records(), [])

    def test_strict_json_before_any_claim(self):
        self.start(enabled=True, successful=True)
        valid = self.request()
        for key, bad in [('issued_ms', True), ('issued_ms', -1), ('issued_ms', 2**64),
                         ('ttl_ms', False), ('ttl_ms', 2**32), ('ttl_ms', 1.5),
                         ('ttl_ms', 0), ('attempt', 'd' * 31), ('title_id', 'CHRS00012')]:
            with self.subTest(key=key, bad=bad):
                self.assertEqual(self.call('POST', '/devloop-launch', {**valid, key: bad})[0], 400)
        raw = json.dumps(valid)
        for body in [raw[:-1] + ',"ttl_ms":10000}', raw[:-1] + ',"admin":true}',
                     raw.replace('ttl_ms', 'ttl_\\u006ds'), raw + ' trailing', raw[:12] + '\0' + raw[12:]]:
            self.assertEqual(self.call('POST', '/devloop-launch', body.encode())[0], 400)
        self.assertEqual(self.records(), [])
        self.assertFalse((self.root / 'fixture-launch-called').exists())

    def test_real_http_queue_then_post_close_simulated_submission_once(self):
        self.start(enabled=True, successful=True)
        request = self.request()
        code, accepted = self.call('POST', '/devloop-launch', request)
        self.assertEqual(code, 202)
        self.assertEqual(accepted['state'], 'queued')
        self.assertEqual(accepted['dispatch_count'], 0)
        final = self.receipt(request['attempt'], 'submitted')
        self.assertEqual(final['dispatch_count'], 1)
        self.assertTrue(final['native_confirmed'])
        self.assertEqual((self.root / 'fixture-launch-called').read_bytes(), b'CHRS00003\n')
        self.assertEqual(len(self.records()), 3)
        self.assertTrue(all(p.stat().st_size == 543 for p in self.records()))
        self.assertEqual(self.call('POST', '/devloop-launch', request)[0], 409)
        self.assertEqual(len(self.records()), 3)

    def test_response_send_loss_leaves_unknown_and_never_submits(self):
        self.start(enabled=True, successful=True)
        request = self.request()
        (self.root / 'fault-launch-send').touch()
        with self.assertRaises((http.client.HTTPException, OSError)):
            self.call('POST', '/devloop-launch', request)
        receipt = self.receipt(request['attempt'], 'unknown')
        self.assertEqual(receipt['reason'], 'response_incomplete')
        self.assertEqual(receipt['dispatch_count'], 0)
        self.assertFalse((self.root / 'fixture-launch-called').exists())
        self.assertEqual(self.call('POST', '/devloop-launch', self.request())[0], 409)

    def test_close_failure_never_submits_even_when_reply_sent(self):
        self.start(enabled=True, successful=True)
        request = self.request()
        (self.root / 'fault-launch-close').touch()
        self.assertEqual(self.call('POST', '/devloop-launch', request)[0], 202)
        receipt = self.receipt(request['attempt'], 'unknown')
        self.assertEqual(receipt['dispatch_count'], 0)
        self.assertEqual(receipt['reason'], 'response_incomplete')
        self.assertFalse((self.root / 'fixture-launch-called').exists())

    def test_rng_failure_retained_and_ordinary_service_survives(self):
        (self.root / 'fault-launch-rng').touch()
        self.start()
        self.assertEqual(self.call('GET', '/devloop-launch/status')[0], 503)
        (self.root / 'fault-launch-rng').unlink()
        self.assertEqual(self.call('GET', '/devloop-launch/status')[0], 503)
        self.assertEqual(self.call('GET', '/status')[0], 200)
        self.assertEqual(self.call('GET', '/devloop-launch/inventory')[0], 200)
        self.stop()
        self.start()
        self.assertEqual(len(self.status()['instance_id']), 32)

    def test_torn_store_kept_and_ordinary_service_survives(self):
        directory = self.root / 'launch-v1'
        directory.mkdir()
        torn = directory / 'record-001.bin'
        torn.write_bytes(b'torn retained claim')
        self.start()
        self.assertEqual(self.call('GET', '/devloop-launch/status')[0], 503)
        self.assertEqual(self.call('GET', '/status')[0], 200)
        self.assertEqual(self.call('GET', '/devloop-launch/inventory')[0], 200)
        self.assertEqual(torn.read_bytes(), b'torn retained claim')

    def test_restart_changes_instance_invalidates_receipt_and_never_replays(self):
        self.start(enabled=True, successful=True)
        before = self.status()
        request = self.request()
        self.assertEqual(self.call('POST', '/devloop-launch', request)[0], 202)
        self.receipt(request['attempt'], 'submitted')
        marker = (self.root / 'fixture-launch-called').stat().st_mtime_ns
        self.stop()
        self.start()
        after = self.status()
        self.assertNotEqual(before['instance_id'], after['instance_id'])
        receipt = self.receipt(request['attempt'], 'unknown')
        self.assertEqual(receipt['reason'], 'restart')
        self.assertEqual(receipt['instance_id'], before['instance_id'])
        self.assertEqual(receipt['samples'], 0)
        self.assertEqual(self.call('POST', '/devloop-launch', request)[0], 412)
        self.assertEqual((self.root / 'fixture-launch-called').stat().st_mtime_ns, marker)

    def test_pin_title_and_expiry_rejections_leave_no_records(self):
        self.start(enabled=True, successful=True)
        for changes, expected in [({'instance_id': 'b' * 32}, 412), ({'resident_build_id': 'b' * 64}, 412),
                                  ({'title_id': 'CHRS00012'}, 400), ({'issued_ms': 0}, 412)]:
            self.assertEqual(self.call('POST', '/devloop-launch', self.request(**changes))[0], expected)
        self.assertEqual(self.records(), [])

    def test_framing_bounds_and_inventory_method_refuse(self):
        self.start(enabled=True, successful=True)
        self.assertEqual(self.call('POST', '/devloop-launch', b'x' * 2049)[0], 413)
        self.assertEqual(self.call('POST', '/devloop-launch', self.request(), headers={'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.call('GET', '/devloop-launch/status', b'a')[0], 400)
        self.assertEqual(self.call('POST', '/devloop-launch/inventory', b'{}')[0], 400)
        self.assertEqual(self.call('GET', '/devloop-launch/observe')[0], 404)
        self.assertEqual(self.records(), [])

    def test_failed_claim_keeps_torn_bytes_and_blocks_broker_only(self):
        self.start(enabled=True, successful=True)
        request = self.request()
        (self.root / 'fault-write').touch()
        self.assertEqual(self.call('POST', '/devloop-launch', request)[0], 503)
        self.assertTrue(self.status()['blocked'])
        self.assertEqual(self.receipt(request['attempt'])['state'], 'unknown')
        self.assertEqual(self.call('GET', '/status')[0], 200)
        self.assertFalse((self.root / 'fixture-launch-called').exists())
        files = self.records()
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].read_bytes(), b'')
        self.stop()
        self.start()
        self.assertEqual(self.call('GET', '/devloop-launch/status')[0], 503)
        self.assertEqual(files[0].read_bytes(), b'')


if __name__ == '__main__':
    unittest.main(verbosity=2)
