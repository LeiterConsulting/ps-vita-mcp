"""Actual stdio MCP inspection calls against an explicitly simulated inbox."""
import asyncio
import base64
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from urllib.parse import parse_qs, urlsplit

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
TOKEN = 'a' * 32
ATTEMPT = 'c' * 32
MAX_FILE = 8 * 1024 * 1024
CHUNK = 16384
PAYLOAD = bytes(range(256)) * 16
FILES = {'probe.bin': PAYLOAD, 'package.vpk': bytes(range(256)) * (MAX_FILE // 256),
         'probe.bin.part': b'', 'package.vpk.part': b'retained incomplete bytes'}
calls = []
fault = {}
stat_count = 0
config_path = None


def value(result):
    return result.structuredContent or json.loads(result.content[0].text)


def common(operation, attempt):
    return {'app': 'Vita Resident', 'protocol': 1, 'storage_protocol': 1,
            'operation': operation, 'attempt': attempt, 'snapshot': False}


def listing(attempt=None, offset=0):
    entries = ([{'name': ATTEMPT, 'kind': 'directory'}] if attempt is None else
               [{'name': leaf, 'kind': 'file', 'bytes': len(data)} for leaf, data in FILES.items()])
    return {**common('list', attempt), 'offset': offset, 'next_offset': None,
            'has_more': False, 'limit_reached': False, 'entries': entries}


def information(leaf='probe.bin'):
    data = FILES[leaf]
    return {**common('stat', ATTEMPT), 'file': leaf, 'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest()}


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
        global stat_count
        calls.append(('GET', self.path))
        if self.headers.get('Authorization') != 'Bearer ' + TOKEN:
            return self.reply(403, {'error': 'Pairing ' + TOKEN})
        url = urlsplit(self.path)
        if url.path == '/status':
            return self.reply(200, {'app': 'Vita Resident', 'protocol': 1,
                'version': fault.get('version', '0.1.4'), 'build_id': '0' * 64,
                'started_ms': 100, 'uptime_ms': 1000, 'heartbeat': 2,
                'requests': len(calls), 'uploads': 0})
        if 'rejection' in fault:
            return self.reply(fault['rejection'], {'error': 'Pairing ' + TOKEN})
        if url.path.startswith('/storage/list'):
            attempt = None if url.path == '/storage/list' else url.path.rsplit('/', 1)[1]
            offset = int(parse_qs(url.query)['offset'][0])
            result = fault.get('list', listing(attempt, offset))
            return self.reply(200, result, fault.get('mime', 'application/json'))
        if url.path.startswith('/storage/stat/'):
            stat_count += 1
            _, _, _, attempt, leaf = url.path.split('/')
            if leaf == 'missing.bin' or fault.get('missing'):
                return self.reply(404, {'error': 'Unknown file'})
            result = copy.deepcopy(fault.get('stat', information(leaf)))
            if fault.get('changed_after') and stat_count > 1:
                result['sha256'] = '0' * 64
            return self.reply(200, result, fault.get('mime', 'application/json'))
        if url.path.startswith('/storage/read/'):
            _, _, _, attempt, leaf = url.path.split('/')
            query = parse_qs(url.query)
            offset, length = int(query['offset'][0]), int(query['length'][0])
            if offset > len(FILES[leaf]):
                return self.reply(416, {'error': 'Range unavailable'})
            data = FILES[leaf][offset:offset + length]
            mode = fault.get('read')
            if mode == 'short':
                data = data[:-1]
            elif mode == 'long':
                data += b'x'
            elif mode == 'corrupt':
                data = b'x' + data[1:]
            elif mode == 'config_change':
                config_path.write_text(json.dumps({'host': '127.0.0.1',
                    'port': self.server.server_port, 'token': 'b' * 32}), encoding='utf-8')
            return self.reply(200, data, 'text/plain' if mode == 'mime' else 'application/octet-stream')
        return self.reply(404, {'error': 'Unknown request'})

    def do_POST(self):
        calls.append(('POST', self.path))
        self.reply(405, {'error': 'Unexpected mutation'})


async def main():
    global config_path, stat_count
    server = ThreadingHTTPServer(('127.0.0.1', 0), Device)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    checks = []
    try:
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / 'resident.json'
            config = {'host': '127.0.0.1', 'port': server.server_port, 'token': TOKEN}
            config_path.write_text(json.dumps(config), encoding='utf-8')
            env = {**os.environ, 'VITA_RESIDENT_CONFIG': str(config_path),
                   'VITA_WORKBENCH_LOCK': str(Path(temp) / 'workbench.lock')}
            async with stdio_client(StdioServerParameters(command=sys.executable,
                    args=[str(ROOT / 'resident/bridge.py')], env=env)) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = (await session.list_tools()).tools
                    names = ('vita_resident_list_inbox', 'vita_resident_file_info', 'vita_resident_read_file')
                    assert len(tools) == 42 and all(name in {tool.name for tool in tools} for name in names)
                    for tool in tools:
                        if tool.name in names:
                            assert tool.annotations.readOnlyHint is True
                            assert tool.annotations.destructiveHint is False
                            assert tool.annotations.idempotentHint is True
                    checks.append('42-tools-and-readonly-inbox-annotations-through-stdio')

                    async def ok(name, args):
                        result = await session.call_tool(name, args)
                        assert not result.isError, result
                        return value(result)

                    async def rejected(name, args, contains=None):
                        result = await session.call_tool(name, args)
                        assert result.isError, result
                        text = result.content[0].text
                        assert TOKEN not in text
                        if contains:
                            assert contains in text, text
                        return text

                    for old in ('0.1.1', '0.1.2', '0.1.3'):
                        fault['version'] = old
                        start = len(calls)
                        await rejected(names[0], {}, 'requires service 0.1.4')
                        assert calls[start:] == [('GET', '/status')]
                    fault.clear()
                    checks.append('older-installed-services-explicitly-unsupported-without-storage-request')

                    root = await ok(names[0], {})
                    assert root['entries'] == [{'name': ATTEMPT, 'kind': 'directory'}]
                    assert root['snapshot'] is False and 'non-atomic' in root['consistency']
                    files = await ok(names[0], {'attempt': ATTEMPT})
                    assert {item['name'] for item in files['entries']} == set(FILES)
                    assert next(item for item in files['entries'] if item['name'] == 'probe.bin.part')['bytes'] == 0
                    checks.append('root-and-attempt-listing-with-allowed-final-and-retained-parts')

                    page = listing(offset=32)
                    page.update(next_offset=64, has_more=True)
                    fault['list'] = page
                    paged = await ok(names[0], {'offset': 32})
                    assert paged['next_offset'] == 64 and paged['has_more']
                    page = listing(offset=1000)
                    page.update(next_offset=None, has_more=True, limit_reached=True, entries=[])
                    fault['list'] = page
                    capped = await ok(names[0], {'offset': 1000})
                    assert capped['limit_reached'] is True and capped['next_offset'] is None
                    fault.clear()
                    checks.append('unordered-raw-offset-pagination-and-explicit-1000-cap')

                    for leaf in FILES:
                        result = await ok(names[1], {'attempt': ATTEMPT, 'file': leaf})
                        assert result['sha256'] == information(leaf)['sha256'] and result['bytes'] == len(FILES[leaf])
                        assert result['snapshot'] is False
                    checks.append('sha256-information-for-final-zero-byte-and-incomplete-part-files')

                    def args(leaf='probe.bin', **kwargs):
                        return {'attempt': ATTEMPT, 'file': leaf,
                                'expected_sha256': information(leaf)['sha256'],
                                'expected_bytes': len(FILES[leaf]), **kwargs}

                    stat_count = 0
                    start = len(calls)
                    complete = await ok(names[2], args())
                    assert base64.b64decode(complete['data_base64']) == PAYLOAD
                    assert complete['full_file_hash_verified'] is True and complete['snapshot'] is False
                    assert calls[start:] == [('GET', '/status'), ('GET', f'/storage/stat/{ATTEMPT}/probe.bin'),
                        ('GET', f'/storage/read/{ATTEMPT}/probe.bin?offset=0&length=16384'),
                        ('GET', f'/storage/stat/{ATTEMPT}/probe.bin')]
                    checks.append('complete-small-file-hashed-with-exact-status-stat-range-stat-sequence')

                    start = len(calls)
                    partial = await ok(names[2], args('package.vpk', offset=123, length=CHUNK))
                    assert base64.b64decode(partial['data_base64']) == FILES['package.vpk'][123:123 + CHUNK]
                    assert partial['bytes'] == CHUNK and partial['full_file_hash_verified'] is False
                    assert len(calls[start:]) == 4 and sum('/storage/read/' in path for _, path in calls[start:]) == 1
                    assert 'not an atomic snapshot' in partial['consistency']
                    checks.append('8MiB-file-only-one-16KiB-range-no-implicit-full-download-or-full-hash-claim')

                    tail = await ok(names[2], args(offset=len(PAYLOAD) - 3, length=100))
                    assert base64.b64decode(tail['data_base64']) == PAYLOAD[-3:]
                    end = await ok(names[2], args(offset=len(PAYLOAD), length=100))
                    assert end['bytes'] == 0 and end['data_base64'] == '' and end['full_file_hash_verified'] is False
                    zero = await ok(names[2], args('probe.bin.part'))
                    assert zero['bytes'] == 0 and zero['data_base64'] == '' and zero['full_file_hash_verified'] is True
                    part = await ok(names[2], args('package.vpk.part', offset=2, length=7))
                    assert base64.b64decode(part['data_base64']) == FILES['package.vpk.part'][2:9]
                    checks.append('short-final-range-eof-empty-range-and-retained-part-read-semantics')

                    invalids = [(names[0], {'attempt': value}) for value in
                                ('../ur0', 'A' * 32, 'c' * 31, 'c' * 33, '', 1)]
                    invalids += [(names[0], {'offset': item}) for item in (-1, 1001, True, 0.5, '0')]
                    invalids += [(names[1], {'attempt': ATTEMPT, 'file': item}) for item in
                                 ('../config.txt', 'probe.bin/../config.txt', 'bridge.cfg', 'probe.bin%00', 'probe.bin.part.extra')]
                    invalids += [(names[2], args(expected_sha256=item)) for item in ('0' * 63, 'A' * 64, '../ur0')]
                    invalids += [(names[2], args(expected_bytes=item)) for item in (-1, MAX_FILE + 1, True, '4096')]
                    invalids += [(names[2], args(offset=item)) for item in (-1, len(PAYLOAD) + 1, True, '0')]
                    invalids += [(names[2], args(length=item)) for item in (0, CHUNK + 1, True, '1')]
                    for name, arguments in invalids:
                        start = len(calls)
                        await rejected(name, arguments)
                        assert len(calls) == start, arguments
                    checks.append('path-type-hash-size-offset-and-chunk-bounds-refused-before-network')

                    bad_lists = [[], {**listing(), 'app': 'Other'}, {**listing(), 'protocol': True},
                        {**listing(), 'storage_protocol': 2}, {**listing(), 'operation': 'read'},
                        {**listing(), 'attempt': ATTEMPT}, {**listing(), 'snapshot': True},
                        {**listing(), 'offset': True}, {**listing(), 'offset': 1},
                        {**listing(), 'entries': {}}, {**listing(), 'has_more': 1},
                        {**listing(), 'limit_reached': 0}, {**listing(), 'next_offset': True},
                        {**listing(), 'next_offset': 0, 'has_more': True},
                        {**listing(), 'next_offset': 1001, 'has_more': True},
                        {**listing(), 'next_offset': 1, 'has_more': True},
                        {**listing(), 'next_offset': None, 'has_more': True, 'limit_reached': True},
                        {**listing(), 'has_more': True}, {**listing(), 'limit_reached': True},
                        {**listing(), 'has_more': True, 'limit_reached': True, 'next_offset': 32},
                        {**listing(), 'entries': [{'name': '../ur0', 'kind': 'directory'}]},
                        {**listing(), 'entries': [{'name': ATTEMPT, 'kind': 'file'}]},
                        {**listing(), 'entries': [{'name': ATTEMPT, 'kind': 'directory', 'bytes': 1}]},
                        {**listing(), 'entries': [listing()['entries'][0]] * 2},
                        {**listing(), 'entries': [{'name': f'{number:032x}', 'kind': 'directory'} for number in range(33)]},
                        {**listing(), 'unexpected': TOKEN}]
                    for payload in bad_lists:
                        fault['list'] = payload
                        await rejected(names[0], {})
                    for entry in ({'name': 'bridge.cfg', 'kind': 'file', 'bytes': 1},
                                  {'name': 'probe.bin', 'kind': 'file', 'bytes': True},
                                  {'name': 'probe.bin', 'kind': 'file', 'bytes': MAX_FILE + 1},
                                  {'name': 'probe.bin', 'kind': 'directory', 'bytes': 1}):
                        fault['list'] = {**listing(ATTEMPT), 'entries': [entry]}
                        await rejected(names[0], {'attempt': ATTEMPT})
                    fault.clear()
                    checks.append('strict-list-identities-pagination-entry-types-and-remote-name-confinement')

                    bad_stats = [[], {**information(), 'app': 'Other'}, {**information(), 'protocol': True},
                        {**information(), 'storage_protocol': True}, {**information(), 'operation': 'list'},
                        {**information(), 'attempt': 'b' * 32}, {**information(), 'file': 'package.vpk'},
                        {**information(), 'bytes': True}, {**information(), 'bytes': -1},
                        {**information(), 'bytes': MAX_FILE + 1}, {**information(), 'sha256': 'g' * 64},
                        {**information(), 'snapshot': True}, {**information(), 'extra': TOKEN}]
                    for payload in bad_stats:
                        fault['stat'] = payload
                        await rejected(names[1], {'attempt': ATTEMPT, 'file': 'probe.bin'})
                    fault.clear()
                    for data in (b'not json ' + TOKEN.encode(), b'{"app":"Vita Resident","app":"Other"}', b'{"a":NaN}'):
                        fault['list'] = data
                        await rejected(names[0], {})
                    fault.clear()
                    fault['mime'] = 'text/plain'
                    await rejected(names[0], {})
                    fault.clear()
                    checks.append('strict-stat-schema-and-malformed-duplicate-nonfinite-JSON-refused-without-content-reflection')

                    for changed in ({'expected_sha256': '0' * 64}, {'expected_bytes': len(PAYLOAD) + 1}):
                        start = len(calls)
                        await rejected(names[2], args(**changed), 'does not match the expected hash and size')
                        assert calls[start:] == [('GET', '/status'), ('GET', f'/storage/stat/{ATTEMPT}/probe.bin')]
                    checks.append('wrong-hash-or-size-pin-stops-before-byte-read')

                    for mode in ('short', 'long', 'corrupt', 'mime'):
                        fault['read'] = mode
                        await rejected(names[2], args())
                    fault.clear()
                    stat_count = 0
                    fault['changed_after'] = True
                    await rejected(names[2], args(), 'changed during the range read')
                    fault.clear()
                    checks.append('short-long-corrupt-mime-and-after-read-hash-drift-refused')

                    fault['missing'] = True
                    await rejected(names[1], {'attempt': ATTEMPT, 'file': 'package.vpk.part'}, 'HTTP 404')
                    fault.clear()
                    for code in (403, 404, 416, 500):
                        fault['rejection'] = code
                        await rejected(names[0], {}, 'HTTP ' + str(code))
                    fault.clear()
                    checks.append('missing-retained-part-and-http-errors-suppress-arbitrary-response-content')

                    fault['read'] = 'config_change'
                    start = len(calls)
                    await rejected(names[2], args(), 'endpoint configuration changed')
                    assert len(calls[start:]) == 3 and '/storage/stat/' not in calls[-1][1]
                    config_path.write_text(json.dumps(config), encoding='utf-8')
                    fault.clear()
                    checks.append('configuration-change-during-read-stops-before-followup-on-new-endpoint')
                    assert all(method == 'GET' for method, _ in calls)
                    checks.append('all-inbox-inspection-requests-readonly-no-retry-or-mutation')
        print(json.dumps({'fixture': 'Simulated HTTP inbox; actual MCP stdio bridge',
                          'passed': len(checks), 'checks': checks}, indent=2))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    asyncio.run(main())
