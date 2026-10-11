"""Build a disabled, one-shot boot experiment against the unchanged Control pair."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'resident'))
from verify_build import elf
from inspector.verify_build import authority, exports
sys.path.insert(0, str(ROOT))
from resident.control.verify_build import CORE


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    return sha(path.read_bytes())


def matched_control():
    report = json.loads((ROOT / 'dist/control/build-report.json').read_text(encoding='utf-8'))
    identity = sha(''.join(digest(ROOT / 'resident/control' / name) for name in CORE).encode('ascii'))
    if report['version'] != '0.3.4' or report['build_id'] != identity:
        raise ValueError('Build the current Control sources before Autostart')
    for name in ('vita_control_kernel', 'vita_control'):
        item = report['modules'][name]
        path = ROOT / 'dist/control' / item['file']
        if digest(path) != item['sha256'] or path.stat().st_size != item['bytes']:
            raise ValueError('Matched Control artifact differs: ' + name)
    if not (ROOT / 'build/resident/control/libvita_control_kernel_stub.a').is_file():
        raise ValueError('Generated Control syscall stubs are missing; run Build-Control.ps1')
    return report


def run(command, logfile):
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=600)
    logfile.write_text(result.stdout + result.stderr, encoding='utf-8')
    if result.returncode:
        print((result.stdout + result.stderr)[-5000:])
        raise RuntimeError('Build/check failed; see ' + str(logfile))


def main():
    control = matched_control()
    setup = 'setup-' + uuid.uuid4().hex
    module_root = 'ux0:data/vita-autostart/' + setup + '/'
    evidence = ROOT / 'evidence/autonomy' / ('build-' + setup)
    evidence.mkdir(parents=True, exist_ok=False)
    image = json.loads((ROOT / 'toolchain.lock.json').read_text(encoding='utf-8'))['image']
    docker = ['docker', 'run', '--rm', '--network', 'none', '--mount',
              f'type=bind,source={ROOT},target=/workspace', image]
    run(docker + ['sh', 'resident/autostart/test_host.sh'], evidence / 'host-tests.log')
    definitions = [
        '-DCONTROL_BUILD_ID=' + control['build_id'],
        '-DCONTROL_KERNEL_SHA256=' + control['modules']['vita_control_kernel']['sha256'],
        '-DCONTROL_SERVICE_SHA256=' + control['modules']['vita_control']['sha256'],
        '-DCONTROL_STUB_DIR=/workspace/build/resident/control',
        '-DCONTROL_MODULE_ROOT=' + module_root,
    ]
    run(docker + ['cmake', '-S', 'resident/autostart', '-B', 'build/autostart', '-G', 'Ninja',
                  '-DCMAKE_BUILD_TYPE=Release', *definitions], evidence / 'configure.log')
    run(docker + ['cmake', '--build', 'build/autostart'], evidence / 'native-build.log')
    run(docker + ['sh', '-c',
        'for mod in vita_autostart autostart_shell_probe; do '
        'arm-vita-eabi-nm -u build/autostart/$mod > build/autostart/$mod-undefined.txt; '
        'arm-vita-eabi-readelf -hlSW build/autostart/$mod.velf > build/autostart/$mod-layout.txt; done'],
        evidence / 'layout.log')
    native = ROOT / 'build/autostart'
    dist = ROOT / 'dist/autostart'
    dist.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    expected_imports = {
        'vita_autostart': {'SceAppMgr', 'SceAppMgrUser', 'SceIofilemgr', 'SceLibKernel', 'SceThreadmgr', 'taihenUnsafe'},
        'autostart_shell_probe': {'SceIofilemgr', 'SceLibKernel', 'SceThreadmgr', 'VitaControlKernel'},
    }
    boot_binary = (native / 'vita_autostart').read_bytes()
    probe_sha = digest(native / 'autostart_shell_probe.suprx')
    header = (native / 'probe_hash.h').read_text(encoding='ascii').strip()
    if header != '#define AO_PROBE_SHA256 "' + probe_sha + '"':
        raise ValueError('Generated probe hash differs from the built SELF')
    for value in (control['build_id'], module_root, probe_sha,
                  control['modules']['vita_control_kernel']['sha256'],
                  control['modules']['vita_control']['sha256']):
        if value.encode('ascii') not in boot_binary:
            raise ValueError('Boot binary is missing an exact artifact/path pin')
    for name in ('vita_autostart', 'autostart_shell_probe'):
        binary = (native / name).read_bytes()
        elf(binary, 2)
        data = (native / (name + '.velf')).read_bytes()
        sections = elf(data, 0xfe04)
        info = sections['.sceModuleInfo.rodata']
        module = data[info[4]:info[4] + info[5]]
        if (len(module) != 92 or struct.unpack_from('<H', module)[0] != 0
                or module[2:4] != b'\x01\x00' or not all(struct.unpack_from('<II', module, 68))
                or module[4:31].split(b'\0')[0] != name.encode('ascii')):
            raise ValueError('Unexpected autostart module identity/lifecycle')
        if (native / (name + '-undefined.txt')).read_text(encoding='utf-8').strip():
            raise ValueError('Unresolved native imports')
        payload = (native / (name + '.suprx')).read_bytes()
        if not 0 < len(payload) < 256 * 1024 or authority(payload) != 0x2f00000000000001:
            raise ValueError('Expected bounded unsafe user SELF')
        imports = sorted(key.removeprefix('.text.fstubs.') for key in sections if key.startswith('.text.fstubs.'))
        if set(imports) != expected_imports[name]:
            raise ValueError('Unexpected native import set: ' + name + ' ' + str(imports))
        if control['build_id'].encode('ascii') not in binary:
            raise ValueError('Missing exact native/module-path pins')
        exported = exports(data, sections)
        if len(exported) != 1 or exported[0]['name'] != 'main' or exported[0]['flags'] != '8000':
            raise ValueError('Boot helpers must not export application syscalls')
        artifacts[name + '.suprx'] = {'bytes': len(payload), 'sha256': sha(payload), 'imports': imports}
        for suffix in ('', '.velf', '.suprx', '-undefined.txt', '-layout.txt'):
            shutil.copy2(native / (name + suffix), evidence / (name + suffix))
        shutil.copy2(native / (name + '.suprx'), dist / (name + '.suprx'))
    for name in ('vita_control_kernel', 'vita_control'):
        item = control['modules'][name]
        shutil.copy2(ROOT / 'dist/control' / item['file'], dist / item['file'])
        artifacts[item['file']] = {'bytes': item['bytes'], 'sha256': item['sha256']}
    sources = {p.relative_to(ROOT).as_posix(): digest(p)
               for p in sorted((ROOT / 'resident/autostart').iterdir()) if p.is_file()}
    for name in ('scripts/build_autostart.py', 'Build-Autostart.ps1', 'toolchain.lock.json',
                 'resident/verify_build.py', 'resident/inspector/verify_build.py',
                 'resident/control/verify_build.py', 'resident/stage.py', 'bridge/ftp_staging.py'):
        sources[name] = digest(ROOT / name)
    control_sources = {(ROOT / 'resident/control' / name).resolve().relative_to(ROOT).as_posix():
                       digest(ROOT / 'resident/control' / name) for name in CORE}
    for relative in sources | control_sources:
        archived = evidence / 'source' / relative
        archived.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, archived)
    shutil.copy2(native / 'probe_hash.h', evidence / 'probe_hash.h')
    report = {'built_utc': datetime.now(timezone.utc).isoformat(), 'version': '0.1.0',
              'mode': 'experimental one-shot only', 'setup': setup, 'module_root': module_root,
              'control_version': control['version'], 'control_build_id': control['build_id'],
              'artifacts': artifacts, 'source_hashes': sources, 'control_source_hashes': control_sources,
              'control_stub_sha256': digest(ROOT / 'build/resident/control/libvita_control_kernel_stub.a'),
              'generated_probe_sha256': probe_sha,
              'host_tests_sha256': digest(evidence / 'host-tests.log'),
              'native_build_sha256': digest(evidence / 'native-build.log'),
              'activation': 'disabled; staging, explicit normal reboot and clean guard required',
              'device_acceptance': 'pending; module submission does not prove a network service',
              'persistent_boot': 'not implemented; first one-shot trial must qualify the deferred load path',
              'evidence_directory': str(evidence)}
    for path in (dist / 'build-report.json', evidence / 'build-report.json'):
        path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('version', 'mode', 'module_root', 'control_build_id', 'artifacts', 'device_acceptance')}, indent=2))


if __name__ == '__main__':
    main()
