"""Actual HTTP and stdio MCP with the real C broker and simulated native IO."""
import asyncio
import ctypes
import hashlib
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from resident.launch_client import BrokerClient, prepare_script_session
from workbench.script_session import ForegroundDevice

TOKEN = 'd' * 32
PHONE = 'e' * 32
BUILD = 'f' * 64
PIN = {'app': 'Vita DevLoop', 'protocol': 1, 'version': '01.04', 'title_id': 'CHRS00003',
       'pid': 77, 'run': '9' * 32, 'build_id': BUILD}


class Core:
    def __init__(self, path):
        self.dll = ctypes.CDLL(str(path))
        self.lock = threading.RLock()
        for name in ['lb_host_status', 'lb_host_offer', 'lb_host_get', 'lb_host_dispatch']:
            getattr(self.dll, name).restype = ctypes.c_char_p
        self.dll.lb_host_init.argtypes = [ctypes.c_int]
        self.dll.lb_host_offer.argtypes = [ctypes.c_int] + [ctypes.c_char_p] * 5 + [ctypes.c_uint64, ctypes.c_uint32]
        self.dll.lb_host_get.argtypes = [ctypes.c_int] + [ctypes.c_char_p] * 3
        self.dll.lb_host_dispatch.argtypes = [ctypes.c_char_p, ctypes.c_int]
        self.dll.lb_host_launches.restype = ctypes.c_uint
        assert self.dll.lb_host_init(0) == 0

    def call(self, name, *args):
        with self.lock:
            result = getattr(self.dll, 'lb_host_' + name)(*[a.encode() if isinstance(a, str) else a for a in args])
            return json.loads(result) if isinstance(result, bytes) else result


class BrokerHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiled = tempfile.TemporaryDirectory()
        compiler = shutil.which('cc') or shutil.which('gcc')
        if not compiler:
            raise RuntimeError('A host C compiler is required for the real broker transport fixture')
        cls.library = Path(cls.compiled.name) / ('broker.dll' if os.name == 'nt' else 'broker.so')
        command = [compiler, '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared']
        command += ['-static-libgcc'] if os.name == 'nt' else ['-fPIC']
        subprocess.run(command + [str(ROOT / 'resident/launch_broker/core.c'), str(ROOT / 'tests/launch_broker_host.c'), '-o', str(cls.library)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        # Windows retains a loaded DLL until process exit; TemporaryDirectory's
        # explicit cleanup can fail there. Retain only this OS temp test file.
        if os.name != 'nt': cls.compiled.cleanup()
        else: cls.compiled._finalizer.detach()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.core = Core(self.library)
        self.available = False
        self.frame = 100
        self.mode = ''
        self.posts = []
        self.calls = []
        self.identity = dict(PIN)
        self.paused = True
        self.status_overrides = {}
        self.script_overrides = {}
        owner = self

        class Foreground(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                if not owner.available:
                    self.close_connection = True
                    return
                if self.headers.get('Authorization') != 'Bearer ' + TOKEN:
                    self.send_error(401)
                    return
                owner.frame += 1
                value = {**owner.identity, 'revision': 10, 'frame': owner.frame, 'sampled_ms': owner.frame * 16,
                         'paused': owner.paused, 'loaded': False, 'active': False, 'faulted': False, 'name': '',
                         'sha256': '', 'source_bytes': 0, 'experiment': 'tilt_playground'}
                value.update(owner.script_overrides if self.path == '/script' else owner.status_overrides)
                data = json.dumps(value).encode()
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)

        class Broker(BaseHTTPRequestHandler):
            complete = False
            attempt = None
            def log_message(self, *args): pass
            def role(self):
                token = self.headers.get('Authorization')
                return 1 if token == 'Bearer ' + TOKEN else 2 if token == 'Bearer ' + PHONE else 0
            def reply(self, value, code=200):
                data = json.dumps(value).encode()
                self.send_response(code); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
            def do_GET(self):
                owner.calls.append(('GET', self.path))
                if self.role() != 1: return self.reply({}, 403)
                status = owner.core.call('status')
                if self.path == '/devloop-launch/status':
                    if owner.mode == 'legacy': return self.reply({}, 404)
                    return self.reply(status)
                if self.path.startswith('/devloop-launch/'):
                    receipt = owner.core.call('get', 1, status['resident_build_id'], status['instance_id'], self.path.rsplit('/', 1)[1])
                    return self.reply(receipt, receipt['code'] or 200)
                return self.reply({}, 404)
            def do_POST(self):
                owner.calls.append(('POST', self.path))
                if self.path != '/devloop-launch': return self.reply({}, 404)
                try:
                    length = int(self.headers.get('Content-Length', '-1'))
                    if not 0 < length <= 2048 or self.headers.get('Content-Type') != 'application/json': raise ValueError()
                    value = json.loads(self.rfile.read(length))
                    fields = {'attempt', 'title_id', 'expected_devloop_build', 'resident_build_id', 'instance_id', 'issued_ms', 'ttl_ms'}
                    if not isinstance(value, dict) or set(value) != fields: raise ValueError()
                    for key, size in [('attempt', 32), ('title_id', 9), ('expected_devloop_build', 64), ('resident_build_id', 64), ('instance_id', 32)]:
                        if not isinstance(value[key], str) or len(value[key]) != size: raise ValueError()
                    if type(value['issued_ms']) is not int or not 0 <= value['issued_ms'] < 2**64 or type(value['ttl_ms']) is not int or not 0 < value['ttl_ms'] < 2**32: raise ValueError()
                except (ValueError, TypeError, UnicodeError): return self.reply({}, 400)
                owner.posts.append(value)
                receipt = owner.core.call('offer', self.role(), value['resident_build_id'], value['instance_id'], value['attempt'], value['title_id'], value['expected_devloop_build'], value['issued_ms'], value['ttl_ms'])
                if receipt['code'] == 202:
                    self.attempt = value['attempt']
                    if owner.mode == 'drop_before_reply':
                        self.close_connection = True
                        return
                    if owner.mode == 'bad_receipt': receipt['attempt'] = '0' * 32
                    self.reply(receipt, 202)
                    self.complete = True
                else: self.reply(receipt, receipt['code'])
            def finish(self):
                try: super().finish()
                finally:
                    if self.attempt:
                        try: self.connection.shutdown(socket.SHUT_RDWR)
                        except OSError: pass
                        self.connection.close()
                        receipt = owner.core.call('dispatch', self.attempt, int(self.complete))
                        if receipt.get('state') == 'submitted': owner.available = True

        self.foreground = ThreadingHTTPServer(('127.0.0.1', 0), Foreground)
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), Broker)
        for server in [self.foreground, self.http]: threading.Thread(target=server.serve_forever, daemon=True).start()
        self.config_path = self.root / 'devloop.json'
        self.config_path.write_text(json.dumps({'host': '127.0.0.1', 'port': self.foreground.server_port, 'token': TOKEN}))
        self.env = patch.dict(os.environ, {'VITA_DEVLOOP_CONFIG': str(self.config_path), 'VITA_WORKBENCH_LOCK': str(self.root / 'lock'), 'VITA_WORKBENCH_ROOT': str(self.root)})
        self.env.start()
        self.endpoint = {'host': '127.0.0.1', 'port': self.http.server_port, 'token': TOKEN}
        self.client = BrokerClient(lambda: dict(self.endpoint))

    def tearDown(self):
        self.env.stop()
        for server in [self.foreground, self.http]: server.shutdown(); server.server_close()
        self.temp.cleanup()

    def prepare(self, **kwargs):
        fields = dict(expected_devloop_build=BUILD, allow_launch=True, expected_resident_build='a' * 64,
                      expected_resident_instance='b' * 32, timeout_s=2, device=ForegroundDevice(), broker=self.client, root=self.root)
        fields.update(kwargs)
        value = prepare_script_session(**fields)
        self.assertNotIn(TOKEN, json.dumps(value))
        self.assertNotIn('127.0.0.1', json.dumps(value))
        return value

    def test_already_open_is_script_ready_without_any_broker_request(self):
        self.available = True
        result = self.prepare(allow_launch=False)
        self.assertEqual(result['result'], 'script_ready', result)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.core.call('launches'), 0)

    def test_one_real_c_submission_then_exact_runtime_observation(self):
        result = self.prepare()
        self.assertTrue(result['ready_for_script_reload'], result)
        self.assertEqual(result['runtime_identity'], PIN)
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.core.call('launches'), 1)
        self.assertFalse(result['ready_for_input_trial'])

    def test_future_launch_through_actual_stdio_mcp_and_real_c_core(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        resident = self.root / 'resident.json'
        resident.write_text(json.dumps(self.endpoint), encoding='utf-8')
        async def prove():
            env = {**os.environ, 'VITA_RESIDENT_CONFIG': str(resident), 'VITA_CONTROL_PORT': '0'}
            async with stdio_client(StdioServerParameters(command=sys.executable,
                                    args=[str(ROOT / 'resident/bridge.py')], env=env)) as streams:
                async with ClientSession(*streams) as client:
                    await client.initialize()
                    catalog = await client.list_tools()
                    self.assertEqual(len(catalog.tools), 33)
                    response = await client.call_tool('vita_workbench_prepare_script_session', {
                        'expected_devloop_build': BUILD, 'allow_launch': True,
                        'expected_resident_build': 'a' * 64, 'expected_resident_instance': 'b' * 32,
                        'timeout_s': 2})
                    self.assertFalse(response.isError, response)
                    result = response.structuredContent or json.loads(next(b.text for b in response.content if b.type == 'text'))
                    self.assertEqual(result['result'], 'script_ready', result)
                    self.assertEqual(result['runtime_identity'], PIN)
                    self.assertFalse(result['ready_for_input_trial'])
                    self.assertEqual(result['launch_submissions'], 1)
                    self.assertNotIn(TOKEN, json.dumps(result))
                    self.assertNotIn('127.0.0.1', json.dumps(result))
        asyncio.run(prove())
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.core.call('launches'), 1)
        self.assertTrue(all(path.startswith('/devloop-launch') for _, path in self.calls))

    def test_lost_reply_after_acceptance_is_inspected_without_replay(self):
        offer = self.client.offer
        def lost(value):
            offer(value)
            raise OSError('simulated client reply loss')
        with patch.object(self.client, 'offer', lost): result = self.prepare()
        self.assertTrue(result['ready_for_script_reload'], result)
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.core.call('launches'), 1)

    def test_response_never_completed_does_not_dispatch(self):
        self.mode = 'drop_before_reply'
        result = self.prepare()
        self.assertEqual(result['result'], 'blocked')
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.core.call('launches'), 0)

    def test_invalid_receipt_never_authorizes_runtime_readiness(self):
        self.mode = 'bad_receipt'
        result = self.prepare()
        self.assertEqual(result['result'], 'blocked')
        self.assertEqual(len(self.posts), 1)

    def test_legacy_disabled_wrong_pin_phone_and_wrong_build_fail_closed(self):
        for mode in ['legacy', 'disabled', 'pin', 'phone', 'native_rejected', 'wrong_runtime_build']:
            with self.subTest(mode=mode):
                self.core.call('init', 0); self.available = False; self.posts.clear(); self.calls.clear(); self.mode = ''
                self.endpoint['token'] = TOKEN; self.identity = dict(PIN)
                kwargs = {}
                if mode == 'legacy': self.mode = 'legacy'
                if mode == 'disabled': self.core.call('enabled', 0)
                if mode == 'pin': kwargs['expected_resident_instance'] = '0' * 32
                if mode == 'phone': self.endpoint['token'] = PHONE; self.client = BrokerClient(lambda: dict(self.endpoint))
                else: self.client = BrokerClient(lambda: dict(self.endpoint))
                if mode == 'native_rejected': self.core.call('fault', 3)
                if mode == 'wrong_runtime_build': self.identity['build_id'] = '0' * 64
                result = self.prepare(**kwargs)
                self.assertEqual(result['result'], 'blocked', result)
                self.assertEqual(self.core.call('launches'), int(mode in ('native_rejected', 'wrong_runtime_build')))

    def test_invalid_opt_in_pins_reject_before_network(self):
        with self.assertRaises(ValueError): self.prepare(expected_resident_instance=None)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.posts, [])

    def test_mismatched_foreground_and_broker_hosts_never_authorize_a_post(self):
        other = ThreadingHTTPServer(('127.0.0.2', 0), self.http.RequestHandlerClass)
        threading.Thread(target=other.serve_forever, daemon=True).start()
        self.endpoint.update(host='127.0.0.2', port=other.server_port)
        self.client = BrokerClient(lambda: dict(self.endpoint))
        try:
            result = self.prepare()
        finally:
            other.shutdown()
            other.server_close()
        self.assertEqual(result['result'], 'blocked', result)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.posts, [])
        self.assertEqual(self.core.call('launches'), 0)

    def test_invalid_unloaded_metadata_never_reports_ready_or_reflects_source(self):
        self.available = True
        secret = 'private-source-' + TOKEN
        for overrides in [{'sha256': secret}, {'name': secret}, {'source_bytes': 1},
                          {'sha256': None}, {'name': None}, {'source_bytes': False},
                          {'active': True}]:
            with self.subTest(fields=overrides):
                self.script_overrides = overrides
                result = self.prepare()
                self.assertEqual(result['result'], 'blocked', result)
                self.assertFalse(result['ready_for_script_reload'])
                self.assertNotIn(secret, json.dumps(result))
                self.assertNotIn('source_sha256', result)
                self.assertEqual(self.posts, [])
                self.assertEqual(self.core.call('launches'), 0)

    def test_invalid_loaded_metadata_never_authorizes_launch(self):
        self.available = True
        valid = {'loaded': True, 'name': 'scene_1', 'sha256': 'a' * 64, 'source_bytes': 128}
        for overrides in [{'sha256': 'not-a-hash'}, {'sha256': 'A' * 64}, {'name': ''},
                          {'name': 'bad name'}, {'name': 'n' * 33}, {'source_bytes': 0},
                          {'source_bytes': 16385}, {'source_bytes': True}, {'source_bytes': '128'}]:
            with self.subTest(fields=overrides):
                self.script_overrides = {**valid, **overrides}
                result = self.prepare()
                self.assertEqual(result['result'], 'blocked', result)
                self.assertFalse(result['ready_for_script_reload'])
                self.assertEqual(self.calls, [])
                self.assertEqual(self.posts, [])
                self.assertEqual(self.core.call('launches'), 0)

    def test_native_experiment_and_script_activity_must_agree(self):
        self.available = True
        for experiment, active in [('lua', False), ('tilt_playground', True), ('unknown', False), (None, False)]:
            with self.subTest(experiment=experiment, active=active):
                self.status_overrides = {'experiment': experiment}
                self.script_overrides = {'loaded': True, 'active': active, 'name': 'scene_1',
                                         'sha256': 'a' * 64, 'source_bytes': 128}
                result = self.prepare()
                self.assertEqual(result['result'], 'blocked', result)
                self.assertEqual(self.calls, [])
                self.assertEqual(self.posts, [])
                self.assertEqual(self.core.call('launches'), 0)

    def test_valid_loaded_active_and_inactive_runtime_can_be_observed_without_launch(self):
        self.available = True
        for active in (False, True):
            with self.subTest(active=active):
                self.status_overrides = {'experiment': 'lua' if active else 'tilt_playground'}
                self.script_overrides = {'loaded': True, 'active': active, 'name': 'scene_1',
                                         'sha256': 'a' * 64, 'source_bytes': 128}
                result = self.prepare(allow_launch=False)
                self.assertEqual(result['result'], 'script_ready', result)
                self.assertEqual(result['source_sha256'], 'a' * 64)
                self.assertEqual(self.calls, [])
                self.assertEqual(self.posts, [])
                self.assertEqual(self.core.call('launches'), 0)


if __name__ == '__main__': unittest.main(verbosity=2)
