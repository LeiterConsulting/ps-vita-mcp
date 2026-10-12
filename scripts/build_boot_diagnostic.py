"""Build an isolated, one-shot Shell resource diagnostic; never contacts a Vita."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'resident'))
from verify_build import elf
from inspector.verify_build import authority, exports


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, log):
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                            encoding='utf-8', timeout=600)
    log.write_text(result.stdout + result.stderr, encoding='utf-8')
    if result.returncode:
        print((result.stdout + result.stderr)[-4000:])
        raise RuntimeError('Diagnostic build failed; see ' + str(log))


def main():
    sources = sorted(path for path in (ROOT / 'resident/boot_diagnostic').iterdir()
                     if path.is_file())
    sources += [ROOT / name for name in ('scripts/build_boot_diagnostic.py',
                'toolchain.lock.json', 'resident/verify_build.py',
                'resident/inspector/verify_build.py')]
    hashes = {path.relative_to(ROOT).as_posix(): digest(path) for path in sources}
    manifest = ''.join(name + ':' + hashes[name] + '\n' for name in sorted(hashes))
    identity = hashlib.sha256(manifest.encode('ascii')).hexdigest()
    setup = 'setup-' + uuid.uuid4().hex
    native_root = 'ux0:data/vita-boot-diagnostic/' + setup + '/'
    evidence = ROOT / 'evidence/autonomy' / ('diagnostic-build-' + setup)
    evidence.mkdir(parents=True, exist_ok=False)
    image = json.loads((ROOT / 'toolchain.lock.json').read_text())['image']
    docker = ['docker', 'run', '--rm', '--network', 'none', '--mount',
              f'type=bind,source={ROOT},target=/workspace', image]
    run(docker + ['sh', 'resident/boot_diagnostic/test_host.sh'], evidence / 'host-tests.log')
    run(docker + ['cmake', '-S', 'resident/boot_diagnostic', '-B', 'build/boot-diagnostic',
                  '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
                  '-DDIAGNOSTIC_BUILD_ID=' + identity,
                  '-DDIAGNOSTIC_MODULE_ROOT=' + native_root], evidence / 'configure.log')
    run(docker + ['cmake', '--build', 'build/boot-diagnostic'], evidence / 'native-build.log')
    native = ROOT / 'build/boot-diagnostic'
    name = 'vita_boot_diagnostic'
    run(docker + ['vita-elf-create', '-e', 'resident/boot_diagnostic/plugin.yml',
                  'build/boot-diagnostic/' + name,
                  'build/boot-diagnostic/chain.velf'], evidence / 'chain-velf.log')
    run(docker + ['vita-make-fself', '-c', 'build/boot-diagnostic/chain.velf',
                  'build/boot-diagnostic/chain.suprx'], evidence / 'chain-self.log')
    assert (native / 'chain.velf').read_bytes() == (native / (name + '.velf')).read_bytes()
    assert (native / 'chain.suprx').read_bytes() == (native / (name + '.suprx')).read_bytes()
    run(docker + ['sh', '-c',
        'arm-vita-eabi-nm -u build/boot-diagnostic/vita_boot_diagnostic > '
        'build/boot-diagnostic/undefined.txt'], evidence / 'undefined.log')
    binary = (native / name).read_bytes()
    elf(binary, 2)
    assert identity.encode('ascii') in binary and native_root.encode('ascii') in binary
    assert not (native / 'undefined.txt').read_text().strip(), 'Unresolved ELF symbols'
    velf = (native / (name + '.velf')).read_bytes()
    sections = elf(velf, 0xfe04)
    entry = sections['.sceModuleInfo.rodata']
    module = velf[entry[4]:entry[4] + entry[5]]
    assert len(module) == 92 and struct.unpack_from('<H', module)[0] == 0
    assert module[2:4] == b'\x01\x00' and all(struct.unpack_from('<II', module, 68))
    assert module[4:31].split(b'\0')[0] == name.encode('ascii')
    imports = sorted(key.removeprefix('.text.fstubs.') for key in sections
                     if key.startswith('.text.fstubs.'))
    assert set(imports) <= {'SceLibKernel', 'SceThreadmgr', 'SceIofilemgr',
                            'SceAppMgr', 'SceAppMgrUser'}, imports
    assert not any('Control' in item or 'taihen' in item or 'Net' in item for item in imports)
    exported = exports(velf, sections)
    assert len(exported) == 1 and exported[0]['name'] == 'main' and exported[0]['flags'] == '8000'
    assert exported[0]['functions'] == 2 and exported[0]['variables'] == 1
    payload = native / (name + '.suprx')
    assert 0 < payload.stat().st_size <= 256 * 1024
    assert authority(payload.read_bytes()) == 0x2f00000000000001
    dist = ROOT / 'dist/boot-diagnostic'
    dist.mkdir(parents=True, exist_ok=True)
    shutil.copy2(payload, dist / payload.name)
    for suffix in ('', '.velf', '.suprx'):
        shutil.copy2(native / (name + suffix), evidence / (name + suffix))
    for path in sources:
        target = evidence / 'source' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    report = {'built_utc': datetime.now(timezone.utc).isoformat(), 'version': '0.1.0',
              'mode': 'isolated one-shot mutex/thread diagnostic; no Control or module loads',
              'setup': setup, 'module_root': native_root, 'build_id': identity,
              'source_hashes': hashes, 'manifest': manifest,
              'artifact': {'file': payload.name, 'bytes': payload.stat().st_size,
                           'sha256': digest(payload), 'imports': imports,
                           'elf_sha256': digest(native / name),
                           'velf_sha256': digest(native / (name + '.velf'))},
              'conversion_verification': 'pinned SDK repeats ELF-to-VELF-to-SELF; exact byte equality',
              'toolchain': image, 'device_acceptance': 'pending'}
    (dist / 'build-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'result': 'PASS native diagnostic build', 'build_id': identity,
                      'module_root': native_root, 'artifact': report['artifact']}, indent=2))


if __name__ == '__main__':
    main()
