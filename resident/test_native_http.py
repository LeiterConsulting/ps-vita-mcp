"""Actual C HTTP framing/auth/stream integration, with synthetic native adapters."""
import hashlib
import json
from pathlib import Path
import socket
import struct
import sys
import time
import unittest
import uuid

import test_launch_service as fixture

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from resident.lifecycle_client import LifecycleClient
from workbench.native_package import make_head


class NativeHTTPTests(unittest.TestCase):
    setUp = fixture.LaunchServiceTests.setUp
    tearDown = fixture.LaunchServiceTests.tearDown
    start = fixture.LaunchServiceTests.start
    stop = fixture.LaunchServiceTests.stop
    call = fixture.LaunchServiceTests.call

    def manifest(self):
        code, status = self.call('GET', '/native-lifecycle/status')
        self.assertEqual(code, 200, status)
        data = [b'SCE\0' + bytes(132) + b'VITA_NATIVE_LIFECYCLE_LAB:' + b'b' * 64, b'sfo', b'icon', b'bg',
                b'startup', b'template', b'license', bytes(0x430)]
        manifest = {'protocol': 1, 'project': 'lifecycle_lab', 'title_id': 'VMCP00001',
                    'version': '01.00', 'native_build_id': 'b' * 64,
                    'package_sha256': 'c' * 64, 'package_bytes': 2048,
                    'resident_build_id': fixture.BUILD, 'instance_id': status['instance_id'],
                    'attempt': uuid.uuid4().hex, 'issued_ms': status['clock_ms'], 'ttl_ms': 30000,
                    'files': [{'bytes': len(item), 'sha256': hashlib.sha256(item).hexdigest()}
                              for item in data]}
        return manifest, data

    def test_native_namespace_requires_administrator_and_strict_framing(self):
        self.start()
        self.assertEqual(self.call('GET', '/native-lifecycle/status', token='2' * 32)[0], 403)
        self.assertEqual(self.call('GET', '/native-lifecycle/status', b'{}')[0], 400)
        self.assertEqual(self.call('DELETE', '/native-lifecycle/status')[0], 405)
        self.assertEqual(self.call('POST', '/native-lifecycle/stage', b'{}',
                                   headers={'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.call('POST', '/native-lifecycle/stage', bytes(4097))[0], 413)
        self.assertFalse(list((self.root / 'n1' / fixture.BUILD / 'attempts').iterdir()))

    def test_streamed_publication_readback_and_repeated_put_refusal(self):
        self.start()
        manifest, files = self.manifest()
        code, stage = self.call('POST', '/native-lifecycle/stage', manifest)
        self.assertEqual(code, 201, stage)
        self.assertFalse(stage['complete'])
        path = '/native-lifecycle/stage/' + manifest['attempt']
        payload = files[0]
        headers = {'Content-Type': 'application/octet-stream',
                   'X-SHA256': hashlib.sha256(payload).hexdigest()}
        code, observed = self.call('PUT', path + '/files/0', payload, headers=headers)
        self.assertEqual(code, 201, observed)
        self.assertTrue(observed['files'][0]['verified'])
        self.assertEqual(self.call('GET', path)[1], observed)
        self.assertEqual(self.call('PUT', path + '/files/0', payload, headers=headers)[0], 409)
        stored = self.root / 'n1' / fixture.BUILD / 'stages' / manifest['attempt'] / 'package/eboot.bin'
        self.assertEqual(stored.read_bytes(), payload)

    def test_strict_pc_client_matches_actual_c_stage_and_stream_receipts(self):
        self.start()
        endpoint = {'host': '127.0.0.1', 'port': self.port, 'token': fixture.ADMIN}
        client = LifecycleClient(provider=lambda: endpoint)
        status = client.status()
        self.assertEqual(status['resident_build_id'], fixture.BUILD)
        manifest, files = self.manifest()
        observed = client.stage(manifest)
        digest = observed['manifest_sha256']
        observed = client.put_file(manifest['attempt'], 0, files[0], manifest, digest)
        self.assertTrue(observed['files'][0]['verified'])
        self.assertEqual(client.inspect_stage(manifest['attempt'], manifest, digest), observed)

    def test_strict_pc_client_install_launch_and_restart_receipt_contract(self):
        self.start()
        (self.root / 'native-idle-ready').touch()
        endpoint = {'host': '127.0.0.1', 'port': self.port, 'token': fixture.ADMIN}
        client = LifecycleClient(provider=lambda: endpoint)
        manifest, files = self.manifest()
        executable = bytearray(files[0])
        struct.pack_into('<Q', executable, 0x80, 0x2f00000000000001)
        files[0] = bytes(executable)
        keys = ('TITLE_ID', 'APP_VER', 'CATEGORY', 'PSP2_SYSTEM_VER')
        values = (b'VMCP00001\0', b'01.00\0', b'gd\0', struct.pack('<I', 0x03650000))
        key_data = b''
        value_data = b''
        entries = b''
        for index, (key, value) in enumerate(zip(keys, values)):
            entries += struct.pack('<HHIII', len(key_data), 0x404 if index == 3 else 0x204,
                                   len(value), len(value), len(value_data))
            key_data += key.encode() + b'\0'
            value_data += value
        files[1] = (struct.pack('<5I', 0x46535000, 0x101, 84, 84 + len(key_data), 4)
                    + entries + key_data + value_data)
        files[7] = make_head(package_bytes=manifest['package_bytes'])
        manifest['files'] = [{'bytes': len(item), 'sha256': hashlib.sha256(item).hexdigest()}
                             for item in files]
        stage = client.stage(manifest)
        digest = stage['manifest_sha256']
        for index, payload in enumerate(files):
            stage = client.put_file(manifest['attempt'], index, payload, manifest, digest)
        self.assertTrue(stage['complete'])
        receipts = []
        for kind, terminal in [('install', 'installed_verified'), ('launch', 'submitted')]:
            status = client.status()
            intent = {'attempt': uuid.uuid4().hex, 'manifest_sha256': digest,
                      'resident_build_id': fixture.BUILD, 'instance_id': status['instance_id'],
                      'issued_ms': status['clock_ms'], 'ttl_ms': 30000}
            receipt = client.operation(manifest['attempt'], kind, intent)
            deadline = time.monotonic() + 5
            while receipt['state'] != terminal and time.monotonic() < deadline:
                time.sleep(.02)
                receipt = client.inspect_operation(intent['attempt'], intent, manifest['attempt'], kind)
            self.assertEqual(receipt['state'], terminal, receipt)
            self.assertEqual(receipt['dispatch_count'], 1)
            self.assertEqual(receipt['installed_verified'], kind == 'install')
            receipts.append((intent, kind, receipt))
        self.stop()
        self.start()
        self.assertFalse(client.status()['blocked'])
        for intent, kind, receipt in receipts:
            self.assertEqual(client.inspect_operation(intent['attempt'], intent,
                                                     manifest['attempt'], kind), receipt)

    def test_bad_stream_retains_part_and_never_publishes(self):
        self.start()
        manifest, files = self.manifest()
        self.assertEqual(self.call('POST', '/native-lifecycle/stage', manifest)[0], 201)
        path = '/native-lifecycle/stage/' + manifest['attempt'] + '/files/0'
        headers = {'Content-Type': 'application/octet-stream',
                   'X-SHA256': hashlib.sha256(files[0]).hexdigest()}
        damaged = b'!' + files[0][1:]
        self.assertEqual(self.call('PUT', path, damaged, headers=headers)[0], 422)
        self.assertEqual(self.call('PUT', path, files[0], headers=headers)[0], 409)
        directory = self.root / 'n1' / fixture.BUILD / 'stages' / manifest['attempt'] / 'package'
        self.assertFalse((directory / 'eboot.bin').exists())
        self.assertEqual((directory / 'eboot.bin.part').read_bytes(), damaged)

    def test_duplicate_length_rejected_before_native_store_mutation(self):
        self.start()
        with socket.create_connection(('127.0.0.1', self.port), timeout=5) as connection:
            connection.sendall(('POST /native-lifecycle/stage HTTP/1.1\r\n'
                                'Authorization: Bearer ' + fixture.ADMIN + '\r\n'
                                'Content-Type: application/json\r\n'
                                'Content-Length: 2\r\nContent-Length: 2\r\n\r\n{}').encode())
            self.assertIn(b' 400 ', connection.recv(4096))
        directory = self.root / 'n1' / fixture.BUILD / 'stages'
        self.assertFalse(list(directory.iterdir()))


if __name__ == '__main__':
    unittest.main(verbosity=2)
