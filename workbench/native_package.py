"""Fixed native-lab package validation and independently constructed homebrew head.

No upstream binary template, signing key or opaque signature bytes are used.
The package wire layout and fake authentication transform are interoperability
facts documented by VitaShell's package installer. Native promoter acceptance
of this newly constructed header remains a separate device qualification gate.
https://github.com/TheOfficialFloW/VitaShell/blob/master/package_installer.c
https://github.com/hrydgard/ppsspp/blob/master/docs/pkg_notes.md
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import re
import struct
import sys
import zipfile
import xml.etree.ElementTree as ET

PROJECT = 'lifecycle_lab'
TITLE = 'VMCP00001'
MAX_FILE = 8 * 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024
FILES = ('eboot.bin', 'sce_sys/param.sfo', 'sce_sys/icon0.png',
         'sce_sys/livearea/contents/bg.png', 'sce_sys/livearea/contents/startup.png',
         'sce_sys/livearea/contents/template.xml', 'LICENSE', 'sce_sys/package/head.bin')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate JSON field')
        value[key] = item
    return value


def json_object(raw):
    value = json.loads(raw, object_pairs_hook=unique_object,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON')))
    if not isinstance(value, dict):
        raise ValueError('Expected JSON object')
    return value


def _fake_auth(data):
    digest = hashlib.sha1(data).digest()
    seed = digest[4:12] * 2 + digest[12:16] + bytes((digest[16], *digest[1:4]))
    seed += seed[16:24]
    return hashlib.sha1(seed.ljust(64, b'\0')).digest()[:16]


def make_head(title_id=TITLE, package_bytes=0):
    """Construct a debug homebrew package header from format fields and zeroes.

    The fixed lab title is the only supported content identity. Sizes are big
    endian. Unused QA/signature regions remain zero. Three fake-auth digests
    cover the header, metadata and complete prefix in that dependency order.
    """
    if title_id != TITLE or type(package_bytes) is not int or not 0 <= package_bytes <= MAX_FILE:
        raise ValueError('Unsupported homebrew package identity')
    data = bytearray(0x430)
    struct.pack_into('>IHHIIIIQQQ', data, 0, 0x7f504b47, 0, 1, 0x280, 11,
                     0x190, 3, package_bytes, 0xa90, 0x310)
    content = f'EP9000-{title_id}_00-0000000000000000'.encode('ascii')
    data[0x30:0x30 + len(content)] = content
    struct.pack_into('>8I', data, 0xc0, 0x7f657874, 1, 0x40, 0x180,
                     0x100, 0x410, 0, 0xde0)
    struct.pack_into('>4I', data, 0xe0, 0, 0xc0000002, 0x420, 0)
    records = ((1, struct.pack('>I', 2)), (2, struct.pack('>I', 0x15)),
               (3, struct.pack('>I', 0xe)), (4, struct.pack('>Q', package_bytes)),
               (5, struct.pack('>I', 0x19670100)), (8, bytes(8)),
               (9, struct.pack('>Q', 0x240000)), (13, bytes(40)),
               (15, bytes(72)), (16, bytes(56)), (17, bytes(40)))
    metadata = b''.join(struct.pack('>II', key, len(value)) + value for key, value in records)
    data[0x280:0x280 + len(metadata)] = metadata
    data[0x100:0x110] = _fake_auth(data[:0x100])
    data[0x410:0x420] = _fake_auth(data[0x280:0x3d0])
    data[0x420:0x430] = _fake_auth(data[:0x420])
    return bytes(data)


def validate_head(data, package_bytes):
    if data != make_head(TITLE, package_bytes):
        raise ValueError('Homebrew package header differs from the independent generator')


def validate_self(data, native_build_id):
    """Check the fixed uncompressed ARM32 user SELF and its literal build marker."""
    marker = ('VITA_NATIVE_LIFECYCLE_LAB:' + native_build_id).encode('ascii')
    if (len(data) < 0x88 or data[:4] != b'SCE\0'
            or struct.unpack_from('<Q', data, 0x38)[0] != 0x80
            or struct.unpack_from('<Q', data, 0x80)[0] != 0x2f00000000000001
            or marker not in data):
        raise ValueError('Native-lab SELF authority or literal build identity differs')
    elf_offset = struct.unpack_from('<Q', data, 0x40)[0]
    segments = struct.unpack_from('<Q', data, 0x58)[0]
    if not 0x88 <= elf_offset <= len(data) - 52 or data[elf_offset:elf_offset + 7] != b'\x7fELF\x01\x01\x01':
        raise ValueError('Native-lab SELF lacks its embedded little-endian ELF32 header')
    if struct.unpack_from('<H', data, elf_offset + 18)[0] != 40:
        raise ValueError('Native-lab embedded executable is not ARM')
    phentsize, count = struct.unpack_from('<HH', data, elf_offset + 42)
    if phentsize != 32 or not 1 <= count <= 16 or not 0x88 <= segments <= len(data) - count * 32:
        raise ValueError('Native-lab SELF segment table is invalid')
    for index in range(count):
        offset, length, compression, encryption = struct.unpack_from('<QQQQ', data, segments + index * 32)
        if compression != 1 or encryption != 2 or offset > len(data) or length > len(data) - offset:
            raise ValueError('Native-lab SELF must contain bounded uncompressed, unencrypted segments')


def load_candidate(expected_sha256, *, root=None):
    """Validate the fixed local package/build report; return immutable payloads.

    Only declared compiled source pins are checked. Documentation metadata may
    be updated independently without relabeling a compiled native binary.
    """
    root = Path(root or Path(__file__).resolve().parents[1]).resolve()
    if not isinstance(expected_sha256, str) or not re.fullmatch('[0-9a-f]{64}', expected_sha256):
        raise ValueError('Pin the exact native-lab VPK SHA-256')
    base = root / 'dist/native-lab'
    report_raw = (base / 'build-report.json').read_bytes()
    report = json_object(report_raw)
    required = {'project', 'title_id', 'version', 'native_build_id', 'package', 'native_source_hashes'}
    if not required <= report.keys() or report['project'] != PROJECT or report['title_id'] != TITLE:
        raise ValueError('Native-lab build report identity differs')
    if (not isinstance(report['version'], str) or not re.fullmatch(r'[0-9]{2}\.[0-9]{2}', report['version'])
            or not isinstance(report['native_build_id'], str)
            or not re.fullmatch('[0-9a-f]{64}', report['native_build_id'])):
        raise ValueError('Native-lab build identity is invalid')
    info = report['package']
    if not isinstance(info, dict) or info.get('file') != 'native_lab.vpk':
        raise ValueError('Native-lab package report differs')
    with (base / 'native_lab.vpk').open('rb') as source:
        payload = source.read(MAX_FILE + 1)
    if (not 0 < len(payload) <= MAX_FILE or sha(payload) != expected_sha256
            or info.get('sha256') != expected_sha256 or type(info.get('bytes')) is not int
            or info['bytes'] != len(payload)):
        raise ValueError('Native-lab package differs from its exact pin')
    pins = report['native_source_hashes']
    if not isinstance(pins, dict) or not pins or len(pins) > 128:
        raise ValueError('Native-lab compiled source pins are unavailable')
    for relative, digest in pins.items():
        if (not isinstance(relative, str) or '\\' in relative or Path(relative).is_absolute()
                or '..' in relative.split('/') or not isinstance(digest, str)
                or not re.fullmatch('[0-9a-f]{64}', digest)):
            raise ValueError('Native-lab compiled source pin is invalid')
        path = (root / relative).resolve()
        if root not in path.parents or not path.is_file() or sha(path.read_bytes()) != digest:
            raise ValueError('Native-lab compiled source changed since the build')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bridge'))
    from ftp_staging import read_sfo
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        entries = archive.infolist()
        if (len(entries) != 7 or set(archive.namelist()) != set(FILES[:-1])
                or any(e.is_dir() or e.flag_bits & 1 or e.file_size <= 0 or e.file_size > MAX_FILE
                       or (e.external_attr >> 16) & 0o170000 == 0o120000 for e in entries)
                or sum(e.file_size for e in entries) > MAX_TOTAL - 0x430 or archive.testzip() is not None):
            raise ValueError('Native-lab package layout or bounds differ')
        files = tuple(archive.read(name) for name in FILES[:-1])
    validate_self(files[0], report['native_build_id'])
    sfo = read_sfo(files[1])
    if (sfo.get('TITLE_ID') != TITLE or sfo.get('APP_VER') != report['version']
            or sfo.get('CATEGORY') != 'gd' or type(sfo.get('PSP2_SYSTEM_VER')) is not int
            or sfo['PSP2_SYSTEM_VER'] > 0x03650000):
        raise ValueError('Native-lab SFO identity or firmware differs')
    from scripts.livearea_png import validate_livearea_png
    for data, size in zip(files[2:5], ((128, 128), (840, 500), (280, 158))):
        validate_livearea_png(data, size)
    template = ET.fromstring(files[5])
    if (template.tag != 'livearea' or template.attrib.get('style') != 'a1'
            or template.findtext('livearea-background/image') != 'bg.png'
            or template.findtext('gate/startup-image') != 'startup.png'):
        raise ValueError('Native-lab LiveArea template differs')
    files += (make_head(TITLE, len(payload)),)
    candidate = {'project': PROJECT, 'title_id': TITLE, 'version': report['version'],
                 'native_build_id': report['native_build_id'], 'package_sha256': expected_sha256,
                 'package_bytes': len(payload), 'build_report_sha256': sha(report_raw),
                 'files': [{'bytes': len(data), 'sha256': sha(data)} for data in files]}
    return candidate, files
