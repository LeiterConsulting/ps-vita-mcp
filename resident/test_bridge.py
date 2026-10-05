"""Real stdio MCP calls against an explicitly simulated resident HTTP endpoint."""
import asyncio
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys
import tempfile
import threading
import zipfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
TOKEN = 'a' * 32
files = {}
fault = {'drop_reply': False, 'bad_readback': False, 'rejection': None}
calls = []

def value(result):
    return result.structuredContent or json.loads(result.content[0].text)


class Device(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code, data, mime='application/json'):
        if not isinstance(data, bytes):
            data = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        calls.append(('GET', self.path))
        if self.headers.get('Authorization') != 'Bearer ' + TOKEN:
            return self.reply(401, {'error': 'Unauthorized'})
        if self.path == '/status':
            return self.reply(200, {'app': 'Vita Resident', 'protocol': 1, 'version': '0.1.1', 'build_id': '0' * 64, 'started_ms': 100, 'uptime_ms': 1000, 'heartbeat': 2, 'requests': len(calls), 'uploads': len(files), 'battery_percent': 73, 'charging': 0, 'clocks_mhz': [333, 222, 111, 111], 'network_state': 3, 'keep_awake': False})
        key = self.path.removeprefix('/files/')
        if key not in files:
            return self.reply(404, {'error': 'Not published'})
        payload = files[key]
        if fault['bad_readback']:
            payload = b'X' + payload[1:]
        self.reply(200, payload, 'application/octet-stream')

    def do_POST(self):
        calls.append(('POST', self.path))
        if self.headers.get('Authorization') != 'Bearer ' + TOKEN:
            return self.reply(401, {'error': 'Unauthorized'})
        payload = self.rfile.read(int(self.headers['Content-Length']))
        if fault['rejection'] is not None:
            return self.reply(500, {'error': fault['rejection']})
        digest = hashlib.sha256(payload).hexdigest()
        if digest != self.headers.get('X-SHA256'):
            return self.reply(422, {'error': 'Hash mismatch'})
        key = self.path.removeprefix('/upload/')
        attempt, leaf = key.split('/')
        if key in files:
            return self.reply(409, {'error': 'Already exists'})
        files[key] = payload
        if fault['drop_reply']:
            self.close_connection = True
            return
        self.reply(201, {'app': 'Vita Resident', 'protocol': 1, 'attempt': attempt, 'bytes': len(payload), 'sha256': digest, 'vita_path': f'ux0:data/vita-resident/inbox/{key}', 'storage_readback': True, 'installation': 'pending'})


