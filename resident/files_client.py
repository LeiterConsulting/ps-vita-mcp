"""Bounded, read-only observations of Resident's managed inbox.

Range reads bracket data with matching size/hash observations. These checks do
not provide an atomic snapshot, particularly for an in-progress .part file.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Literal
from pydantic import StrictInt

MAX_FILE = 8 * 1024 * 1024
MAX_CHUNK = 16 * 1024
LEAVES = frozenset(('package.vpk', 'probe.bin', 'package.vpk.part', 'probe.bin.part'))
FileLeaf = Literal['package.vpk', 'probe.bin', 'package.vpk.part', 'probe.bin.part']
COMMON = frozenset(('app', 'protocol', 'storage_protocol', 'operation', 'attempt', 'snapshot'))


def _hex(value, size):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(size) + '}', value) is not None


def _attempt(value, *, optional=False):
    if not (optional and value is None) and not _hex(value, 32):
        raise ValueError('Choose a 32-character lowercase hexadecimal inbox attempt')


def _file(value):
    if not isinstance(value, str) or value not in LEAVES:
        raise ValueError('Choose an allowed managed inbox file')


def _integer(value, minimum, maximum, reason):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(reason)


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate JSON field')
        value[key] = item
    return value


def _json(data, content_type):
    try:
        if content_type != 'application/json':
            raise ValueError()
        value = json.loads(data, object_pairs_hook=_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, UnicodeError, TypeError):
        raise RuntimeError('Invalid Resident managed inbox response') from None


def _identity(value, operation, attempt, extra):
    if (set(value) != COMMON | set(extra) or value.get('app') != 'Vita Resident'
            or type(value.get('protocol')) is not int or value['protocol'] != 1
            or type(value.get('storage_protocol')) is not int or value['storage_protocol'] != 1
            or value.get('operation') != operation or value.get('attempt') != attempt
            or value.get('snapshot') is not False):
        raise RuntimeError('Invalid Resident managed inbox identity or schema')


class ManagedInboxClient:
    def __init__(self, requester, status):
        self.requester = requester
        if status()['version'] not in ('0.1.4', '0.1.5', '0.1.6', '0.1.7'):
            raise RuntimeError('Resident managed inbox inspection requires service 0.1.4 or newer')

    def list(self, attempt, offset):
        path = '/storage/list' + ('' if attempt is None else '/' + attempt)
        data, mime, timing = self.requester('GET', path + '?offset=' + str(offset), limit=16384)
        value = _json(data, mime)
        _identity(value, 'list', attempt,
                  ('offset', 'next_offset', 'has_more', 'limit_reached', 'entries'))
        next_offset = value['next_offset']
        more, capped = value['has_more'], value['limit_reached']
        entries = value['entries']
        if (type(value['offset']) is not int or value['offset'] != offset
                or type(more) is not bool or type(capped) is not bool
                or not isinstance(entries, list) or len(entries) > 32
                or (next_offset is not None and (type(next_offset) is not int
                                                  or not offset < next_offset <= 1000))
                or (not more and (next_offset is not None or capped))
                or (more and capped != (offset + 32 > 1000))
                or (more and not capped and next_offset != offset + 32)
                or (more and ((capped and next_offset is not None)
                              or (not capped and next_offset is None)))):
            raise RuntimeError('Invalid Resident managed inbox pagination')
        names = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise RuntimeError('Invalid Resident managed inbox entry')
            if attempt is None:
                valid = (set(entry) == {'name', 'kind'} and _hex(entry.get('name'), 32)
                         and entry.get('kind') == 'directory')
            else:
                valid = (set(entry) == {'name', 'kind', 'bytes'}
                         and isinstance(entry.get('name'), str) and entry['name'] in LEAVES
                         and entry.get('kind') == 'file' and type(entry.get('bytes')) is int
                         and 0 <= entry['bytes'] <= MAX_FILE)
            if not valid or entry['name'] in names:
                raise RuntimeError('Invalid Resident managed inbox entry')
            names.add(entry['name'])
        return {**value, 'bridge': timing,
                'consistency': 'Unordered, non-atomic page; offsets count raw directory entries'}

    def info(self, attempt, file):
        data, mime, timing = self.requester('GET', f'/storage/stat/{attempt}/{file}')
        value = _json(data, mime)
        _identity(value, 'stat', attempt, ('file', 'bytes', 'sha256'))
        if (value['file'] != file or type(value['bytes']) is not int
                or not 0 <= value['bytes'] <= MAX_FILE or not _hex(value['sha256'], 64)):
            raise RuntimeError('Invalid Resident managed inbox file information')
        return {**value, 'bridge': timing}

    def read(self, attempt, file, expected_sha256, expected_bytes, offset, length):
        before = self.info(attempt, file)

        def matches(info):
            return info['sha256'] == expected_sha256 and info['bytes'] == expected_bytes

        if not matches(before):
            raise RuntimeError('Resident file information does not match the expected hash and size')
        count = min(length, expected_bytes - offset)
        data, mime, timing = self.requester('GET',
            f'/storage/read/{attempt}/{file}?offset={offset}&length={length}', limit=MAX_CHUNK)
        if mime != 'application/octet-stream' or len(data) != count:
            raise RuntimeError('Resident range read does not match the expected length or content type')
        whole = offset == 0 and count == expected_bytes
        if whole and hashlib.sha256(data).hexdigest() != expected_sha256:
            raise RuntimeError('Resident complete-file read does not match the expected hash')
        after = self.info(attempt, file)
        if not matches(after):
            raise RuntimeError('Resident file information changed during the range read')
        return {'app': 'Vita Resident', 'protocol': 1, 'storage_protocol': 1,
                'operation': 'read', 'attempt': attempt, 'file': file,
                'expected_sha256': expected_sha256, 'expected_bytes': expected_bytes,
                'offset': offset, 'requested_length': length, 'bytes': len(data),
                'data_base64': base64.b64encode(data).decode('ascii'),
                'snapshot': False, 'full_file_hash_verified': whole,
                'consistency': 'Matching hash and size observations before and after; not an atomic snapshot',
                'bridge': timing, 'stat_before': before['bridge'], 'stat_after': after['bridge']}


def register(mcp, requester, status, configuration, annotations):
    def client():
        endpoint = dict(configuration())
        return ManagedInboxClient(
            lambda *args, **kwargs: requester(*args, **kwargs, endpoint=endpoint),
            lambda: status(endpoint=endpoint))

    @mcp.tool(annotations=annotations)
    def vita_resident_list_inbox(attempt: str | None = None, offset: StrictInt = 0) -> dict:
        """List one unordered managed inbox page; pagination is not an atomic snapshot."""
        _attempt(attempt, optional=True)
        _integer(offset, 0, 1000, 'Choose an inbox offset from 0 through 1000')
        return client().list(attempt, offset)

    @mcp.tool(annotations=annotations)
    def vita_resident_file_info(attempt: str, file: FileLeaf) -> dict:
        """Inspect size and SHA-256 of one allowed inbox file, including retained .part data."""
        _attempt(attempt)
        _file(file)
        return client().info(attempt, file)

    @mcp.tool(annotations=annotations)
    def vita_resident_read_file(attempt: str, file: FileLeaf, expected_sha256: str,
                                expected_bytes: StrictInt, offset: StrictInt = 0,
                                length: StrictInt = MAX_CHUNK) -> dict:
        """Read at most 16 KiB as base64 with size/hash observations bracketing the read.

        Only a complete file fitting this single range gets an independent byte
        hash check. Partial ranges remain non-atomic observations; no full-file
        download is performed automatically.
        """
        _attempt(attempt)
        _file(file)
        if not _hex(expected_sha256, 64):
            raise ValueError('Pin a lowercase SHA-256 digest before reading a file')
        _integer(expected_bytes, 0, MAX_FILE, 'Pin an expected file size from 0 through 8 MiB')
        _integer(offset, 0, expected_bytes, 'Choose a read offset within the expected file size')
        _integer(length, 1, MAX_CHUNK, 'Choose a range length from 1 through 16384 bytes')
        return client().read(attempt, file, expected_sha256, expected_bytes, offset, length)
