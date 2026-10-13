"""Read-only host transport checks; these do not qualify Vita sleep or Wi-Fi."""
from __future__ import annotations

import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from resident.keep_awake_transport_client import (
    APP, MAX_REPLY_BYTES, RECORD_PREFIX, STATUS_PATH, U32, U64,
    KeepAwakeTransportClient, TransportLost, TransportRejected, TransportUnsupported,
    register, validate_record, validate_status,
)

TOKEN, BUILD, INSTANCE, SEQUENCE = 'a' * 32, 'b' * 64, 'c' * 32, '0000000000000001'


def common(code=200):
    return {'app': APP, 'protocol': 1, 'resident_build_id': BUILD,
            'instance_id': INSTANCE, 'status': code}


def status():
    return common() | {
        'capacity': 16, 'record_bytes': 184, 'count': 1, 'oldest_seq': SEQUENCE,
        'newest_seq': SEQUENCE, 'overwritten': 0, 'diagnostic_reads': 5,
        'accepted': 7, 'listen_attempts': 1, 'listen_failures': 0,
        'accept_would_block': 20, 'accept_failures': 0, 'listener_generation': 1,
        'listener': {'clock_ms': 1234, 'stage': 6, 'result': -1, 'errno': 11,
                     'close_result': 0, 'close_errno': 0},
        'network': {'result': 0, 'state': 3, 'changes': 1, 'clock_ms': 1200, 'max_gap_ms': 10,
                    'last_loss_result': 0, 'last_loss_state': -1, 'last_loss_ms': 0},
        'sequence_exhausted': False, 'resource_sampling': False,
    }


def record():
    return common() | {
        'seq': SEQUENCE, 'listener_generation': 1, 'accepted_ms': 1100,
        'method': 2, 'operation': 3, 'phase_ms': [1, 2, 3, 4, 5, 6, 7, 8],
        'bytes': [240, 100, 500], 'would_block': [0, 1], 'revision': [4, 5],
        'apply_result': 0, 'http_status': 200, 'outcome': 1, 'io_stage': 10,
        'io_result': 0, 'io_errno': 0, 'accept_result': 12, 'accept_errno': 0,
        'close_result': 0, 'close_errno': 0, 'tick_count': [4, 5], 'max_gap_ms': 10,
        'flags': 12,
    }


