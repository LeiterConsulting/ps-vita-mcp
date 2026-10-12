"""Real Resident C HTTP with POSIX storage; no Vita or physical acceptance."""
import hashlib
import http.client
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest
import uuid


ADMIN = '1' * 32  # Host fixture only.
MAX_FILE = 8 * 1024 * 1024
CHUNK = 16384
LEAVES = ('package.vpk', 'probe.bin', 'package.vpk.part', 'probe.bin.part')


class FilesServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.inbox = self.root / 'inbox'
        self.inbox.mkdir()
        self.log_path = self.root / 'host.log'
        self.log = self.log_path.open('wb')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.process = subprocess.Popen(
            ['build/resident/host-server', str(self.root), str(self.port), ADMIN],
            stdout=self.log, stderr=self.log)
        self.addCleanup(self.cleanup)
        for _ in range(100):
            try:
                if self.call('GET', '/status')[0] == 200:
                    break
            except OSError:
                pass
            if self.process.poll() is not None:
                raise RuntimeError('Resident host fixture exited before readiness')
            time.sleep(.02)
        else:
            raise RuntimeError('Resident host fixture readiness deadline')

    def cleanup(self):
        if self.process.poll() is None:
            self.process.terminate()
        result = self.process.wait(timeout=10)
        self.log.close()
        text = self.log_path.read_text(encoding='utf-8')
        self.temp.cleanup()
        self.assertEqual(result, 0, text)
        self.assertNotIn('AddressSanitizer', text)
        self.assertNotIn('runtime error:', text)

    def call(self, method, path, body=None, token=ADMIN, headers=None, timeout=10):
        h = dict(headers or {})
        if token is not None:
            h['Authorization'] = 'Bearer ' + token
        if isinstance(body, dict):
            body = json.dumps(body).encode('utf-8')
            h['Content-Type'] = 'application/json'
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=timeout)
        try:
            connection.request(method, path, body, h)
            response = connection.getresponse()
            payload = response.read()
            self.assertEqual(response.getheader('Connection'), 'close')
            self.assertEqual(response.getheader('Cache-Control'), 'no-store')
            if method != 'HEAD':
                self.assertEqual(int(response.getheader('Content-Length')), len(payload))
            return response.status, payload, response.getheader('Content-Type')
        finally:
            connection.close()

    def json_call(self, path, operation, **kwargs):
        status, payload, mime = self.call('GET', path, **kwargs)
        self.assertEqual(status, 200, payload)
        self.assertEqual(mime, 'application/json')
        value = json.loads(payload)
        self.assertEqual(value['app'], 'Vita Resident')
        self.assertEqual(value['protocol'], 1)
        self.assertEqual(value['storage_protocol'], 1)
        self.assertEqual(value['operation'], operation)
        self.assertIs(value['snapshot'], False)
        return value

    def attempt(self, name=None):
        name = name or uuid.uuid4().hex
        directory = self.inbox / name
        directory.mkdir()
        return name, directory

    def snapshot(self):
        """Inspect inbox contents only, outside mutable service logs/pairing."""
        return {str(p.relative_to(self.inbox)): p.read_bytes()
                for p in self.inbox.rglob('*') if p.is_file() and not p.is_symlink()}

    def assert_healthy(self):
        status, payload, _ = self.call('GET', '/status')
        self.assertEqual(status, 200, payload)
        value = json.loads(payload)
        self.assertFalse(value['keep_awake'])
        status, payload, _ = self.call('GET', '/devloop-launch/status')
        self.assertEqual(status, 200, payload)
        broker = json.loads(payload)
        self.assertFalse(broker['enabled'])
        self.assertFalse(broker['configured_enabled'])
        self.assertFalse((self.root / 'fixture-launch-called').exists())

    def phone(self):
        """Obtain a real C-issued credential; local approval is simulated."""
        control = 'c' * 64
        self.assertEqual(self.call('POST', '/pairing/native/register',
                         {'protocol': 1, 'control_build_id': control})[0], 200)
        self.assertEqual(self.call('POST', '/pairing/ui/open',
                         {'protocol': 1, 'control_build_id': control})[0], 200)
        client, nonce = uuid.uuid4().hex, uuid.uuid4().hex
        status, data, _ = self.call('POST', '/pairing/request',
            {'protocol': 1, 'client_id': client, 'client_nonce': nonce,
             'client_name': 'Storage inspection host fixture'}, token=None)
        self.assertEqual(status, 201, data)
        request_id = json.loads(data)['request_id']
        binding = {'protocol': 1, 'request_id': request_id,
                   'client_id': client, 'client_nonce': nonce}
        code = '000007'
        digest = hashlib.sha256(
            ('VitaPairing1' + request_id + client + nonce + code).encode()).hexdigest()
        self.assertEqual(self.call('POST', '/pairing/ui/approve',
                         {**binding, 'code_sha256': digest})[0], 200)
        status, data, _ = self.call('POST', '/pairing/confirm',
                                   {**binding, 'code': code}, token=None)
        self.assertEqual(status, 200, data)
        return json.loads(data)['token']

    def test_empty_root_and_empty_attempt_have_explicit_end(self):
        root = self.json_call('/storage/list?offset=0', 'list')
        self.assertIsNone(root['attempt'])
        self.assertEqual(root['entries'], [])
        self.assertEqual(root['offset'], 0)
        self.assertIsNone(root['next_offset'])
        self.assertIs(root['has_more'], False)
        self.assertIs(root['limit_reached'], False)
        attempt, _ = self.attempt()
        value = self.json_call(f'/storage/list/{attempt}?offset=0', 'list')
        self.assertEqual(value['attempt'], attempt)
        self.assertEqual(value['entries'], [])
        self.assertIsNone(value['next_offset'])
        self.assertIs(value['has_more'], False)
        self.assert_healthy()

    def test_root_list_filters_names_and_kinds_without_exposing_private_root(self):
        accepted = {self.attempt()[0] for _ in range(3)}
        for name in ('private', 'launch-v1', '../not-used', 'A' * 32,
                     'a' * 31, 'b' * 33, 'c' * 32 + '.part', 'contains space'):
            if '/' not in name:
                (self.inbox / name).mkdir()
        (self.inbox / ('d' * 32)).write_bytes(b'not a directory')
        (self.root / 'private' / 'fixture-secret').parent.mkdir(exist_ok=True)
        (self.root / 'private' / 'fixture-secret').write_bytes(b'outside inbox')
        value = self.json_call('/storage/list?offset=0', 'list')
        self.assertEqual({entry['name'] for entry in value['entries']}, accepted)
        for entry in value['entries']:
            self.assertEqual(entry['kind'], 'directory')
            self.assertNotIn('bytes', entry)
        self.assert_healthy()

    def test_root_paging_consumes_raw_entries_and_has_no_false_completion(self):
        accepted = {self.attempt(f'{n:032x}')[0] for n in range(1, 76)}
        for n in range(40):
            (self.inbox / f'unsupported-{n:03}').mkdir()
        offset, seen, pages = 0, set(), 0
        while True:
            value = self.json_call(f'/storage/list?offset={offset}', 'list')
            self.assertEqual(value['offset'], offset)
            self.assertLessEqual(len(value['entries']), 32)
            names = {entry['name'] for entry in value['entries']}
            self.assertFalse(seen & names)
            seen |= names
            pages += 1
            self.assertLess(pages, 8)
            if not value['has_more']:
                self.assertIsNone(value['next_offset'])
                break
            self.assertIs(value['limit_reached'], False)
            self.assertEqual(value['next_offset'], offset + 32)
            offset = value['next_offset']
        self.assertGreater(pages, 1)
        self.assertEqual(seen, accepted)
        self.assert_healthy()

    def test_scan_limit_is_explicit_including_unsupported_entries(self):
        for n in range(1035):
            (self.inbox / f'unsupported-{n:04}').mkdir()
        value = self.json_call('/storage/list?offset=1000', 'list')
        self.assertEqual(value['entries'], [])
        self.assertIs(value['limit_reached'], True)
        self.assertIsNone(value['next_offset'])
        self.assert_healthy()

    def test_attempt_list_returns_four_allowed_leaves_and_retains_parts(self):
        attempt, directory = self.attempt()
        contents = {leaf: bytes([n]) * (n + 1) for n, leaf in enumerate(LEAVES)}
        for leaf, payload in contents.items():
            (directory / leaf).write_bytes(payload)
        for leaf in ('bridge.cfg', 'pairing-0.bin', 'unexpected.log',
                     'package.vpk.part.extra', 'probe.bin.tmp'):
            (directory / leaf).write_bytes(b'unsupported')
        (directory / 'another-directory').mkdir()
        before = self.snapshot()
        value = self.json_call(f'/storage/list/{attempt}?offset=0', 'list')
        self.assertEqual({entry['name'] for entry in value['entries']}, set(LEAVES))
        for entry in value['entries']:
            self.assertEqual(entry['kind'], 'file')
            self.assertEqual(entry['bytes'], len(contents[entry['name']]))
        self.assertEqual(self.snapshot(), before)
        self.assert_healthy()

    def test_stat_all_leaves_hashes_empty_binary_and_maximum_files(self):
        attempt, directory = self.attempt()
        contents = {'package.vpk': bytes(range(256)) * (MAX_FILE // 256),
                    'probe.bin': bytes(range(256)) * 256,
                    'package.vpk.part': b'', 'probe.bin.part': b'partial\x00\xff'}
        for leaf, payload in contents.items():
            (directory / leaf).write_bytes(payload)
        before = self.snapshot()
        for leaf, payload in contents.items():
            with self.subTest(leaf=leaf, size=len(payload)):
                value = self.json_call(f'/storage/stat/{attempt}/{leaf}', 'stat')
                self.assertEqual(value['attempt'], attempt)
                self.assertEqual(value['file'], leaf)
                self.assertEqual(value['bytes'], len(payload))
                self.assertEqual(value['sha256'], hashlib.sha256(payload).hexdigest())
        self.assertEqual(self.snapshot(), before)
        self.assert_healthy()

    def test_oversized_files_are_not_hashed_or_read(self):
        attempt, directory = self.attempt()
        for leaf in LEAVES:
            with (directory / leaf).open('wb') as stream:
                stream.truncate(MAX_FILE + 1)
            for path in (f'/storage/stat/{attempt}/{leaf}',
                         f'/storage/read/{attempt}/{leaf}?offset=0&length=1'):
                with self.subTest(path=path):
                    self.assertIn(self.call('GET', path)[0], (413, 404))
        self.assert_healthy()

    def test_chunk_reads_are_exact_binary_bounded_and_nonmutating(self):
        attempt, directory = self.attempt()
        payload = bytes(range(256)) * 161
        (directory / 'package.vpk.part').write_bytes(payload)
        before = self.snapshot()
        for offset, length in ((0, 1), (0, CHUNK), (3, CHUNK),
                               (CHUNK - 1, 3), (len(payload) - 2, CHUNK),
                               (len(payload), 1), (len(payload), CHUNK)):
            with self.subTest(offset=offset, length=length):
                status, data, mime = self.call('GET',
                    f'/storage/read/{attempt}/package.vpk.part?offset={offset}&length={length}')
                self.assertEqual(status, 200, data)
                self.assertEqual(mime, 'application/octet-stream')
                self.assertEqual(data, payload[offset:offset + length])
        self.assertEqual(self.call('GET',
            f'/storage/read/{attempt}/package.vpk.part?offset={len(payload) + 1}&length=1')[0], 416)
        self.assertEqual(self.snapshot(), before)
        self.assert_healthy()

    def test_empty_file_returns_empty_chunk_without_publishing_part(self):
        attempt, directory = self.attempt()
        part = directory / 'probe.bin.part'
        part.write_bytes(b'')
        status, payload, mime = self.call('GET',
            f'/storage/read/{attempt}/probe.bin.part?offset=0&length=1')
        self.assertEqual((status, payload, mime), (200, b'', 'application/octet-stream'))
        self.assertTrue(part.exists())
        self.assertFalse((directory / 'probe.bin').exists())
        self.assertEqual(self.call('GET', f'/files/{attempt}/probe.bin.part')[0], 404)
        self.assert_healthy()

    def test_short_disk_reads_complete_hash_and_chunk_without_file_changes(self):
        attempt, directory = self.attempt()
        payload = bytes(range(256)) * 65
        (directory / 'package.vpk.part').write_bytes(payload)
        before = self.snapshot()
        (self.root / 'fault-partial-read').touch()
        value = self.json_call(f'/storage/stat/{attempt}/package.vpk.part', 'stat')
        self.assertEqual(value['sha256'], hashlib.sha256(payload).hexdigest())
        (self.root / 'fault-partial-read').touch()
        status, data, mime = self.call('GET',
            f'/storage/read/{attempt}/package.vpk.part?offset=3&length={CHUNK}')
        self.assertEqual((status, mime), (200, 'application/octet-stream'))
        self.assertEqual(data, payload[3:3 + CHUNK])
        self.assertFalse((self.root / 'fault-partial-read').exists())
        self.assertEqual(self.snapshot(), before)
        self.assert_healthy()

    def test_file_faults_fail_before_success_headers_and_retain_contents(self):
        attempt, directory = self.attempt()
        (directory / 'probe.bin.part').write_bytes(b'retained partial contents')
        before = self.snapshot()
        for operation in ('stat', 'read'):
            path = f'/storage/{operation}/{attempt}/probe.bin.part'
            if operation == 'read':
                path += '?offset=0&length=16'
            for fault in ('files-open', 'files-stat', 'files-close',
                          'read', 'zero-read', 'files-size-change'):
                with self.subTest(operation=operation, fault=fault):
                    marker = self.root / ('fault-' + fault)
                    marker.touch()
                    status, data, mime = self.call('GET', path)
                    self.assertEqual(status, 500, data)
                    self.assertEqual(mime, 'application/json')
                    self.assertIn('error', json.loads(data))
                    self.assertFalse(marker.exists())
                    self.assertEqual(self.snapshot(), before)
                    self.assert_healthy()
        (self.root / 'fault-files-seek').touch()
        status, data, _ = self.call('GET',
            f'/storage/read/{attempt}/probe.bin.part?offset=1&length=1')
        self.assertEqual(status, 500, data)
        self.assertFalse((self.root / 'fault-files-seek').exists())
        self.assertEqual(self.snapshot(), before)
        self.assert_healthy()

    def test_directory_faults_do_not_report_successful_empty_listing(self):
        attempt, directory = self.attempt()
        (directory / 'probe.bin.part').write_bytes(b'retained')
        before = self.snapshot()
        for path in ('/storage/list?offset=0', f'/storage/list/{attempt}?offset=0'):
            for fault in ('files-directory', 'files-dir-read', 'files-dir-close'):
                with self.subTest(path=path, fault=fault):
                    marker = self.root / ('fault-' + fault)
                    marker.touch()
                    status, data, mime = self.call('GET', path)
                    self.assertEqual(status, 500, data)
                    self.assertEqual(mime, 'application/json')
                    self.assertIn('error', json.loads(data))
                    self.assertFalse(marker.exists())
                    self.assertEqual(self.snapshot(), before)
                    self.assert_healthy()

    def test_open_deadline_returns_timeout_then_status_recovers(self):
        attempt, directory = self.attempt()
        (directory / 'probe.bin.part').write_bytes(b'retained')
        before = self.snapshot()
        marker = self.root / 'fault-files-deadline'
        marker.touch()
        started = time.monotonic()
        status, data, mime = self.call('GET',
            f'/storage/stat/{attempt}/probe.bin.part', timeout=20)
        elapsed = time.monotonic() - started
        self.assertEqual(status, 408, data)
        self.assertEqual(mime, 'application/json')
        self.assertGreaterEqual(elapsed, 10)
        self.assertLess(elapsed, 18)
        self.assertFalse(marker.exists())
        self.assertEqual(self.snapshot(), before)
        self.assert_healthy()

    def test_strict_queries_reject_duplicates_signs_overflow_and_unknown_fields(self):
        attempt, directory = self.attempt()
        (directory / 'probe.bin').write_bytes(b'abc')
        paths = ['/storage/list?offset=-1', '/storage/list?offset=+1',
                 '/storage/list?offset=1001', '/storage/list?offset=4294967296',
                 '/storage/list?offset=0&offset=0', '/storage/list?offset=0&extra=1',
                 '/storage/list?offset=%30', '/storage/list?offset=',
                 f'/storage/stat/{attempt}/probe.bin?offset=0']
        base = f'/storage/read/{attempt}/probe.bin?'
        paths += [base + query for query in (
            'offset=0', 'length=1', 'offset=0&length=0',
            f'offset=0&length={CHUNK + 1}', 'offset=-1&length=1',
            'offset=0&length=-1', 'offset=0&length=+1',
            'offset=18446744073709551616&length=1',
            'offset=0&length=1&length=1', 'offset=0&length=1&extra=1',
            'offset=0&length=%31', 'offset=0&length=1&')]
        for path in paths:
            with self.subTest(path=path):
                self.assertIn(self.call('GET', path)[0], (400, 413, 416))
        self.assert_healthy()

    def test_path_validation_rejects_encoded_traversal_separators_and_private_files(self):
        attempt, directory = self.attempt()
        (directory / 'probe.bin').write_bytes(b'abc')
        before = self.snapshot()
        paths = ['/storage/list/../private?offset=0',
                 '/storage/list/%2e%2e?offset=0',
                 '/storage/list/' + 'A' * 32 + '?offset=0',
                 '/storage/stat/../../private/pairing-0.bin',
                 f'/storage/stat/{attempt}/../bridge.cfg',
                 f'/storage/stat/{attempt}/%2e%2e%2fbridge.cfg',
                 f'/storage/stat/{attempt}/probe.bin%00',
                 f'/storage/stat/{attempt}/probe.bin/extra',
                 f'/storage/stat/{attempt}/probe.bin\\extra',
                 f'/storage/stat/{attempt}/bridge.cfg',
                 f'/storage/read/{attempt}/private?offset=0&length=1',
                 f'/storage/read/{attempt}/probe.bin%2fpart?offset=0&length=1']
        for path in paths:
            with self.subTest(path=path):
                self.assertIn(self.call('GET', path)[0], (400, 404))
        self.assertEqual(self.snapshot(), before)
        self.assert_healthy()

    def test_missing_attempt_and_file_are_unavailable_without_creation(self):
        attempt = uuid.uuid4().hex
        for path in (f'/storage/list/{attempt}?offset=0',
                     f'/storage/stat/{attempt}/probe.bin',
                     f'/storage/read/{attempt}/probe.bin?offset=0&length=1'):
            self.assertEqual(self.call('GET', path)[0], 404)
        self.assertFalse((self.inbox / attempt).exists())
        self.assert_healthy()

    def test_namespace_is_admin_only_and_methods_do_not_write(self):
        attempt, directory = self.attempt()
        (directory / 'probe.bin.part').write_bytes(b'retained')
        before = self.snapshot()
        routes = ('/storage/list?offset=0', f'/storage/list/{attempt}?offset=0',
                  f'/storage/stat/{attempt}/probe.bin.part',
                  f'/storage/read/{attempt}/probe.bin.part?offset=0&length=1')
        for route in routes:
            for token in (None, '2' * 32, 'broken'):
                self.assertEqual(self.call('GET', route, token=token)[0], 403)
            for method in ('POST', 'PUT', 'DELETE', 'HEAD'):
                self.assertIn(self.call(method, route)[0], (400, 405))
            self.assertEqual(self.call('GET', route, b'x')[0], 400)
        self.assertEqual(self.snapshot(), before)
        self.assert_healthy()

    def test_real_phone_credential_has_status_but_no_storage_authority(self):
        attempt, directory = self.attempt()
        (directory / 'probe.bin').write_bytes(b'fixture')
        token = self.phone()
        self.assertNotEqual(token, ADMIN)
        self.assertEqual(self.call('GET', '/status', token=token)[0], 200)
        before = self.snapshot()
        for path in ('/storage/list?offset=0', f'/storage/list/{attempt}?offset=0',
                     f'/storage/stat/{attempt}/probe.bin',
                     f'/storage/read/{attempt}/probe.bin?offset=0&length=1'):
            self.assertEqual(self.call('GET', path, token=token)[0], 403)
        self.assertEqual(self.snapshot(), before)
        self.assert_healthy()

    def test_leaf_symlink_does_not_expose_outside_content(self):
        attempt, directory = self.attempt()
        outside = self.root / 'outside-secret'
        outside.write_bytes(b'secret outside managed inbox')
        (directory / 'probe.bin').symlink_to(outside)
        for path in (f'/storage/stat/{attempt}/probe.bin',
                     f'/storage/read/{attempt}/probe.bin?offset=0&length={CHUNK}'):
            status, payload, _ = self.call('GET', path)
            self.assertNotEqual(status, 200)
            self.assertNotIn(outside.read_bytes(), payload)
        value = self.json_call(f'/storage/list/{attempt}?offset=0', 'list')
        self.assertNotIn('probe.bin', {entry['name'] for entry in value['entries']})
        self.assertEqual(outside.read_bytes(), b'secret outside managed inbox')
        self.assert_healthy()

    def test_attempt_symlink_does_not_expose_outside_directory(self):
        attempt = uuid.uuid4().hex
        outside = self.root / 'outside-attempt'
        outside.mkdir()
        (outside / 'probe.bin').write_bytes(b'outside attempt')
        (self.inbox / attempt).symlink_to(outside, target_is_directory=True)
        for path in (f'/storage/list/{attempt}?offset=0',
                     f'/storage/stat/{attempt}/probe.bin',
                     f'/storage/read/{attempt}/probe.bin?offset=0&length=16'):
            status, payload, _ = self.call('GET', path)
            self.assertNotEqual(status, 200)
            self.assertNotIn(b'outside attempt', payload)
        value = self.json_call('/storage/list?offset=0', 'list')
        self.assertNotIn(attempt, {entry['name'] for entry in value['entries']})
        self.assert_healthy()

    def test_inbox_symlink_does_not_change_inspection_root(self):
        attempt = uuid.uuid4().hex
        outside = self.root / 'outside-inbox'
        (outside / attempt).mkdir(parents=True)
        (outside / attempt / 'probe.bin').write_bytes(b'outside root')
        self.inbox.rmdir()
        self.inbox.symlink_to(outside, target_is_directory=True)
        for path in ('/storage/list?offset=0', f'/storage/list/{attempt}?offset=0',
                     f'/storage/stat/{attempt}/probe.bin',
                     f'/storage/read/{attempt}/probe.bin?offset=0&length=16'):
            status, payload, _ = self.call('GET', path)
            self.assertNotEqual(status, 200)
            self.assertNotIn(b'outside root', payload)
        self.assert_healthy()


if __name__ == '__main__':
    unittest.main(verbosity=2)
