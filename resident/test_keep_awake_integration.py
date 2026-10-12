"""Real serialized C upload plus independent C lease worker; no Vita involved."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from resident.keep_awake_client import KeepAwakeClient

TOKEN = '1' * 32


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class ParallelLeaseTests(unittest.TestCase):
    def test_renewal_and_ticks_continue_during_serial_upload_then_stop(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'inbox').mkdir()
            main_port, power_port = free_port(), free_port()
            process = subprocess.Popen(
                ['build/resident/host-server', str(root), str(main_port), TOKEN],
                env={**os.environ, 'VITA_RESIDENT_KEEP_AWAKE_TEST_PORT': str(power_port)},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            upload = None

            def call(method, path, body=None):
                connection = http.client.HTTPConnection('127.0.0.1', power_port, timeout=2)
                try:
                    connection.request(method, path, body, {'Authorization': 'Bearer ' + TOKEN,
                                                            'Content-Type': 'application/octet-stream'})
                    reply = connection.getresponse()
                    self.assertEqual(reply.status, 200)
                    return json.loads(reply.read())
                finally:
                    connection.close()

            lease_id, job_id = uuid.uuid4().hex, uuid.uuid4().hex
            client = KeepAwakeClient(lambda: {'host': '127.0.0.1', 'port': main_port, 'token': TOKEN},
                                     port=power_port)

            def mutate(state, ttl, duration=0):
                return client.mutate(state['revision'], ttl, duration, state['instance_id'],
                                     lease_id, job_id, state['resident_build_id'])

            try:
                for _ in range(100):
                    try:
                        state = call('GET', '/keep-awake/status')
                        break
                    except (OSError, http.client.HTTPException):
                        if process.poll() is not None:
                            raise AssertionError(process.communicate())
                        time.sleep(.05)
                else:
                    self.fail('Lease worker did not start')
                self.assertFalse(state['active'])
                state = mutate(state, 5000, 30000)
                first_tick = state['tick_count']
                first_revision = state['revision']
                payload = b'abcdefghij'
                attempt = uuid.uuid4().hex
                upload = socket.create_connection(('127.0.0.1', main_port), timeout=3)
                upload.sendall((f'POST /upload/{attempt}/probe.bin HTTP/1.1\r\n'
                                f'Authorization: Bearer {TOKEN}\r\nContent-Length: 10\r\n'
                                f'X-SHA256: {hashlib.sha256(payload).hexdigest()}\r\n\r\n').encode())
                # The main worker remains inside this request for over two TTLs.
                for byte in payload:
                    upload.sendall(bytes([byte]))
                    time.sleep(1.1)
                    observed = call('GET', '/keep-awake/status')
                    self.assertTrue(observed['active'])
                    state = mutate(observed, 5000)
                response = bytearray()
                while block := upload.recv(4096):
                    response.extend(block)
                self.assertIn(b' 201 ', response.split(b'\r\n')[0])
                self.assertEqual((root / 'inbox' / attempt / 'probe.bin').read_bytes(), payload)
                self.assertGreaterEqual(state['revision'] - first_revision, 10)
                self.assertGreaterEqual(state['tick_count'] - first_tick, 8)
                state = mutate(call('GET', '/keep-awake/status'), 0)
                self.assertFalse(state['active'])
                ended_count = state['tick_count']
                time.sleep(1.2)
                after = call('GET', '/keep-awake/status')
                self.assertFalse(after['active'])
                self.assertEqual(after['tick_count'], ended_count)
                self.assertEqual(after['revision'], state['revision'])
            finally:
                if upload is not None:
                    upload.close()
                process.terminate()
                output, errors = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, (output, errors))
                self.assertNotIn(b'AddressSanitizer', errors)
                self.assertNotIn(b'runtime error:', errors)


if __name__ == '__main__':
    unittest.main()