class Fixture:
    def __init__(self):
        self.value = None
        self.raw = None
        self.code = 200
        self.content_type = 'application/json'
        self.drip = None
        self.calls = []
        self.hook = None
        # Inspection must not invoke or change any of these lease values.
        self.lease = {'revision': 17, 'active': True, 'renewals': 0, 'deadline': 30000}

    def handler(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                authorized = self.headers.get('Authorization') == 'Bearer ' + TOKEN
                owner.calls.append((self.command, self.path, authorized, self.headers.get('Content-Length')))
                if owner.hook:
                    owner.hook()
                if not authorized:
                    value, code = {'error': 'administrator_required'}, 401
                else:
                    value = owner.value if owner.value is not None else (
                        status() if self.path == STATUS_PATH else record())
                    code = owner.code
                raw = owner.raw if owner.raw is not None else json.dumps(value, separators=(',', ':')).encode()
                try:
                    if owner.drip == 'headers':
                        head = (f'HTTP/1.1 {code} OK\r\nContent-Type: {owner.content_type}\r\n'
                                f'Content-Length: {len(raw)}\r\nConnection: close\r\n\r\n').encode()
                        for byte in head:
                            self.wfile.write(bytes((byte,)))
                            self.wfile.flush()
                            time.sleep(0.015)
                        self.wfile.write(raw)
                        return
                    self.send_response(code)
                    self.send_header('Content-Type', owner.content_type)
                    self.send_header('Content-Length', str(len(raw)))
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    if owner.drip == 'body':
                        for byte in raw:
                            self.wfile.write(bytes((byte,)))
                            self.wfile.flush()
                            time.sleep(0.015)
                    else:
                        self.wfile.write(raw)
                except OSError:
                    pass

            def do_POST(self):
                owner.calls.append(('POST', self.path, False, None))
                owner.lease['renewals'] += 1
                self.send_error(405)

        return Handler


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), self.fixture.handler())
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=0.01), daemon=True)
        self.thread.start()
        self.config = {'host': '127.0.0.1', 'port': 17866, 'token': TOKEN}
        self.client = KeepAwakeTransportClient(lambda: dict(self.config), port=self.server.server_port, timeout=0.5)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)

    def test_status_and_exact_record_are_get_only_and_do_not_change_lease(self):
        before = copy.deepcopy(self.fixture.lease)
        self.assertEqual(self.client.status(), status())
        self.assertEqual(self.client.record(SEQUENCE, BUILD, INSTANCE), record() | {'record_status': 'available'})
        self.assertEqual(self.fixture.lease, before)
        self.assertEqual(self.fixture.calls, [('GET', STATUS_PATH, True, None),
                                             ('GET', RECORD_PREFIX + SEQUENCE, True, None)])

    def test_pinned_status_accepts_power_instance_and_rejects_drift(self):
        self.assertEqual(self.client.status(BUILD, INSTANCE)['instance_id'], INSTANCE)
        for build, instance in [('d' * 64, INSTANCE), (BUILD, 'e' * 32)]:
            with self.subTest(build=build, instance=instance), self.assertRaises(TransportLost):
                self.client.status(build, instance)

    def test_record_pins_and_requested_sequence_are_checked(self):
        for key, value in [('resident_build_id', 'd' * 64), ('instance_id', 'e' * 32),
                           ('seq', '0000000000000002')]:
            self.fixture.value = record() | {key: value}
            with self.subTest(key=key), self.assertRaises(TransportLost):
                self.client.record(SEQUENCE, BUILD, INSTANCE)
        self.assertEqual(len(self.fixture.calls), 3)

    def test_zero_sequence_is_well_formed_but_missing(self):
        zero = '0' * 16
        self.fixture.code = 404
        self.fixture.value = common(404) | {'seq': zero, 'error': 1}
        self.assertEqual(self.client.record(zero, BUILD, INSTANCE)['record_status'], 'not_found')
        self.fixture.value['error'] = 2
        with self.assertRaises(TransportLost):
            self.client.record(zero, BUILD, INSTANCE)
        self.fixture.code, self.fixture.value = 200, record() | {'seq': zero}
        with self.assertRaises(TransportLost):
            self.client.record(zero, BUILD, INSTANCE)

    def test_missing_and_overwritten_are_distinct_pinned_observations(self):
        self.fixture.code = 404
        for error, classification in [(1, 'not_found'), (2, 'overwritten')]:
            self.fixture.value = common(404) | {'seq': SEQUENCE, 'error': error}
            self.assertEqual(self.client.record(SEQUENCE, BUILD, INSTANCE)['record_status'], classification)
        self.assertEqual(len(self.fixture.calls), 2)  # No status probe or lease action.

    def test_old_routes_are_explicitly_unsupported(self):
        self.fixture.code, self.fixture.value = 404, {'error': 'route_not_found'}
        for call in [self.client.status, lambda: self.client.record(SEQUENCE, BUILD, INSTANCE)]:
            with self.assertRaises(TransportUnsupported) as raised:
                call()
            self.assertEqual(raised.exception.classification, 'unsupported')
        self.assertEqual(len(self.fixture.calls), 2)

    def test_unrecognized_404_is_not_a_record_absence(self):
        self.fixture.code = 404
        for value in [{'error': 1}, {'app': 'foreign', 'seq': SEQUENCE, 'error': 2},
                      common(404) | {'seq': SEQUENCE, 'error': 'private remote text'},
                      common(404) | {'seq': SEQUENCE, 'error': True},
                      common(404) | {'seq': SEQUENCE, 'error': 3},
                      common(404) | {'seq': SEQUENCE, 'error': 1, 'extra': 0}]:
            self.fixture.value = value
            with self.subTest(value=value), self.assertRaises(TransportLost):
                self.client.record(SEQUENCE, BUILD, INSTANCE)

    def test_404_status_cannot_be_adopted_as_success(self):
        self.fixture.code = 404
        self.fixture.value = common(404) | {'seq': SEQUENCE, 'error': 1}
        with self.assertRaises(TransportLost):
            self.client.status()

    def test_admin_credential_is_required_and_remote_errors_are_not_reflected(self):
        self.config['token'] = 'f' * 32
        client = KeepAwakeTransportClient(lambda: dict(self.config), port=self.server.server_port)
        with self.assertRaises(TransportRejected) as raised:
            client.status()
        self.assertEqual(raised.exception.status, 401)
        self.assertNotIn('administrator_required', str(raised.exception))
        self.assertNotIn(self.config['token'], str(raised.exception))
        self.assertEqual(self.fixture.calls, [('GET', STATUS_PATH, False, None)])

    def test_remote_failure_text_and_credential_like_fields_are_not_reflected(self):
        secret = 'Bearer ' + TOKEN
        self.fixture.value = {'error': secret}
        self.fixture.code = 503
        with self.assertRaises(TransportRejected) as raised:
            self.client.status()
        self.assertEqual(raised.exception.status, 503)
        self.assertNotIn(secret, str(raised.exception))
        self.fixture.code, self.fixture.value = 200, status() | {'authorization': secret}
        with self.assertRaises(TransportLost) as raised:
            self.client.status()
        self.assertNotIn(secret, str(raised.exception))

    def test_invalid_routes_sequences_and_pins_fail_before_http(self):
        for seq in ['', '1', 'A' * 16, '0' * 17, '../status', '0' * 16 + '?x=1', 1]:
            with self.subTest(seq=seq), self.assertRaises(ValueError):
                self.client.record(seq, BUILD, INSTANCE)
        for build, instance in [(None, INSTANCE), (BUILD, None), ('A' * 64, INSTANCE),
                                (BUILD, '0' * 31), (True, INSTANCE)]:
            with self.subTest(build=build, instance=instance), self.assertRaises(ValueError):
                self.client.status(build, instance)
        for path in ['/keep-awake/status', '/keep-awake/lease', RECORD_PREFIX + SEQUENCE + '/x']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.client._get(path, lambda value, code: value)
        self.assertEqual(self.fixture.calls, [])

    def test_local_configuration_is_strict_and_sanitized(self):
        bad = [self.config | {'host': '8.8.8.8'}, self.config | {'host': '0.0.0.0'},
               self.config | {'host': '224.0.0.1'}, self.config | {'host': 'localhost'},
               self.config | {'host': 2130706433}, self.config | {'port': True},
               self.config | {'port': 65536}, self.config | {'token': TOKEN.upper()},
               {'host': '127.0.0.1', 'port': 17866, 'companion_token': TOKEN},
               self.config | {'companion_token': TOKEN}]
        for config in bad:
            with self.subTest(config=config), self.assertRaises(TransportLost) as raised:
                KeepAwakeTransportClient(lambda: config)
            self.assertNotIn(TOKEN, str(raised.exception))
        def failed_provider():
            raise RuntimeError(TOKEN)
        with self.assertRaises(TransportLost) as raised:
            KeepAwakeTransportClient(failed_provider)
        self.assertNotIn(TOKEN, str(raised.exception))
        self.assertIsNone(raised.exception.__cause__)
        self.assertEqual(self.fixture.calls, [])

    def test_default_local_file_configuration_uses_admin_token(self):
        with tempfile.TemporaryDirectory() as folder:
            config_file = Path(folder) / 'resident.json'
            config_file.write_text(json.dumps(self.config), encoding='utf-8')
            with patch.dict(os.environ, {'VITA_RESIDENT_CONFIG': str(config_file)}):
                client = KeepAwakeTransportClient(port=self.server.server_port, timeout=0.5)
                self.assertEqual(client.status()['resident_build_id'], BUILD)
                config_file.write_text(json.dumps({'host': '127.0.0.1', 'port': 17866,
                                                  'companion_token': TOKEN}), encoding='utf-8')
                with self.assertRaises(TransportLost):
                    KeepAwakeTransportClient(port=self.server.server_port)
        self.assertEqual(len(self.fixture.calls), 1)

    def test_configuration_drift_is_checked_before_and_after_get(self):
        self.config['port'] += 1
        with self.assertRaises(TransportLost):
            self.client.status()
        self.assertEqual(self.fixture.calls, [])
        self.config['port'] -= 1
        self.fixture.hook = lambda: self.config.update(token='f' * 32)
        with self.assertRaises(TransportLost):
            self.client.status()
        self.assertEqual(len(self.fixture.calls), 1)

    def test_http_foreign_and_malformed_numeric_identity_replies_fail_closed(self):
        for key, value in [('app', 'foreign'), ('protocol', True), ('status', True),
                           ('resident_build_id', 'B' * 64), ('instance_id', 3),
                           ('accepted', True), ('overwritten', -1), ('count', 1.0),
                           ('record_bytes', '184'), ('resource_sampling', 0)]:
            self.fixture.value = status() | {key: value}
            with self.subTest(key=key), self.assertRaises(TransportLost):
                self.client.status()
        self.assertEqual(len(self.fixture.calls), 10)

    def test_bounds_content_type_and_malformed_json(self):
        for raw, content_type in [(b' ' * (MAX_REPLY_BYTES + 1), 'application/json'),
                                  (json.dumps(status()).encode(), 'text/plain'),
                                  (b'not-json Bearer ' + TOKEN.encode(), 'application/json'),
                                  (b'{"protocol":1,"protocol":1}', 'application/json'),
                                  (b'{"value":NaN}', 'application/json'),
                                  (b'[]', 'application/json'), (b'\xff', 'application/json')]:
            self.fixture.raw, self.fixture.content_type = raw, content_type
            with self.subTest(content_type=content_type, size=len(raw)), self.assertRaises(TransportLost) as raised:
                self.client.status()
            self.assertNotIn(TOKEN, str(raised.exception))

    def test_exact_body_bound_and_json_charset_are_accepted(self):
        raw = json.dumps(status(), separators=(',', ':')).encode()
        self.fixture.raw = raw + b' ' * (MAX_REPLY_BYTES - len(raw))
        self.fixture.content_type = 'application/json; charset=utf-8'
        self.assertEqual(self.client.status(), status())

    def test_absolute_deadline_interrupts_drip_fed_headers_and_body(self):
        client = KeepAwakeTransportClient(lambda: dict(self.config), port=self.server.server_port, timeout=0.1)
        for mode in ['headers', 'body']:
            self.fixture.drip = mode
            started = time.monotonic()
            with self.subTest(mode=mode), self.assertRaises(TimeoutError):
                client.status()
            self.assertLess(time.monotonic() - started, 0.6)
        self.assertEqual(len(self.fixture.calls), 2)
        self.assertEqual(self.fixture.lease['renewals'], 0)

    def test_schema_validation_is_inside_absolute_deadline(self):
        client = KeepAwakeTransportClient(lambda: dict(self.config), port=self.server.server_port, timeout=0.08)
        original = validate_status
        def delayed(*args, **kwargs):
            time.sleep(0.12)
            return original(*args, **kwargs)
        with patch('resident.keep_awake_transport_client.validate_status', delayed), self.assertRaises(TimeoutError):
            client.status()
        self.assertEqual(len(self.fixture.calls), 1)

    def test_listener_port_and_deadline_configuration_are_bounded(self):
        for timeout in [0, -1, 5.01, float('nan'), True, '5']:
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                KeepAwakeTransportClient(lambda: self.config, timeout=timeout)
        for port in [0, 65536, True, '17869']:
            with self.subTest(port=port), self.assertRaises(ValueError):
                KeepAwakeTransportClient(lambda: self.config, port=port)
        self.assertEqual(KeepAwakeTransportClient(lambda: self.config).timeout, 5)
        self.assertEqual(self.fixture.calls, [])


