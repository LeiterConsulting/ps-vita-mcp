"""Independent MCP bridge for the SceShell resident-service prototype."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import http.client
import io
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Literal
import uuid
import zipfile
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bridge'))
from ftp_staging import read_sfo
CONFIG = Path(os.environ.get('VITA_RESIDENT_CONFIG', str(ROOT / '.devloop-private/resident.json')))
MAX_FILE = 8 * 1024 * 1024
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
REMOTE_REASONS = frozenset({
    'Invalid upload metadata', 'Probe exceeds 64 KiB',
    'Attempt exists or storage unavailable; choose a fresh attempt', 'Cannot create part file',
    'Incomplete upload; part retained and final file not published', 'Upload hash mismatch; part retained',
    'Storage read-back failed; part retained', 'Final rename failed; outcome needs inspection',
    'Unknown file', 'Published file unavailable', 'NUL in header',
    'Header exceeds bound or incomplete', 'Invalid request framing',
    'Pairing authorization required', 'GET body is not supported', 'Method not supported',
})


class ResidentRejection(RuntimeError):
    """Only expose fixed protocol error reasons; never reflect arbitrary server content."""
    def __init__(self, status: int, reason: str | None):
        self.status = status
        self.reason = reason if reason in REMOTE_REASONS else None
        super().__init__(f'Resident rejected request with HTTP {status}' + (': ' + self.reason if self.reason else ''))


mcp = FastMCP('Vita Resident', instructions='This prototype contacts a user plugin running in SceShell, independently of the foreground DevLoop app. Status is device-level, not game telemetry. Staging writes only fresh inbox attempts and does not install packages. Never automatically replay an uncertain upload; use verify_upload for its reported attempt. True sleep may make the service unavailable; do not change sleep settings. Physical app-switching acceptance is separate from PC tests.', log_level='WARNING')


def configuration() -> dict:
    try:
        data = json.loads(CONFIG.read_text(encoding='utf-8-sig'))
        address = ipaddress.IPv4Address(data['host'])
        if not (address.is_private or address.is_loopback) or address.is_unspecified or address.is_multicast:
            raise ValueError('Endpoint must be local')
        if type(data['port']) is not int or not 1 <= data['port'] <= 65535 or not re.fullmatch('[0-9a-f]{32}', data['token']):
            raise ValueError('Invalid pairing configuration')
        return {'host': str(address), 'port': data['port'], 'token': data['token']}
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise RuntimeError('Resident pairing is not configured; use the staged prototype setup.') from error


def request(method: str, path: str, body: bytes | None = None, digest: str | None = None, limit: int = 4096):
    config = configuration()
    connection = http.client.HTTPConnection(config['host'], config['port'], timeout=30 if body is not None else 10)
    headers = {'Authorization': 'Bearer ' + config['token'], 'Connection': 'close'}
    if digest:
        headers['X-SHA256'] = digest
    started = time.monotonic()
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        data = response.read(limit + 1)
        if len(data) > limit:
            raise RuntimeError('Resident response exceeded the expected length')
        if response.status not in [200, 201]:
            reason = None
            try:
                native_error = json.loads(data)
                candidate = native_error.get('error') if isinstance(native_error, dict) else None
                if isinstance(candidate, str):
                    reason = candidate
            except (ValueError, UnicodeError):
                pass
            raise ResidentRejection(response.status, reason)
        return data, response.getheader('Content-Type', '').split(';')[0], {'received_utc': datetime.now(timezone.utc).isoformat(), 'round_trip_ms': round((time.monotonic() - started) * 1000, 2)}
    except (OSError, http.client.HTTPException) as error:
        raise RuntimeError('Resident service unavailable or interrupted. Wake/reconnect the Vita; do not automatically replay an upload.') from error
    finally:
        connection.close()


@mcp.tool(annotations=READ)
def vita_resident_status() -> dict:
    """Read resident heartbeat, process instance, battery, clocks and network state."""
    data, content_type, timing = request('GET', '/status')
    value = json.loads(data)
    if content_type != 'application/json' or value.get('app') != 'Vita Resident' or value.get('protocol') != 1 or value.get('version') != '0.1.1':
        raise RuntimeError('Unexpected resident service identity')
    if not isinstance(value.get('build_id'), str) or not re.fullmatch('[0-9a-f]{64}', value['build_id']):
        raise RuntimeError('Invalid resident build identifier')
    for key in ('started_ms', 'uptime_ms', 'heartbeat', 'requests', 'uploads'):
        if type(value.get(key)) is not int or value[key] < 0:
            raise RuntimeError('Invalid resident counters')
    value['bridge'] = timing
    return value


def verify(attempt: str, leaf: str, expected_sha256: str, expected_bytes: int) -> dict:
    if not re.fullmatch('[0-9a-f]{32}', attempt) or leaf not in ['package.vpk', 'probe.bin'] or not re.fullmatch('[0-9a-f]{64}', expected_sha256) or type(expected_bytes) is not int or not 0 < expected_bytes <= MAX_FILE:
        raise ValueError('Invalid verification identity')
    checks = []
    for _ in range(2):
        payload, content_type, timing = request('GET', f'/files/{attempt}/{leaf}', limit=expected_bytes)
        digest = hashlib.sha256(payload).hexdigest()
        if content_type != 'application/octet-stream' or len(payload) != expected_bytes or digest != expected_sha256:
            raise RuntimeError('Resident file read-back does not match the expected artifact')
        checks.append(timing)
    return {'attempt': attempt, 'file': leaf, 'bytes': expected_bytes, 'sha256': expected_sha256, 'read_back_checks': 2, 'vita_path': f'ux0:data/vita-resident/inbox/{attempt}/{leaf}', 'read_backs': checks, 'installation': 'pending'}


@mcp.tool(annotations=READ)
def vita_resident_verify_upload(attempt: str, file: Literal['package.vpk', 'probe.bin'], expected_sha256: str, expected_bytes: int) -> dict:
    """Read back a published attempt twice, including recovery after a lost upload reply."""
    return verify(attempt, file, expected_sha256, expected_bytes)


def upload(payload: bytes, leaf: str) -> dict:
    if not 0 < len(payload) <= MAX_FILE or leaf not in ['package.vpk', 'probe.bin']:
        raise ValueError('Invalid upload')
    attempt = uuid.uuid4().hex
    digest = hashlib.sha256(payload).hexdigest()
    try:
        data, content_type, timing = request('POST', f'/upload/{attempt}/{leaf}', payload, digest)
        result = json.loads(data)
        expected_path = f'ux0:data/vita-resident/inbox/{attempt}/{leaf}'
        if content_type != 'application/json' or result.get('app') != 'Vita Resident' or result.get('protocol') != 1 or result.get('attempt') != attempt or result.get('bytes') != len(payload) or result.get('sha256') != digest or result.get('vita_path') != expected_path or result.get('storage_readback') is not True:
            raise RuntimeError('Invalid publication receipt; inspect this attempt before proceeding')
        proof = verify(attempt, leaf, digest, len(payload))
        proof['device_storage_readback'] = True
        proof['upload'] = timing
        return proof
    except Exception as error:
        cause = str(error) if isinstance(error, ResidentRejection) else type(error).__name__
        raise RuntimeError(f'Upload outcome may be uncertain. Attempt {attempt}; file {leaf}; expected bytes {len(payload)}; SHA-256 {digest}. Do not replay this upload. Verify the attempt first. Cause: {cause}.') from error


@mcp.tool(annotations=WRITE)
def vita_resident_probe_upload() -> dict:
    """Upload a fixed 4 KiB binary probe to a fresh inbox and verify two read-backs."""
    return upload(bytes(range(256)) * 16, 'probe.bin')


def package_bytes(package: str, expected_sha256: str) -> tuple[bytes, dict]:
    paths = {'devloop': ('dist/devloop/vita_devloop.vpk', 'CHRS00003')}
    if package not in paths or not re.fullmatch('[0-9a-f]{64}', expected_sha256):
        raise ValueError('Choose an allowed package and its exact SHA-256')
    relative, title_id = paths[package]
    with (ROOT / relative).open('rb') as handle:
        payload = handle.read(MAX_FILE + 1)
    if not 0 < len(payload) <= MAX_FILE or hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError('Package size or expected SHA-256 does not match')
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        entries = archive.infolist()
        names = [item.filename for item in entries]
        if len(set(names)) != len(names) or len(names) > 64 or any(name.startswith('/') or '\\' in name or '..' in name.split('/') for name in names) or sum(item.file_size for item in entries) > 64 * 1024 * 1024:
            raise ValueError('Package entries exceed the allowed layout')
        if archive.testzip() is not None or archive.read('eboot.bin')[:4] != b'SCE\0':
            raise ValueError('Invalid ZIP or executable')
        sfo = read_sfo(archive.read('sce_sys/param.sfo'))
    if sfo.get('TITLE_ID') != title_id or sfo.get('CATEGORY') != 'gd' or type(sfo.get('PSP2_SYSTEM_VER')) is not int or sfo['PSP2_SYSTEM_VER'] > 0x03650000:
        raise ValueError('Package title or firmware does not match')
    return payload, {'package': package, 'title_id': title_id, 'version': sfo['APP_VER'], 'local_file': str(ROOT / relative)}


@mcp.tool(annotations=WRITE)
def vita_resident_stage_package(package: Literal['devloop'], expected_sha256: str) -> dict:
    """Validate an allowed local VPK and stage it while another Vita app runs; installation is manual."""
    payload, identity = package_bytes(package, expected_sha256)
    return {**upload(payload, 'package.vpk'), **identity}



if __name__ == '__main__':
    mcp.run()