async def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Device)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    checks = []
    try:
        with tempfile.TemporaryDirectory() as temp:
            fixture_root = Path(temp)
            for name in ('resident/bridge.py', 'bridge/server.py', 'bridge/ftp_staging.py', 'resident/control/bridge_tools.py', 'resident/control/rgb_codec.py'):
                destination = fixture_root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / name, destination)
            for source in (ROOT / 'workbench').glob('*.py'):
                destination = fixture_root / 'workbench' / source.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            # A synthetic local VPK exercises package validation and transport;
            # it is neither an installable app nor a private game-port artifact.
            values = [('TITLE_ID', 'CHRS00003'), ('CATEGORY', 'gd'), ('APP_VER', '01.03'), ('PSP2_SYSTEM_VER', 0)]
            keys = bytearray(); payload = bytearray(); entries = bytearray()
            for key, fixture_value in values:
                key_offset = len(keys); keys.extend(key.encode() + b'\0')
                data = struct.pack('<I', fixture_value) if isinstance(fixture_value, int) else fixture_value.encode() + b'\0'
                entries.extend(struct.pack('<HHIII', key_offset, 0x404 if isinstance(fixture_value, int) else 0x204, len(data), len(data), len(payload)))
                payload.extend(data)
            key_start = 20 + len(entries)
            sfo = struct.pack('<5I', 0x46535000, 0x101, key_start, key_start + len(keys), len(values)) + entries + keys + payload
            package_path = fixture_root / 'dist/devloop/vita_devloop.vpk'
            package_path.parent.mkdir(parents=True)
            with zipfile.ZipFile(package_path, 'w') as archive:
                archive.writestr('eboot.bin', b'SCE\0fixture')
                archive.writestr('sce_sys/param.sfo', sfo)
            package_hash = hashlib.sha256(package_path.read_bytes()).hexdigest()
            # A separately labelled synthetic Input Target checks the actual
            # Workbench candidate journal -> Resident upload -> two-readback flow.
            target_path = fixture_root / 'dist/workbench/input_target.vpk'
            target_path.parent.mkdir(parents=True)
            with zipfile.ZipFile(target_path, 'w') as archive:
                archive.writestr('eboot.bin', b'SCE\0fixture')
                archive.writestr('sce_sys/param.sfo', sfo.replace(b'CHRS00003', b'CHRS00012').replace(b'01.03', b'01.00'))
            target_bytes = target_path.read_bytes()
            target_hash = hashlib.sha256(target_bytes).hexdigest()
            with zipfile.ZipFile(target_path) as archive:
                target_files = [{'name': name, 'bytes': len(archive.read(name)), 'sha256': hashlib.sha256(archive.read(name)).hexdigest()} for name in archive.namelist()]
            target_report = {'build_id': 'e' * 64, 'package': {'titleId': 'CHRS00012', 'version': '01.00',
                             'sha256': target_hash, 'bytes': len(target_bytes), 'files': target_files},
                             'source_hashes': {'resident/bridge.py': hashlib.sha256((fixture_root / 'resident/bridge.py').read_bytes()).hexdigest()},
                             'accepted_artifacts_preserved': {}}
            (target_path.parent / 'build-report.json').write_text(json.dumps(target_report))
            config = Path(temp) / 'resident.json'
            config.write_text(json.dumps({'host': '127.0.0.1', 'port': server.server_port, 'token': TOKEN}), encoding='utf-8')
            env = {**os.environ, 'VITA_RESIDENT_CONFIG': str(config), 'VITA_WORKBENCH_LOCK': str(fixture_root / 'session.lock')}
            async with stdio_client(StdioServerParameters(command=sys.executable, args=[str(fixture_root / 'resident/bridge.py')], env=env)) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    assert len(tools.tools) == 27
                    assert {'vita_resident_status', 'vita_resident_verify_upload', 'vita_resident_probe_upload', 'vita_resident_stage_package'}.issubset({tool.name for tool in tools.tools})
                    checks.append('four-resident-thirteen-control-ten-workbench-tools-listed')
                    status = await session.call_tool('vita_resident_status', {})
                    assert not status.isError and value(status)['app'] == 'Vita Resident'
                    checks.append('status-through-MCP')
                    probe = await session.call_tool('vita_resident_probe_upload', {})
                    assert not probe.isError and value(probe)['read_back_checks'] == 2
                    assert value(probe)['bytes'] == 4096 and files[value(probe)['attempt'] + '/probe.bin'] == bytes(range(256)) * 16
                    checks.append('binary-probe-and-two-readbacks')
                    package = await session.call_tool('vita_resident_stage_package', {'package': 'devloop', 'expected_sha256': package_hash})
                    assert not package.isError and value(package)['title_id'] == 'CHRS00003'
                    checks.append('validated-DevLoop-fixture-staging-through-MCP')
                    before = len(calls)
                    bad = await session.call_tool('vita_resident_stage_package', {'package': 'devloop', 'expected_sha256': '0' * 64})
                    assert bad.isError and len(calls) == before
                    checks.append('wrong-local-hash-refused-before-network')
                    candidate_args = {'package': 'target', 'expected_sha256': target_hash}
                    before = len(calls)
                    staged = value(await session.call_tool('vita_workbench_stage_candidate', candidate_args))
                    assert staged['result'] == 'verified staged candidate; installation and runtime pending', staged
                    attempt = staged['attempt']
                    assert staged['receipt']['attempt'] == attempt and staged['receipt']['read_back_checks'] == 2
                    assert files[attempt + '/package.vpk'] == target_bytes
                    assert calls[before:] == [('GET', '/status'), ('POST', '/upload/' + attempt + '/package.vpk'),
                                             ('GET', '/files/' + attempt + '/package.vpk'), ('GET', '/files/' + attempt + '/package.vpk')]
                    journal = [json.loads(line) for line in (Path(staged['evidence_directory']) / 'journal.jsonl').read_text().splitlines()]
                    assert [entry['kind'] for entry in journal] == ['mutation_intent', 'mutation_receipt']
                    assert journal[0]['attempt'] == attempt == journal[1]['receipt']['attempt']
                    assert staged['activation'] == 'not performed'
                    checks.append('candidate-MCP-journal-wire-attempt-and-two-readbacks-match')
                    before = len(calls)
                    drift = target_path.parent / 'build-report.json'
                    bad_report = {**target_report, 'source_hashes': {'resident/bridge.py': '0' * 64}}
                    drift.write_text(json.dumps(bad_report))
                    assert (await session.call_tool('vita_workbench_stage_candidate', candidate_args)).isError
                    assert len(calls) == before
                    drift.write_text(json.dumps(target_report))
                    checks.append('candidate-source-drift-refused-before-network')
                    fault['drop_reply'] = True
                    before = len(calls)
                    uncertain = value(await session.call_tool('vita_workbench_stage_candidate', candidate_args))
                    fault['drop_reply'] = False
                    assert uncertain['result'] == 'failed or publication uncertain; inspect this attempt without replay'
                    attempt = uncertain['attempt']
                    assert calls[before:] == [('GET', '/status'), ('POST', '/upload/' + attempt + '/package.vpk')]
                    journal = [json.loads(line) for line in (Path(uncertain['evidence_directory']) / 'journal.jsonl').read_text().splitlines()]
                    assert [entry['kind'] for entry in journal] == ['mutation_intent', 'mutation_unconfirmed']
                    assert journal[0]['attempt'] == attempt and journal[1]['replayed'] is False
                    recovered = value(await session.call_tool('vita_resident_verify_upload', {'attempt': attempt, 'file': 'package.vpk',
                                      'expected_sha256': target_hash, 'expected_bytes': len(target_bytes)}))
                    assert recovered['attempt'] == attempt and recovered['read_back_checks'] == 2
                    assert calls[before:] == [('GET', '/status'), ('POST', '/upload/' + attempt + '/package.vpk'),
                                             ('GET', '/files/' + attempt + '/package.vpk'), ('GET', '/files/' + attempt + '/package.vpk')]
                    checks.append('candidate-lost-reply-retains-journal-attempt-read-only-recovery')
                    fault['bad_readback'] = True
                    bad = await session.call_tool('vita_resident_probe_upload', {})
                    assert bad.isError
                    fault['bad_readback'] = False
                    checks.append('corrupted-remote-readback-refused')
                    fault['drop_reply'] = True
                    before = len([call for call in calls if call[0] == 'POST'])
                    uncertain = await session.call_tool('vita_resident_probe_upload', {})
                    assert uncertain.isError
                    text = uncertain.content[0].text
                    attempt = re.search(r'Attempt ([0-9a-f]{32})', text)[1]
                    fault['drop_reply'] = False
                    recovered = await session.call_tool('vita_resident_verify_upload', {'attempt': attempt, 'file': 'probe.bin', 'expected_sha256': hashlib.sha256(bytes(range(256)) * 16).hexdigest(), 'expected_bytes': 4096})
                    assert not recovered.isError and len([call for call in calls if call[0] == 'POST']) == before + 1
                    checks.append('lost-publication-reply-recovered-by-reads-without-replay')
                    bad = await session.call_tool('vita_resident_verify_upload', {'attempt': '../ur0', 'file': 'probe.bin', 'expected_sha256': '0' * 64, 'expected_bytes': 10})
                    assert bad.isError
                    checks.append('invalid-verification-path-refused')
                    fault['rejection'] = 'Storage read-back failed; part retained'
                    before = len([call for call in calls if call[0] == 'POST'])
                    rejected = await session.call_tool('vita_resident_probe_upload', {})
                    assert rejected.isError and 'HTTP 500: Storage read-back failed; part retained' in rejected.content[0].text
                    assert len([call for call in calls if call[0] == 'POST']) == before + 1
                    checks.append('native-rejection-preserved-without-upload-replay')
                    fault['rejection'] = 'Pairing ' + TOKEN
                    rejected = await session.call_tool('vita_resident_probe_upload', {})
                    assert rejected.isError and 'HTTP 500' in rejected.content[0].text and TOKEN not in rejected.content[0].text
                    fault['rejection'] = None
                    checks.append('arbitrary-error-content-not-reflected')
                    config.write_text(json.dumps({'host': '127.0.0.1', 'port': server.server_port, 'token': 'b' * 32}), encoding='utf-8')
                    bad = await session.call_tool('vita_resident_status', {})
                    assert bad.isError and TOKEN not in bad.content[0].text
                    checks.append('auth-failure-and-no-token-in-error')
            # The internal supplied-attempt API is not remotely callable through
            # MCP. Its guard must reject wrong types/paths before any request.
            sys.path.insert(0, str(fixture_root / 'resident'))
            sys.path.insert(0, str(fixture_root / 'bridge'))
            import importlib.util
            spec = importlib.util.spec_from_file_location('candidate_upload_guard', fixture_root / 'resident/bridge.py')
            bridge = importlib.util.module_from_spec(spec); spec.loader.exec_module(bridge)
            sent = []
            bridge.request = lambda *args, **kwargs: sent.append(args)
            for invalid in ('', '../ur0', 'A' * 32, '0' * 31, '0' * 33, 7, False, b'0' * 32):
                try:
                    bridge.upload(b'x', 'package.vpk', invalid)
                except ValueError:
                    pass
                else:
                    raise AssertionError('Invalid attempt accepted')
            assert not sent
            checks.append('supplied-upload-attempt-type-and-path-guard-before-network')
        print(json.dumps({'fixture': 'Simulated HTTP device; actual MCP stdio bridge', 'passed': len(checks), 'checks': checks}, indent=2))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    asyncio.run(main())
