"""Verify the independently built lab and publish a hash-bound local candidate."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import sys
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ('main.c', 'lab_core.c', 'lab_core.h', 'lab_platform.h',
           'lab_platform_vita.c', 'lab_server.c', 'lab_server.h', 'CMakeLists.txt')
FILES = ('eboot.bin', 'sce_sys/param.sfo', 'sce_sys/icon0.png',
         'sce_sys/livearea/contents/bg.png', 'sce_sys/livearea/contents/startup.png',
         'sce_sys/livearea/contents/template.xml', 'LICENSE')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify(build, version, variant, destination, evidence=None):
    if not re.fullmatch(r'[0-9]{2}\.[0-9]{2}', version) or variant not in (1, 2):
        raise ValueError('Choose a canonical version and variant 1 or 2')
    pins = {f'lifecycle_lab/{name}': sha((ROOT / 'lifecycle_lab' / name).read_bytes())
            for name in SOURCES}
    expected = sha((f'{version}:{variant}:' + ''.join(pins.values())).encode('ascii'))
    if (build / 'native-build-id.txt').read_text().strip() != expected:
        raise ValueError('Native compiled source identity differs; rebuild the lab')
    elf = (build / 'native_lab').read_bytes()
    marker = ('VITA_NATIVE_LIFECYCLE_LAB:' + expected).encode('ascii')
    if elf[:7] != b'\x7fELF\x01\x01\x01' or struct.unpack_from('<H', elf, 18)[0] != 40 or marker not in elf:
        raise ValueError('Expected an independently identified ARM32 little-endian ELF')
    payload = (build / 'native_lab.vpk').read_bytes()
    if not 0 < len(payload) <= 8 * 1024 * 1024:
        raise ValueError('Native lab package exceeds its declared bound')
    with zipfile.ZipFile(build / 'native_lab.vpk') as archive:
        if len(archive.infolist()) != 7 or set(archive.namelist()) != set(FILES) or archive.testzip():
            raise ValueError('Native lab package must contain exactly its seven public entries')
        executable = archive.read('eboot.bin')
        if executable != (build / 'native_lab.self').read_bytes():
            raise ValueError('Packaged SELF differs from the independently built executable')
        if (len(executable) < 0x88 or executable[:4] != b'SCE\0'
                or struct.unpack_from('<Q', executable, 0x38)[0] != 0x80
                or struct.unpack_from('<Q', executable, 0x80)[0] != 0x2f00000000000001
                or marker not in executable):
            raise ValueError('Expected uncompressed user SELF with exact native identity marker')
        hashes = {name: {'bytes': len(archive.read(name)), 'sha256': sha(archive.read(name))}
                  for name in FILES}
        sys.path.insert(0, str(ROOT / 'bridge'))
        sys.path.insert(0, str(ROOT))
        from ftp_staging import read_sfo
        from scripts.livearea_png import validate_livearea_png
        sfo = read_sfo(archive.read('sce_sys/param.sfo'))
        if (sfo.get('TITLE_ID') != 'VMCP00001' or sfo.get('APP_VER') != version
                or sfo.get('CATEGORY') != 'gd' or type(sfo.get('PSP2_SYSTEM_VER')) is not int
                or sfo['PSP2_SYSTEM_VER'] > 0x03650000):
            raise ValueError('Lab SFO identity, category or firmware requirement differs')
        for name, dimensions in zip(FILES[2:5], ((128, 128), (840, 500), (280, 158))):
            validate_livearea_png(archive.read(name), dimensions)
        template = ET.fromstring(archive.read(FILES[5]))
        if (template.tag != 'livearea' or template.attrib.get('style') != 'a1'
                or template.findtext('livearea-background/image') != 'bg.png'
                or template.findtext('gate/startup-image') != 'startup.png'
                or archive.read('LICENSE') != (ROOT / 'LICENSE').read_bytes()):
            raise ValueError('Lab original LiveArea template or public license differs')
    lock = json.loads((ROOT / 'toolchain.lock.json').read_text())
    report = {'project': 'lifecycle_lab', 'title_id': 'VMCP00001', 'version': version,
              'variant': variant, 'native_build_id': expected,
              'package': {'file': 'native_lab.vpk', 'bytes': len(payload), 'sha256': sha(payload)},
              'native_source_hashes': pins, 'package_entries': hashes,
              'toolchain_image': lock['image'],
              'toolchain_lock_sha256': sha((ROOT / 'toolchain.lock.json').read_bytes()),
              'elf_sha256': sha(elf),
              'self': {'authid': '0x2F00000000000001', 'compressed': False,
                       'native_identity_marker_verified': True},
              'created_utc': datetime.now(timezone.utc).isoformat(),
              'acceptance': {'host_core_and_http_tests': 'separate build evidence',
                             'native_build_and_package': 'passed',
                             'device_install_launch_exit_redeploy': 'pending'}}
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(build / 'native_lab.vpk', destination / 'native_lab.vpk')
    (destination / 'build-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    # Exercise the actual PC candidate validator after publication. It checks
    # SFO/firmware, original LiveArea PNGs/XML, source pins and constructs head.bin.
    sys.path.insert(0, str(ROOT))
    from workbench.native_package import load_candidate
    if destination.resolve() == (ROOT / 'dist/native-lab').resolve():
        candidate, files = load_candidate(report['package']['sha256'], root=ROOT)
        if len(files) != 8 or candidate['native_build_id'] != expected:
            raise ValueError('Independent PC normalization differs from the build')
    if evidence:
        evidence.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(destination / 'build-report.json', evidence / 'build-report.json')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, default=ROOT / 'build/native-lab')
    parser.add_argument('--version', default='01.00')
    parser.add_argument('--variant', type=int, default=1)
    parser.add_argument('--destination', type=Path, default=ROOT / 'dist/native-lab')
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args()
    result = verify(args.build, args.version, args.variant, args.destination, args.evidence)
    print(json.dumps({'native_build_id': result['native_build_id'], 'package': result['package'],
                      'device_acceptance': 'pending'}, indent=2))


if __name__ == '__main__':
    main()
