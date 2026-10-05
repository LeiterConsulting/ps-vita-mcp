"""Actual two C services with POSIX/clock/SDK adapters; approval here is simulated."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time
import unittest
import uuid

ADMIN = '1' * 32  # Fixture only, never a device token.
CONTROL_BUILD = 'c' * 64


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class PairingHTTP(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.resident = self.root / 'resident'
        self.control = self.root / 'control'
        (self.resident / 'inbox').mkdir(parents=True)
        (self.control / 'workspace').mkdir(parents=True)
        self.rport, self.cport = free_port(), free_port()
        self.processes, self.logs = [], []
        self.start_resident()
        env = {**os.environ, 'PR_RESIDENT_PORT': str(self.rport)}
        self.start('build/resident/control/host-server', self.control, self.cport, env)
        self.client, self.nonce = uuid.uuid4().hex, uuid.uuid4().hex

    def start(self, executable, root, port, env=None):
        log = (root / f'server-{len(self.logs)}.log').open('wb')
        proc = subprocess.Popen([executable, str(root), str(port), ADMIN], stdout=log, stderr=log, env=env)
        self.processes.append(proc)
        self.logs.append(log)
        for _ in range(100):
            try:
                if self.call('GET', '/status', port=port, token=ADMIN)[0] == 200:
                    return proc
            except OSError:
                pass
            if proc.poll() is not None:
                raise RuntimeError('Fixture exited before readiness')
            time.sleep(.02)
        raise RuntimeError('Fixture readiness deadline')

    def start_resident(self):
        self.rproc = self.start('build/resident/host-server', self.resident, self.rport)

    def tearDown(self):
        for p in self.processes:
            if p.poll() is None:
                p.terminate()
            self.assertEqual(p.wait(timeout=10), 0)
        for log in self.logs:
            log.close()
            text = Path(log.name).read_text(encoding='utf-8')
            self.assertNotIn('AddressSanitizer', text)
            self.assertNotIn('runtime error:', text)
        self.temp.cleanup()

    def call(self, method, path, body=None, token=None, port=None, headers=None):
        h = dict(headers or {})
        if token is not None:
            h['Authorization'] = 'Bearer ' + token
        if isinstance(body, dict):
            body = json.dumps(body, ensure_ascii=False).encode('utf-8')
            h['Content-Type'] = 'application/json'
        conn = http.client.HTTPConnection('127.0.0.1', port or self.rport, timeout=5)
        try:
            conn.request(method, path, body, h)
            result = conn.getresponse()
            data = result.read()
            self.assertEqual(result.getheader('Cache-Control'), 'no-store')
            return result.status, data
        finally:
            conn.close()

    def ui(self, action, **fields):
        return self.call('POST', '/pairing/ui/' + action, {'protocol': 1, **fields}, ADMIN)

    def request(self):
        return self.call('POST', '/pairing/request', {'protocol': 1, 'client_id': self.client,
                        'client_nonce': self.nonce, 'client_name': 'Phone "one" 日本'})

    def pairing(self):
        self.assertEqual(self.ui('open', control_build_id=CONTROL_BUILD)[0], 200)
        code, data = self.request()
        self.assertEqual(code, 201)
        req = json.loads(data)['request_id']
        self.binding = {'protocol': 1, 'request_id': req, 'client_id': self.client, 'client_nonce': self.nonce}
        self.assertEqual(self.call('POST', '/pairing/confirm', {**self.binding, 'code': '000007'})[0], 403)
        digest = hashlib.sha256(('VitaPairing1' + req + self.client + self.nonce + '000007').encode()).hexdigest()
        code, approved = self.ui('approve', **{k: v for k, v in self.binding.items() if k != 'protocol'}, code_sha256=digest)
        self.assertEqual(code, 200)
        self.assertNotIn(b'000007', approved)
        code, data = self.call('POST', '/pairing/confirm', {**self.binding, 'code': '000007'})
        self.assertEqual(code, 200)
        receipt = json.loads(data)
        self.assertEqual(receipt['expires_at'] - receipt['last_seen_at'], 7776000)
        return receipt

    def end_window(self):
        # Only the POSIX fixture clock advances; production code has no such input.
        (self.resident / 'fixture-ms-offset').write_text('120001', encoding='ascii')

    def test_public_probe_and_exact_protected_control_gate(self):
        code, data = self.call('GET', '/pairing/info')
        info = json.loads(data)
        self.assertEqual(code, 200)
        self.assertEqual((info['resident_version'], info['control_version']), ('0.1.2', '0.3.4'))
        self.assertEqual(info['control_build_id'], CONTROL_BUILD)
        self.assertFalse(info['pairing_open'])
        self.assertNotIn('token', info)
        self.assertEqual(self.request()[0], 403)
        self.assertEqual(self.ui('open', control_build_id='a' * 64)[0], 403)
        self.assertEqual(self.call('POST', '/pairing/ui/open', {'protocol': 1, 'control_build_id': CONTROL_BUILD})[0], 403)
        (self.resident / 'fault-pair-lan').touch()
        self.assertEqual(self.ui('open', control_build_id=CONTROL_BUILD)[0], 403)

    def test_confirmation_recovery_and_secret_boundaries(self):
        receipt = self.pairing()
        again = json.loads(self.call('POST', '/pairing/confirm', {**self.binding, 'code': '000007'})[1])
        self.assertEqual(again, receipt)
        listing = json.loads(self.ui('list')[1])
        self.assertEqual(len(listing['phones']), 1)
        self.assertEqual(listing['phones'][0]['client_name'], 'Phone "one" 日本')
        token = receipt['token'].encode()
        for path in (self.resident / 'private').glob('*'):
            self.assertNotIn(token, path.read_bytes())
            self.assertNotIn(b'000007', path.read_bytes())
        session = json.loads(self.call('GET', '/pairing/session', token=receipt['token'])[1])
        self.assertNotIn('token', session)
        self.assertEqual(session['credential_id'], receipt['credential_id'])
        self.assertEqual(self.call('GET', '/pairing/session', token=ADMIN)[0], 401)

    def test_actual_lost_confirmation_reply_recovers_one_credential(self):
        self.assertEqual(self.ui('open', control_build_id=CONTROL_BUILD)[0], 200)
        req = json.loads(self.request()[1])['request_id']
        binding = {'protocol': 1, 'request_id': req, 'client_id': self.client, 'client_nonce': self.nonce}
        digest = hashlib.sha256(('VitaPairing1' + req + self.client + self.nonce + '000007').encode()).hexdigest()
        self.assertEqual(self.ui('approve', **{k: v for k, v in binding.items() if k != 'protocol'}, code_sha256=digest)[0], 200)
        body = json.dumps({**binding, 'code': '000007'}).encode()
        with socket.create_connection(('127.0.0.1', self.rport), timeout=5) as sock:
            sock.sendall(b'POST /pairing/confirm HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(body)).encode() + b'\r\nConnection: close\r\n\r\n' + body)
            # Drop the response, not the request. Native commit must be observable.
        time.sleep(.1)
        self.assertEqual(json.loads(self.ui('poll')[1])['approval_state'], 'complete')
        first = json.loads(self.call('POST', '/pairing/confirm', {**binding, 'code': '000007'})[1])
        again = json.loads(self.call('POST', '/pairing/confirm', {**binding, 'code': '000007'})[1])
        self.assertEqual(first, again)
        self.assertEqual(len(json.loads(self.ui('list')[1])['phones']), 1)

    def test_native_rejection_and_wrong_attempt_limit(self):
        self.assertEqual(self.ui('open', control_build_id=CONTROL_BUILD)[0], 200)
        req = json.loads(self.request()[1])['request_id']
        binding = {'request_id': req, 'client_id': self.client, 'client_nonce': self.nonce}
        self.assertEqual(self.ui('reject', **binding)[0], 200)
        self.assertEqual(json.loads(self.ui('poll')[1])['approval_state'], 'rejected')
        self.assertEqual(self.call('POST', '/pairing/confirm', {'protocol': 1, **binding, 'code': '000007'})[0], 403)
        self.nonce = uuid.uuid4().hex
        receipt = self.pairing()
        for n in range(5):
            self.assertEqual(self.call('POST', '/pairing/confirm', {**self.binding, 'code': '123456'})[0], 409 if n == 4 else 422)
        self.assertEqual(self.ui('open', control_build_id=CONTROL_BUILD)[0], 429)
        # Exhausting recovery does not revoke the already confirmed phone.
        self.assertEqual(self.call('GET', '/pairing/session', token=receipt['token'])[0], 200)

    def test_shared_phone_inspection_and_no_write_authority(self):
        receipt = self.pairing()
        self.end_window()
        token = receipt['token']
        for route in ['/status', '/power/status', '/screen/preview', '/screen/detail/rle']:
            self.assertEqual(self.call('GET', route, token=token, port=self.cport)[0], 200)
        self.assertEqual(self.call('GET', '/status', token=token)[0], 200)
        for route in ['/input', '/release', '/power/lease', '/app/launch/CHRS00003', '/workspace/write/' + 'a' * 32 + '/x']:
            self.assertEqual(self.call('POST', route, b'', token, self.cport)[0], 403)
        self.assertEqual(self.call('GET', '/workspace/list/0/' + 'a' * 32, token=token, port=self.cport)[0], 403)
        self.assertEqual(self.call('POST', '/upload/' + 'a' * 32 + '/x.vpk', b'x', token)[0], 403)
        state = json.loads(self.call('GET', '/status', token=ADMIN, port=self.cport)[1])
        self.assertEqual(state['lease_remaining_ms'], 0)
        self.assertEqual(state['work_remaining_ms'], 0)
        old = receipt['last_seen_at']
        time.sleep(1.05)
        self.assertEqual(self.call('GET', '/screen/preview', token=token, port=self.cport)[0], 200)
        renewed = json.loads(self.call('GET', '/pairing/session', token=token)[1])
        self.assertGreater(renewed['last_seen_at'], old)
        self.assertEqual(renewed['expires_at'] - renewed['last_seen_at'], 7776000)

    def test_revoke_and_restart_share_authority(self):
        receipt = self.pairing()
        self.assertEqual(self.ui('revoke', credential_id=receipt['credential_id'])[0], 200)
        self.assertEqual(self.call('GET', '/status', token=receipt['token'], port=self.cport)[0], 401)
        self.rproc.terminate()
        self.assertEqual(self.rproc.wait(timeout=10), 0)
        self.start_resident()
        self.assertEqual(self.call('GET', '/pairing/session', token=receipt['token'])[0], 401)
        self.assertEqual(self.call('GET', '/status', token=ADMIN)[0], 200)
        self.assertEqual(self.call('GET', '/status', token=ADMIN, port=self.cport)[0], 200)

    def test_control_reregisters_after_resident_restart_without_helper_reload(self):
        self.rproc.terminate()
        self.assertEqual(self.rproc.wait(timeout=10), 0)
        self.start_resident()
        end = time.monotonic() + 7
        while time.monotonic() < end:
            info = json.loads(self.call('GET', '/pairing/info')[1])
            if info['control_build_id'] == CONTROL_BUILD:
                break
            time.sleep(.1)
        else:
            self.fail('Existing Control did not reregister with restarted authority')
        self.assertEqual(self.ui('open', control_build_id=CONTROL_BUILD)[0], 200)

    def test_native_privacy_denies_admin_and_phone_capture_and_input(self):
        token = self.pairing()['token']
        self.end_window()
        payload = struct.pack('<13Ii', 0x31495256, 2, 100, 0x4000, 0, 128, 128, 128, 128, 0, 0, 0, 0, 77)
        for fault in ['starter', 'title-fail']:
            (self.control / ('fault-' + fault)).touch()
            for credential in [ADMIN, token]:
                self.assertEqual(self.call('GET', '/screen/preview', token=credential, port=self.cport)[0], 503)
            self.assertEqual(self.call('POST', '/input', payload, ADMIN, self.cport)[0], 409)
            (self.control / 'fault-normal-title').touch()
            self.assertEqual(self.call('GET', '/screen/preview', token=ADMIN, port=self.cport)[0], 200)

    def test_persistence_failure_and_ambiguous_parts_fail_closed(self):
        token = self.pairing()['token']
        time.sleep(1.05)
        (self.resident / 'fault-pair-sync').touch()
        self.assertEqual(self.call('GET', '/pairing/session', token=token)[0], 503)
        self.assertEqual(self.call('GET', '/status', token=ADMIN)[0], 200)

        self.assertEqual(self.call('GET', '/status', token=token, port=self.cport)[0], 503)
        self.assertTrue(list((self.resident / 'private').glob('*.part')))
        self.rproc.terminate()
        self.rproc.wait(timeout=10)
        self.start_resident()
        self.assertEqual(self.call('GET', '/pairing/info')[0], 503)
        self.assertEqual(self.call('GET', '/status', token=ADMIN)[0], 200)

    def test_active_code_globally_blocks_capture_and_authority_loss_fails_closed(self):
        token = self.pairing()['token']
        for credential in [ADMIN, token]:
            for route in ['/screen/preview', '/screen/detail/rle']:
                self.assertEqual(self.call('GET', route, token=credential, port=self.cport)[0], 503)
        self.end_window()
        self.assertEqual(self.call('GET', '/screen/preview', token=ADMIN, port=self.cport)[0], 200)
        self.rproc.terminate()
        self.rproc.wait(timeout=10)
        self.assertEqual(self.call('GET', '/screen/preview', token=ADMIN, port=self.cport)[0], 503)
        self.assertEqual(self.call('GET', '/status', token=ADMIN, port=self.cport)[0], 200)

    def test_utf8_framing_and_binding_rejected(self):
        self.assertEqual(self.ui('open', control_build_id=CONTROL_BUILD)[0], 200)
        code, data = self.request()
        first = json.loads(data)
        second = json.loads(self.request()[1])
        self.assertEqual(first['request_id'], second['request_id'])
        self.assertGreaterEqual(second['expires_in_seconds'], 1)
        self.assertLessEqual(second['expires_in_seconds'], 120)
        body = {'protocol': 1, 'request_id': first['request_id'], 'client_id': self.client, 'client_nonce': 'a' * 32, 'code': '000007'}
        self.assertEqual(self.call('POST', '/pairing/confirm', body)[0], 403)
        self.assertEqual(self.call('POST', '/pairing/request', b'x' * 1025, headers={'Content-Type': 'application/json'})[0], 413)
        self.assertEqual(self.call('POST', '/pairing/request', b'{"protocol":1}', headers={'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.call('POST', '/pairing/request', b'{"protocol":1,"protocol":1}', headers={'Content-Type': 'application/json'})[0], 400)
        self.assertEqual(self.call('GET', '/pairing/info', b'x')[0], 400)


if __name__ == '__main__':
    unittest.main(verbosity=2)
