"""Exercise the real resident C request/file code using POSIX adapters, not Vita APIs."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest
import uuid

TOKEN = '1' * 32


class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        (cls.root / 'inbox').mkdir()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            cls.port = sock.getsockname()[1]
        cls.proc = subprocess.Popen(['build/resident/host-server', str(cls.root), str(cls.port), TOKEN], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', cls.port), timeout=.1):
                    break
            except OSError:
                if cls.proc.poll() is not None:
                    raise RuntimeError(cls.proc.communicate())
                time.sleep(.05)
        else:
            raise RuntimeError('Host fixture did not start')

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        stdout, stderr = cls.proc.communicate(timeout=10)
        cls.temp.cleanup()
        if cls.proc.returncode != 0 or b'AddressSanitizer' in stderr or b'runtime error:' in stderr:
            raise AssertionError((cls.proc.returncode, stdout, stderr))

    def call(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        try:
            connection.request(method, path, body, {'Authorization': 'Bearer ' + TOKEN, **(headers or {})})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def raw(self, request):
        with socket.create_connection(('127.0.0.1', self.port), timeout=10) as sock:
            sock.sendall(request)
            response = bytearray()
            while block := sock.recv(4096):
                response.extend(block)
        return bytes(response)

    def test_authenticated_heartbeat_and_device_status(self):
        code, data = self.call('GET', '/status')
        self.assertEqual(code, 200)
        before = json.loads(data)
        time.sleep(.6)
        after = json.loads(self.call('GET', '/status')[1])
        self.assertEqual(after['started_ms'], before['started_ms'])
        self.assertGreater(after['heartbeat'], before['heartbeat'])
        self.assertEqual(after['battery_percent'], 73)  # Explicitly synthetic host sample.
        self.assertFalse(after['keep_awake'])

    def test_binary_upload_hash_storage_readback_and_download(self):
        for size in [1, 55, 56, 63, 64, 65, 4095, 16385, 131071, 8 * 1024 * 1024]:
            with self.subTest(size=size):
                payload = (bytes(range(256)) * ((size + 255) // 256))[:size]
                attempt = uuid.uuid4().hex
                digest = hashlib.sha256(payload).hexdigest()
                code, data = self.call('POST', f'/upload/{attempt}/package.vpk', payload, {'X-SHA256': digest})
                self.assertEqual(code, 201, data)
                result = json.loads(data)
                self.assertEqual(result['sha256'], digest)
                self.assertTrue(result['storage_readback'])
                final = self.root / 'inbox' / attempt / 'package.vpk'
                self.assertEqual(final.read_bytes(), payload)
                self.assertFalse(final.with_suffix('.vpk.part').exists())
                self.assertEqual(self.call('GET', f'/files/{attempt}/package.vpk'), (200, payload))

    def test_unauthorized_upload_makes_no_directory(self):
        attempt = uuid.uuid4().hex
        code, _ = self.call('POST', f'/upload/{attempt}/probe.bin', b'abc', {'Authorization': 'Bearer ' + '2' * 32, 'X-SHA256': hashlib.sha256(b'abc').hexdigest()})
        self.assertEqual(code, 401)
        self.assertFalse((self.root / 'inbox' / attempt).exists())

    def test_hash_mismatch_retains_part_without_publication(self):
        attempt = uuid.uuid4().hex
        self.assertEqual(self.call('POST', f'/upload/{attempt}/probe.bin', b'abc', {'X-SHA256': '0' * 64})[0], 422)
        self.assertEqual((self.root / 'inbox' / attempt / 'probe.bin.part').read_bytes(), b'abc')
        self.assertFalse((self.root / 'inbox' / attempt / 'probe.bin').exists())
        self.assertEqual(self.call('GET', f'/files/{attempt}/probe.bin.part')[0], 404)

    def test_attempt_replay_does_not_overwrite(self):
        attempt = uuid.uuid4().hex
        path = f'/upload/{attempt}/probe.bin'
        digest = hashlib.sha256(b'first').hexdigest()
        self.assertEqual(self.call('POST', path, b'first', {'X-SHA256': digest})[0], 201)
        self.assertEqual(self.call('POST', path, b'next', {'X-SHA256': hashlib.sha256(b'next').hexdigest()})[0], 409)
        self.assertEqual((self.root / 'inbox' / attempt / 'probe.bin').read_bytes(), b'first')

    def test_disconnect_does_not_publish_and_server_recovers(self):
        attempt = uuid.uuid4().hex
        with socket.create_connection(('127.0.0.1', self.port), timeout=10) as sock:
            sock.sendall((f'POST /upload/{attempt}/probe.bin HTTP/1.1\r\nAuthorization: Bearer {TOKEN}\r\nContent-Length: 10\r\nX-SHA256: {"0" * 64}\r\n\r\nabc').encode())
            sock.shutdown(socket.SHUT_WR)
            while sock.recv(4096):
                pass
        self.assertFalse((self.root / 'inbox' / attempt / 'probe.bin').exists())
        self.assertEqual(self.call('GET', '/status')[0], 200)

    def test_disk_failures_do_not_publish(self):
        for fault in ['write', 'read', 'corrupt-read', 'close', 'rename']:
            with self.subTest(fault=fault):
                attempt = uuid.uuid4().hex
                (self.root / ('fault-' + fault)).touch()
                code, _ = self.call('POST', f'/upload/{attempt}/probe.bin', b'abc', {'X-SHA256': hashlib.sha256(b'abc').hexdigest()})
                self.assertIn(code, [408, 500])
                self.assertFalse((self.root / 'inbox' / attempt / 'probe.bin').exists())
                self.assertTrue((self.root / 'inbox' / attempt / 'probe.bin.part').exists())
                self.assertFalse((self.root / ('fault-' + fault)).exists())
                self.assertEqual(self.call('GET', '/status')[0], 200)

    def test_short_disk_write_is_completed(self):
        attempt = uuid.uuid4().hex
        (self.root / 'fault-partial-write').touch()
        payload = bytes(range(256)) * 16
        code, _ = self.call('POST', f'/upload/{attempt}/probe.bin', payload, {'X-SHA256': hashlib.sha256(payload).hexdigest()})
        self.assertEqual(code, 201)
        self.assertEqual((self.root / 'inbox' / attempt / 'probe.bin').read_bytes(), payload)

    def test_stalled_upload_times_out_and_recovers(self):
        attempt = uuid.uuid4().hex
        began = time.monotonic()
        with socket.create_connection(('127.0.0.1', self.port), timeout=10) as sock:
            sock.sendall((f'POST /upload/{attempt}/probe.bin HTTP/1.1\r\nAuthorization: Bearer {TOKEN}\r\nContent-Length: 10\r\nX-SHA256: {"0" * 64}\r\n\r\nabc').encode())
            response = bytearray()
            while block := sock.recv(4096):
                response.extend(block)
        self.assertIn(b'408 Result', response)
        self.assertLess(time.monotonic() - began, 8)
        self.assertFalse((self.root / 'inbox' / attempt / 'probe.bin').exists())
        self.assertEqual(self.call('GET', '/status')[0], 200)

    def test_refuses_paths_bad_framing_and_oversized_length(self):
        before = set(self.root.joinpath('inbox').iterdir())
        for request in [
            f'GET /status HTTP/1.1\r\nAuthorization: Bearer {TOKEN}\r\nContent-Length: 0\r\nContent-Length: 0\r\n\r\n',
            f'GET /status HTTP/1.1\r\nAuthorization: Bearer {TOKEN}\r\nTransfer-Encoding: chunked\r\n\r\n',
            f'GET /status HTTP/1.1\r\nAuthorization: Bearer {TOKEN}\r\nAuthorization: Bearer {TOKEN}\r\n\r\n',
            f'POST /upload/{uuid.uuid4().hex}/package.vpk HTTP/1.1\r\nAuthorization: Bearer {TOKEN}\r\nContent-Length: 8388609\r\n\r\n',
            f'POST /upload/../../ur0/tai/config.txt HTTP/1.1\r\nAuthorization: Bearer {TOKEN}\r\nContent-Length: 3\r\nX-SHA256: {"0" * 64}\r\n\r\nabc',
        ]:
            with self.subTest(request=request[:60]):
                response = self.raw(request.encode())
                self.assertIn(response.split(b' ')[1], [b'400', b'413'])
        self.assertEqual(set(self.root.joinpath('inbox').iterdir()), before)
        self.assertEqual(self.call('GET', '/status')[0], 200)


if __name__ == '__main__':
    unittest.main(verbosity=2)