class SchemaTests(unittest.TestCase):
    def test_status_exact_shape_and_numeric_ranges(self):
        for key, invalid in [('capacity', [15, 17, True]), ('record_bytes', [0, 193, True]),
                             ('count', [-1, 17, False]), ('listener_generation', [-1, U32 + 1, True]),
                             ('accepted', [-1, U64 + 1, 1.0]), ('sequence_exhausted', [0, 1, None]),
                             ('oldest_seq', ['1', 'A' * 16, 1]), ('resource_sampling', [True, 0, None])]:
            for value in invalid:
                with self.subTest(key=key, value=value), self.assertRaises(TransportLost):
                    validate_status(status() | {key: value})
        for change in [('extra', 0), ('error', None)]:
            with self.assertRaises(TransportLost):
                validate_status(status() | {change[0]: change[1]})
        missing = status()
        missing.pop('accepted')
        with self.assertRaises(TransportLost):
            validate_status(missing)

    def test_nested_status_shape_signed_counters_and_stages(self):
        for group, key, values in [('listener', 'stage', [11, -1, True]),
                                   ('listener', 'clock_ms', [-1, U64 + 1]),
                                   ('listener', 'errno', [-0x80000001, 0x80000000, True]),
                                   ('network', 'state', [1.0, 0x80000000]),
                                   ('network', 'last_loss_result', [True, -0x80000001]),
                                   ('network', 'last_loss_state', [0x80000000]),
                                   ('network', 'last_loss_ms', [-1, U64 + 1]),
                                   ('network', 'changes', [-1, U64 + 1]),
                                   ('network', 'max_gap_ms', [-1, U32 + 1])]:
            for value in values:
                candidate = status()
                candidate[group][key] = value
                with self.subTest(group=group, key=key, value=value), self.assertRaises(TransportLost):
                    validate_status(candidate)
        for group in ['listener', 'network']:
            candidate = status()
            candidate[group]['raw'] = TOKEN
            with self.assertRaises(TransportLost):
                validate_status(candidate)
        candidate = status()
        candidate['listener']['result'] = -0x80000000
        candidate['listener']['errno'] = 0x7fffffff
        candidate['network']['changes'] = U64
        self.assertEqual(validate_status(candidate), candidate)

    def test_ring_empty_bounds_wrap_and_saturating_counters(self):
        empty = status() | {'count': 0, 'oldest_seq': '0' * 16, 'newest_seq': '0' * 16}
        self.assertEqual(validate_status(empty), empty)
        maximum = status() | {'count': 16, 'oldest_seq': f'{U64 - 15:016x}',
                              'newest_seq': f'{U64:016x}', 'sequence_exhausted': True,
                              'accepted': U64, 'overwritten': U64, 'diagnostic_reads': U64}
        self.assertEqual(validate_status(maximum), maximum)
        # Accepted connections include diagnostic GETs; no sequence equality is required.
        self.assertEqual(validate_status(status() | {'accepted': 500})['accepted'], 500)
        for value in [empty | {'oldest_seq': SEQUENCE}, status() | {'count': 0},
                      status() | {'count': 2}, status() | {'oldest_seq': '0' * 16},
                      status() | {'oldest_seq': '0000000000000002'},
                      status() | {'sequence_exhausted': True}]:
            with self.subTest(value=value), self.assertRaises(TransportLost):
                validate_status(value)

    def test_record_exact_shape_and_enum_ranges(self):
        for key, invalid in [('listener_generation', [-1, U32 + 1, True]),
                             ('accepted_ms', [-1, U64 + 1]), ('method', [-1, 3, True]),
                             ('operation', [-1, 5, 1.0]), ('outcome', [-1, 11]),
                             ('io_stage', [-1, 11]), ('max_gap_ms', [-1, U32 + 1]),
                             ('flags', [-1, 32]), ('http_status', [-1, 1, 99, 600, True]),
                             ('apply_result', [-0x80000001, 0x80000000, False])]:
            for value in invalid:
                with self.subTest(key=key, value=value), self.assertRaises(TransportLost):
                    validate_record(record() | {key: value}, 200, SEQUENCE, BUILD, INSTANCE)
        for code in [0, 100, 599]:
            self.assertEqual(validate_record(record() | {'http_status': code}, 200, SEQUENCE,
                                             BUILD, INSTANCE)['http_status'], code)
        missing = record()
        missing.pop('close_errno')
        for value in [missing, record() | {'raw': TOKEN}, record() | {'error': None}]:
            with self.assertRaises(TransportLost):
                validate_record(value, 200, SEQUENCE, BUILD, INSTANCE)

    def test_record_vectors_and_missing_phase_sentinel(self):
        for key, count, maximum in [('phase_ms', 8, U32), ('bytes', 3, U32),
                                     ('would_block', 2, U32), ('revision', 2, U32),
                                     ('tick_count', 2, U64)]:
            for value in [[0] * (count - 1), [0] * (count + 1), [True] * count,
                          [-1] * count, [maximum + 1] * count, '0' * count]:
                with self.subTest(key=key, value=value), self.assertRaises(TransportLost):
                    validate_record(record() | {key: value}, 200, SEQUENCE, BUILD, INSTANCE)
            self.assertEqual(validate_record(record() | {key: [maximum] * count}, 200, SEQUENCE,
                                             BUILD, INSTANCE)[key], [maximum] * count)
        # A regressed clock or saturated offset must remain inspectable.
        candidate = record() | {'phase_ms': [U32, 5, 4, 3, 2, 1, 0, U32], 'flags': 3,
                                'tick_count': [U64, U64]}
        self.assertEqual(validate_record(candidate, 200, SEQUENCE, BUILD, INSTANCE)['flags'], 3)

    def test_registration_has_only_two_read_only_tools(self):
        class MCP:
            def __init__(self):
                self.tools = {}
            def tool(self, **kwargs):
                def decorate(function):
                    self.tools[function.__name__] = (function, kwargs)
                    return function
                return decorate
        mcp, annotations = MCP(), object()
        register(mcp, lambda: {'host': '127.0.0.1', 'port': 17866, 'token': TOKEN}, annotations)
        self.assertEqual(set(mcp.tools), {'vita_resident_keep_awake_transport_status',
                                         'vita_resident_keep_awake_transport_record'})
        for function, kwargs in mcp.tools.values():
            self.assertIs(kwargs['annotations'], annotations)
            self.assertIn('GET', function.__doc__)


if __name__ == '__main__':
    unittest.main()
