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
            for name in ('resident/bridge.py', 'bridge/ftp_staging.py'):
                destination = fixture_root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / name, destination)
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
            config = Path(temp) / 'resident.json'
            config.write_text(json.dumps({'host': '127.0.0.1', 'port': server.server_port, 'token': TOKEN}), encoding='utf-8')
            env = {**os.environ, 'VITA_RESIDENT_CONFIG': str(config)}
            async with stdio_client(StdioServerParameters(command=sys.executable, args=[str(fixture_root / 'resident/bridge.py')], env=env)) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    assert {'vita_resident_status', 'vita_resident_verify_upload', 'vita_resident_probe_upload', 'vita_resident_stage_package'} == {tool.name for tool in tools.tools}
                    checks.append('four-tools-listed')
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
        print(json.dumps({'fixture': 'Simulated HTTP device; actual MCP stdio bridge', 'passed': len(checks), 'checks': checks}, indent=2))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    asyncio.run(main())
