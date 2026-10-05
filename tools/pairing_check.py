"""Loopback-only PC pairing qualification. Explicit operator actions; no secret logging."""
from pathlib import Path
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, HTTPServer
import datetime
import html
import http.client
import json
import os
import re
import secrets
import sys
import time
import urllib.parse
import uuid

ROOT = Path(__file__).resolve().parents[1]
# Only synthetic identifiers are used by --self-test. Live operation requires
# exact operator-supplied native build pins from the matching build reports.
RESIDENT = 'a' * 64
CONTROL = 'b' * 64
HEX = re.compile(r'[0-9a-f]{32}\Z')

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def write_json(path, value, exclusive=False):
    with path.open('x' if exclusive else 'w', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, indent=2)
        f.write('\n')

class State:
    def __init__(self, config, evidence, private, lock, wire=None):
        self.config, self.evidence, self.private, self.lock = config, evidence, private, lock
        self.wire = wire or self.http
        self.cap, self.csrf = uuid.uuid4().hex, secrets.token_hex(32)
        self.phase, self.message = 'ready', 'Ready for one fresh pairing request.'
        self.binding = {'protocol': 1, 'client_id': uuid.uuid4().hex, 'client_nonce': uuid.uuid4().hex}
        self.report = {'utc': utc(), 'state': self.phase, 'code_recorded': False,
                       'resident_build_id': RESIDENT, 'control_build_id': CONTROL,
                       'client_id': self.binding['client_id'], 'client_nonce': self.binding['client_nonce'],
                       'checks': []}
        self.report_path = evidence / ('browser-pairing-' + self.binding['client_id'] + '.json')
        self.save(exclusive=True)

    def save(self, exclusive=False):
        self.report['state'] = self.phase
        self.report['updated_utc'] = utc()
        write_json(self.report_path, self.report, exclusive)

    def http(self, port, method, route, body=None, token=None):
        c = http.client.HTTPConnection(self.config['host'], port, timeout=5)
        try:
            headers = {'Connection': 'close'}
            if token:
                headers['Authorization'] = 'Bearer ' + token
            if body is not None:
                body = json.dumps(body).encode()
                headers['Content-Type'] = 'application/json'
            c.request(method, route, body=body, headers=headers)
            reply = c.getresponse()
            raw = reply.read(8193)
            if len(raw) > 8192 or reply.getheader('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('Invalid JSON response framing')
            return reply.status, json.loads(raw)
        finally:
            c.close()

    def check(self, label, port, method, route, expected, body=None, token=None):
        status, reply = self.wire(port, method, route, body, token)
        self.report['checks'].append({'check': label, 'http_status': status, 'passed': status == expected})
        self.save()
        if status != expected or not isinstance(reply, dict):
            raise ValueError('Unexpected response')
        if 'token' in reply and route != '/pairing/confirm':
            raise ValueError('Unexpected credential disclosure')
        return reply

    def neutral(self, reply):
        if (reply.get('version') != '0.3.4' or reply.get('build_id') != CONTROL or reply.get('abi') != 2
                or reply.get('lease_remaining_ms') != 0 or reply.get('work_remaining_ms') != 0
                or reply.get('keep_awake') is not False):
            raise ValueError('Exact idle Control is required')

    def begin(self):
        if self.phase != 'ready':
            return
        try:
            with self.lock():
                self.neutral(self.check('exact idle Control before request', 17867, 'GET', '/status', 200,
                                        token=self.config['token']))
                info = self.check('public native pairing identity', 17866, 'GET', '/pairing/info', 200)
                if (info.get('resident_build_id') != RESIDENT or info.get('control_build_id') != CONTROL
                        or info.get('resident_version') != '0.1.2' or info.get('control_version') != '0.3.4'):
                    raise ValueError('Native identity mismatch')
                if not info.get('pairing_open'):
                    self.message = 'Open pairing on the Vita with SQUARE, then select Start test request.'
                    return
                self.phase = 'uncertain'
                self.report['request_intent_utc'] = utc()
                self.save()
                reply = self.check('fresh public request', 17866, 'POST', '/pairing/request', 201,
                                   {**self.binding, 'client_name': 'Windows pairing test'})
                if not HEX.fullmatch(reply.get('request_id', '')):
                    raise ValueError('Invalid request identity')
                self.binding['request_id'] = reply['request_id']
                self.report['request_id'] = reply['request_id']
                self.phase = 'pending'
                self.message = 'On the Vita, release the controls briefly, then press CROSS once. Enter the six-digit code here immediately.'
                self.save()
        except Exception as error:
            self.report['failure_type'] = type(error).__name__
            self.message = 'The test stopped safely. No automatic retry. Tell Codex this message.'
            self.phase = 'stopped'
            self.save()

    @staticmethod
    def receipt(reply, binding):
        fields = ('protocol', 'device_id', 'client_id', 'credential_id', 'inactivity_days',
                  'last_seen_at', 'expires_at', 'resident_port', 'control_port')
        value = {k: reply[k] for k in fields}
        if (value['protocol'] != 1 or value['client_id'] != binding['client_id']
                or not HEX.fullmatch(value['credential_id']) or not HEX.fullmatch(value['device_id'])
                or value['inactivity_days'] != 90 or value['expires_at'] - value['last_seen_at'] != 7776000
                or value['resident_port'] != 17866 or value['control_port'] != 17867):
            raise ValueError('Invalid native receipt')
        return value

    def confirm(self, code):
        if self.phase != 'pending':
            return
        if not re.fullmatch(r'[0-9]{6}', code):
            self.message = 'Enter exactly six digits, including any leading zeros.'
            return
        try:
            with self.lock():
                self.phase = 'uncertain'
                self.report['confirmation_intent_utc'] = utc()
                self.save()
                status, reply = self.wire(17866, 'POST', '/pairing/confirm', {**self.binding, 'code': code}, None)
                code = ''
                self.report['confirmation_http_status'] = status
                self.save()
                if status != 200 or not isinstance(reply, dict):
                    raise ValueError('Confirmation rejected or uncertain')
                token = reply.pop('token', '')
                if not HEX.fullmatch(token):
                    raise ValueError('Invalid credential')
                # Preserve the returned credential before further qualification can fail.
                credential_path = self.private / ('windows-pairing-qualification-' + self.binding['client_id'] + '.json')
                write_json(credential_path, {'host': self.config['host'], 'port': 17866, 'control_port': 17867,
                                            'token': token, 'client_id': self.binding['client_id'],
                                            'credential_id': reply.get('credential_id')}, exclusive=True)
                self.report['credential_saved_privately'] = True
                self.report['receipt'] = self.receipt(reply, self.binding)
                self.save()
                # Both services permit inspection, with no work or input lease acquired.
                session = self.check('individual saved session', 17866, 'GET', '/pairing/session', 200, token=token)
                self.report['renewed_receipt'] = self.receipt(session, self.binding)
                self.check('individual Resident inspection', 17866, 'GET', '/status', 200, token=token)
                self.neutral(self.check('individual Control inspection', 17867, 'GET', '/status', 200, token=token))
                self.check('individual power inspection', 17867, 'GET', '/power/status', 200, token=token)
                for label, port, route in (
                    ('Resident upload denied', 17866, '/upload/' + uuid.uuid4().hex + '/probe.bin'),
                    ('input denied', 17867, '/input'),
                    ('power lease denied', 17867, '/power/lease'),
                    ('workspace write denied', 17867, '/workspace/write/' + uuid.uuid4().hex + '/probe.bin'),
                    ('app launch denied', 17867, '/app/launch/CHRS00003')):
                    self.check(label, port, 'POST', route, 403, {}, token)
                self.check('Windows Resident authorization retained', 17866, 'GET', '/status', 200,
                           token=self.config['token'])
                self.neutral(self.check('Windows Control authorization retained; no leases', 17867, 'GET', '/status', 200,
                                        token=self.config['token']))
                self.phase = 'complete'
                self.message = 'Pairing passed. Individual inspection and saved session passed; file, input, power and launch requests were denied. Windows access remains available. Reply “Pairing passed” to Codex.'
                self.save()
        except Exception as error:
            self.report['failure_type'] = type(error).__name__
            self.phase = 'stopped'
            self.message = 'The test stopped safely. No automatic retry. Tell Codex this message.'
            self.save()

    def page(self):
        form = ''
        if self.phase in ('ready', 'pending'):
            action = 'request' if self.phase == 'ready' else 'confirm'
            control = '' if self.phase == 'ready' else '<label>Vita code <input name="code" type="password" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="off" required autofocus></label>'
            label = 'Start test request' if self.phase == 'ready' else 'Confirm now'
            form = '<form method="post"><input type="hidden" name="csrf" value="' + self.csrf + '"><input type="hidden" name="action" value="' + action + '">' + control + '<button>' + label + '</button></form>'
        return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>Vita pairing test</title><style>body{background:#121b24;color:#e7f1f6;font:18px system-ui;max-width:680px;margin:60px auto;padding:20px;line-height:1.6}button,input{font:inherit;padding:12px;margin:12px 0;display:block}button{background:#8debd0;border:0;border-radius:6px;color:#102b23;cursor:pointer}small{color:#adbecb}</style>'
                '<h1>Vita pairing test</h1><p>' + html.escape(self.message) + '</p>' + form +
                '<p><small>This form runs only on this PC. The code and credential are never shown in test reports. Keep Starter open while confirming.</small></p></html>').encode()

def serve(config_path):
    sys.path.insert(0, str(ROOT))
    os.environ['VITA_WORKBENCH_LOCK'] = str(ROOT / '.devloop-private/workbench.lock')
    from workbench.session import exclusive
    config = json.loads(config_path.read_text(encoding='utf-8-sig'))
    import ipaddress
    host_address = ipaddress.IPv4Address(config['host'])
    if (not (host_address.is_private or host_address.is_loopback) or host_address.is_unspecified
            or host_address.is_multicast or config.get('port', 17866) != 17866
            or not HEX.fullmatch(config.get('token', ''))):
        raise ValueError('Expected a private IPv4 Resident configuration on port 17866')
    private = ROOT / '.devloop-private'
    private.mkdir(exist_ok=True)
    evidence = ROOT / 'evidence/workbench' / ('pairing-check-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    evidence.mkdir(parents=True)
    state = State(config, evidence, private, exclusive)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def respond(self, status, body=b'', location=None):
            self.send_response(status)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(body)))
            if location:
                self.send_header('Location', location)
            self.end_headers()
            self.wfile.write(body)
        def valid_route(self):
            return (self.path == '/' + state.cap and self.headers.get('Host') == host)
        def do_GET(self):
            if not self.valid_route():
                return self.respond(404)
            self.respond(200, state.page())
        def do_POST(self):
            if not self.valid_route() or self.headers.get('Origin', origin) != origin:
                return self.respond(403)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 1024 or self.headers.get('Content-Type') != 'application/x-www-form-urlencoded':
                    return self.respond(400)
                form = urllib.parse.parse_qs(self.rfile.read(length).decode('ascii'), strict_parsing=True)
                if any(len(v) != 1 for v in form.values()) or not secrets.compare_digest(form.get('csrf', [''])[0], state.csrf):
                    return self.respond(403)
                action = form.get('action', [''])[0]
                if action == 'request':
                    state.begin()
                elif action == 'confirm':
                    state.confirm(form.get('code', [''])[0])
                else:
                    return self.respond(400)
                self.respond(303, location='/' + state.cap)
            except (ValueError, UnicodeError):
                self.respond(400)
    server = HTTPServer(('127.0.0.1', 0), Handler)
    server.timeout = 0.5
    host = '127.0.0.1:' + str(server.server_port)
    origin = 'http://' + host
    # Only the local, secret-free form URL is printed.
    print(origin + '/' + state.cap, flush=True)
    print('Loopback pairing form active for up to 30 minutes; no automatic Vita requests.', flush=True)
    deadline = time.monotonic() + 1800
    try:
        while time.monotonic() < deadline:
            server.handle_request()
    finally:
        server.server_close()

