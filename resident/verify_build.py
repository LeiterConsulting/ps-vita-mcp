"""Bind the ARM module and host test logs to the exact resident prototype sources."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import struct

ROOT = Path(__file__).resolve().parents[1]
ACCEPTED = {}  # Fresh public checkouts have no private DevLoop/Quake release artifacts.


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def elf(data, expected_type):
    if data[:6] != b'\x7fELF\x01\x01' or struct.unpack_from('<HH', data, 16) != (expected_type, 40):
        raise ValueError('Expected a little-endian ELF32 ARM module')
    offset = struct.unpack_from('<I', data, 32)[0]
    size, count, string_index = struct.unpack_from('<HHH', data, 46)
    if size != 40 or not 0 < string_index < count or offset + size * count > len(data):
        raise ValueError('Invalid ELF section table')
    sections = [struct.unpack_from('<10I', data, offset + size * i) for i in range(count)]
    strings = sections[string_index]
    names = data[strings[4]:strings[4] + strings[5]]
    result = {}
    for section in sections:
        name = names[section[0]:].split(b'\0', 1)[0].decode('ascii')
        result[name] = section
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    if evidence.parent != (ROOT / 'evidence/resident').resolve():
        raise ValueError('Evidence must be a fresh resident build directory')
    native = ROOT / 'build/resident/native'
    elf_data = (native / 'vita_resident').read_bytes()
    sections = elf(elf_data, 2)
    velf_data = (native / 'vita_resident.velf').read_bytes()
    velf_sections = elf(velf_data, 0xfe04)
    section = velf_sections['.sceModuleInfo.rodata']
    module = velf_data[section[4]:section[4] + section[5]]
    if len(module) != 92 or struct.unpack_from('<H', module)[0] != 0 or module[2:4] != b'\x01\x00' or module[4:31].split(b'\0')[0] != b'vita_resident':
        raise ValueError('Module must identify the independent user plugin')
    if not all(struct.unpack_from('<II', module, 68)):
        raise ValueError('Module start/stop entries are required')
    self_data = (native / 'vita_resident.suprx').read_bytes()
    if self_data[:4] != b'SCE\0' or not 0 < len(self_data) < 256 * 1024:
        raise ValueError('Invalid plugin SELF size or magic')
    embedded = struct.unpack_from('<Q', self_data, 64)[0]
    if self_data[embedded:embedded + 6] != b'\x7fELF\x01\x01' or struct.unpack_from('<H', self_data, embedded + 18)[0] != 40:
        raise ValueError('Plugin SELF must contain the ARM ELF header')
    if (native / 'undefined-symbols.txt').read_text(encoding='utf-8').strip():
        raise ValueError('Unexpected unresolved ELF symbols')
    core = ['service.c', 'sha256.c', 'sha256.h', 'platform.h', 'platform_vita.c', 'pairing.c', 'pairing_json.c', 'pairing_io.c', 'pairing.h', 'CMakeLists.txt', 'exports.yml', 'files.c', 'files.h', 'files_platform.h', 'files_platform_vita.c',
            'launch_broker/core.c', 'launch_broker/launch_broker.h', 'launch_broker/http.c', 'launch_broker/http.h',
            'launch_broker/store.c', 'launch_broker/store.h', 'launch_broker/native_vita.c', 'launch_broker/native.h',
            'launch_broker/service.c', 'launch_broker/service.h',
            'native_install/service.c', 'native_install/service.h', 'native_install/platform.h', 'native_install/platform_vita.c', 'native_install/paths.h',
            'native_launch/native_launch.c', 'native_launch/native_launch.h',
            'keep_awake/policy.c', 'keep_awake/policy.h', 'keep_awake/service.c', 'keep_awake/service.h',
            'keep_awake/power_platform.h', 'keep_awake/power_platform_vita.c']
    build_id = hashlib.sha256(''.join(digest(ROOT / 'resident' / name) for name in core).encode('ascii')).hexdigest()
    if build_id.encode('ascii') not in elf_data:
        raise ValueError('Native build identifier differs from the source fingerprint')
    forbidden = [b'sceAppMgrDestroy', b'sceKernelLoadStartModule',
                 b'taiLoadStart', b'fixture-enable-launch', b'fixture-launch-success']
    if any(name in elf_data for name in forbidden):
        raise ValueError('Module contains a forbidden destroy/loader or host-fixture path')
    if b'sceAppMgrLaunchAppByUri' not in elf_data or b'psgm:play?titleid=VMCP00001' not in elf_data:
        raise ValueError('Fixed Lifecycle Lab launch adapter is missing')
    imports = sorted(name.removeprefix('.text.fstubs.') for name in velf_sections if name.startswith('.text.fstubs.'))
    if set(imports) != {'SceLibKernel', 'SceNet', 'SceNetCtl', 'SceSysmodule', 'SceThreadmgr', 'SceIofilemgr', 'ScePower', 'SceRtcUser', 'SceLibRng', 'SceAppMgr', 'SceAppMgrUser', 'ScePromoterUtil', 'SceProcessmgr'}:
        raise ValueError('Unexpected imports')
    preserved = {}
    for relative, expected in ACCEPTED.items():
        actual = digest(ROOT / relative)
        if actual != expected:
            raise ValueError('Previously accepted artifact changed: ' + relative)
        preserved[relative] = actual
    logs = {}
    for name in ['c-service-tests.log', 'mcp-tests.log', 'files-mcp-tests.log', 'ftp-tests.log', 'update-tests.log', 'native-lifecycle-pc-tests.log', 'keep-awake-pc-tests.log', 'native-build.log']:
        path = evidence / name
        if not path.exists() or not path.stat().st_size:
            raise ValueError('Missing build evidence: ' + name)
        logs[name] = digest(path)
    for name in ['vita_resident', 'vita_resident.velf', 'vita_resident.suprx', 'elf-layout.txt', 'undefined-symbols.txt', 'section-sizes.txt']:
        shutil.copy2(native / name, evidence / name)
    sources = {}
    for path in sorted((ROOT / 'resident').iterdir()):
        if path.is_file():
            sources[path.relative_to(ROOT).as_posix()] = digest(path)
    for relative in ['Build-Resident.ps1', 'toolchain.lock.json', 'bridge/ftp_staging.py', 'tests/ftp_fixture.py']:
        sources[relative] = digest(ROOT / relative)
    for directory in ['resident/launch_broker', 'resident/native_install', 'resident/native_launch', 'resident/keep_awake', 'lifecycle_lab']:
        for path in sorted((ROOT / directory).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                sources[path.relative_to(ROOT).as_posix()] = digest(path)
    for relative in ['workbench/native_package.py', 'workbench/native_lifecycle.py']:
        sources[relative] = digest(ROOT / relative)
    allocated = sum(section[5] for section in velf_sections.values() if section[2] & 2)
    report = {
        'built_utc': datetime.now(timezone.utc).isoformat(), 'version': '0.1.6',
        'toolchain': json.loads((ROOT / 'toolchain.lock.json').read_text(encoding='utf-8')),
        'plugin': {'file': 'vita_resident.suprx', 'bytes': len(self_data), 'sha256': hashlib.sha256(self_data).hexdigest(), 'build_id': build_id, 'elf_sha256': hashlib.sha256(elf_data).hexdigest(), 'velf_sha256': hashlib.sha256(velf_data).hexdigest(), 'module_attributes': 0, 'imports': imports, 'linked_allocated_section_bytes': allocated, 'worker_stack_bytes': 65536, 'keep_awake_worker_stack_bytes': 32768},
        'source_hashes': sources, 'test_log_hashes': logs, 'accepted_artifacts_preserved': preserved,
        'evidence_directory': str(evidence),
        'host_validation': 'Real C service with POSIX adapters, ASan/UBSan; real stdio MCP against simulated HTTP; guarded FTP staging against simulated FTP.',
        'launch_broker': {'enabled': False, 'native_submission': 'unconditionally refused', 'store_format': 1, 'store_capacity_records': 128, 'startup_dispatch': False},
        'managed_files': {'protocol': 1, 'read_only': True, 'root': 'ux0:data/vita-resident/inbox', 'page_entries': 32, 'max_offset': 1000, 'max_read_bytes': 16384, 'max_file_bytes': 8388608, 'snapshot': False},
        'native_lifecycle': {'protocol': 1, 'project': 'lifecycle_lab', 'title_id': 'VMCP00001', 'policy': 'idle_shell_only', 'file_count': 8, 'max_file_bytes': 8388608, 'max_total_bytes': 16777216, 'startup_dispatch': False, 'foreground_verified': False, 'protected_ui_verified': False},
        'keep_awake': {'protocol': 1, 'port': 17869, 'ttl_ms': [5000, 30000], 'max_duration_ms': 1800000, 'automatic_suspend_only': True, 'persistent': False, 'status_renews': False, 'display_settings_changed': False},
        'device_acceptance': 'pending: 0.1.6 normal boot, unchanged pairing/configuration, live lease expiry/end, long-transfer renewal, native job and automatic sleep; host evidence and ARM packaging do not establish hardware acceptance',
    }
    dist = ROOT / 'dist/resident'
    dist.mkdir(parents=True, exist_ok=True)
    shutil.copy2(native / 'vita_resident.suprx', dist / 'vita_resident.suprx')
    if digest(dist / 'vita_resident.suprx') != report['plugin']['sha256']:
        raise ValueError('Distribution copy mismatch')
    for path in [dist / 'build-report.json', evidence / 'build-report.json']:
        path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    (dist / 'SHA256SUMS.txt').write_text(report['plugin']['sha256'] + '  vita_resident.suprx\n', encoding='ascii')
    print(json.dumps({'plugin': report['plugin'], 'evidence': str(evidence), 'device_acceptance': 'pending'}, indent=2))


if __name__ == '__main__':
    main()