def self_test():
    import tempfile
    import unittest
    class Tests(unittest.TestCase):
        def fixture(self, fault=None):
            temp = tempfile.TemporaryDirectory()
            self.addCleanup(temp.cleanup)
            folder = Path(temp.name)
            calls = []
            token = 'fedcba9876543210fedcba9876543210'
            session = {}
            def wire(port, method, route, body=None, auth=None):
                calls.append((port, method, route, body, auth))
                if route == '/pairing/info':
                    return 200, {'resident_build_id': RESIDENT, 'control_build_id': CONTROL,
                                 'resident_version': '0.1.2', 'control_version': '0.3.4', 'pairing_open': fault != 'closed'}
                if route == '/pairing/request':
                    return 201, {'request_id': 'a' * 32}
                if route == '/pairing/confirm':
                    if fault == 'lost':
                        raise TimeoutError('Sensitive error ' + token + ' 000007')
                    if fault == 'expired':
                        return 409, {'error': 'Challenge expired'}
                    session.update(protocol=1, device_id='b' * 32, client_id=body['client_id'], credential_id='c' * 32,
                                   inactivity_days=90, last_seen_at=1000, expires_at=1000+7776000, resident_port=17866, control_port=17867)
                    return 200, {**session, 'token': token}
                if route == '/pairing/session':
                    return 200, dict(session)
                if method == 'POST':
                    return 403, {'error': 'Inspection only'}
                if port == 17867 and route == '/status':
                    return 200, {'version': '0.3.4', 'build_id': CONTROL, 'abi': 2, 'lease_remaining_ms': 0,
                                 'work_remaining_ms': 0, 'keep_awake': False}
                return 200, {}
            state = State({'host': 'fixture', 'token': 'd' * 32}, folder, folder, nullcontext, wire)
            return state, calls, token
        def test_success_secrets_and_single_execution(self):
            state, calls, token = self.fixture()
            state.begin(); state.begin()
            state.confirm('000007'); state.confirm('000007')
            self.assertEqual(state.phase, 'complete')
            self.assertEqual(sum(c[2] == '/pairing/request' for c in calls), 1)
            self.assertEqual(sum(c[2] == '/pairing/confirm' for c in calls), 1)
            self.assertEqual(sum(c[1] == 'POST' and c[4] == token for c in calls), 5)
            public = state.report_path.read_text() + state.page().decode()
            self.assertNotIn(token, public); self.assertNotIn('000007', public)
            self.assertTrue(all(c['passed'] for c in state.report['checks']))
            saved = list(state.private.glob('windows-pairing-qualification-*.json'))
            self.assertEqual(len(saved), 1)
            self.assertEqual(json.loads(saved[0].read_text())['token'], token)
        def test_confirmation_fault_never_replays_or_logs_secret(self):
            for fault in ('lost', 'expired'):
                state, calls, token = self.fixture(fault)
                state.begin(); state.confirm('000007'); state.confirm('000007'); state.begin()
                self.assertEqual(state.phase, 'stopped')
                self.assertEqual(sum(c[2] == '/pairing/confirm' for c in calls), 1)
                public = state.report_path.read_text() + state.page().decode()
                self.assertNotIn(token, public); self.assertNotIn('000007', public)
                self.assertFalse(list(state.private.glob('windows-pairing-qualification-*.json')))
        def test_closed_window_has_no_request(self):
            state, calls, token = self.fixture('closed')
            state.begin()
            self.assertEqual(state.phase, 'ready')
            self.assertFalse(any(c[1] == 'POST' for c in calls))
        def test_input_validation_retains_leading_zeros(self):
            state, calls, token = self.fixture()
            state.begin(); state.confirm('7')
            self.assertEqual(state.phase, 'pending')
            self.assertFalse(any(c[2] == '/pairing/confirm' for c in calls))
            state.confirm('000007')
            self.assertEqual(next(c[3]['code'] for c in calls if c[2] == '/pairing/confirm'), '000007')
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    if not result.wasSuccessful():
        raise SystemExit(1)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true', help='Use local simulated replies only; no Vita/config access')
    parser.add_argument('--config', type=Path, default=ROOT / '.devloop-private/resident.json')
    parser.add_argument('--resident-build', help='Exact installed Resident build ID, 64 lowercase hex characters')
    parser.add_argument('--control-build', help='Exact installed Control build ID, 64 lowercase hex characters')
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        if not all(isinstance(pin, str) and re.fullmatch('[0-9a-f]{64}', pin) for pin in (args.resident_build, args.control_build)):
            parser.error('Live pairing requires --resident-build and --control-build exact pins')
        RESIDENT, CONTROL = args.resident_build, args.control_build
        serve(args.config)

