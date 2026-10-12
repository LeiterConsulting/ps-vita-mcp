"""Build source-bound prototypes for the single owned VMCP00001 development slot.

This module never contacts a Vita, changes boot configuration, loads Control,
or grants arbitrary-title installation. The existing native lifecycle adapter
can preview the exact candidate published by a successful build.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import posixpath
import re
import shutil
import struct
import subprocess
import sys
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TITLE = 'VMCP00001'
PORT = 17868
PROJECT_FILES = ('native-slot.json', 'app.c', 'app.h', 'app_sim.c', 'app_sim.h', 'test_app.c')
FRAMEWORK_FILES = ('app_slot/main.c', 'app_slot/app_api.h', 'app_slot/CMakeLists.txt',
                   'lifecycle_lab/lab_core.c', 'lifecycle_lab/lab_core.h',
                   'lifecycle_lab/lab_server.c', 'lifecycle_lab/lab_server.h',
                   'lifecycle_lab/lab_platform.h', 'lifecycle_lab/lab_platform_vita.c',
                   'lifecycle_lab/assets/icon0.png', 'lifecycle_lab/assets/bg.png',
                   'lifecycle_lab/assets/startup.png', 'lifecycle_lab/assets/template.xml',
                   'scripts/vita_native_slot.py', 'toolchain.lock.json', 'LICENSE')
MANIFEST_FIELDS = {'schema_version', 'route', 'module_api', 'name', 'display_name'}
LIMITATIONS = [
    'One replaceable VMCP00001 development slot; no arbitrary-title support.',
    'The slot replaces the previous Lab/prototype content; the pristine Lab sources are preserved.',
    'The authenticated Lab envelope retains paused=true; application callbacks run independently.',
    'Harness CRC and application self-test are separate; live selftest_passed includes sticky per-update state health.',
    'Application callbacks are native code without Lua instruction or memory containment.',
    'Compilation and host simulation checks do not qualify physical controls, graphics, sound or hardware timing.',
    'Build does not install or launch; use a fresh native lifecycle preview of the resulting exact package hash.'
]


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def _object(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate native-slot manifest field')
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON')))
    if not isinstance(value, dict):
        raise ValueError('Expected native-slot JSON object')
    return value


def _directory(project_directory, root, *, absent=False):
    root = Path(root).resolve()
    path = Path(project_directory)
    # Reject traversal before normalization, including an absolute input that
    # would happen to resolve back inside the repository.
    if any(part in ('.', '..') for part in path.parts):
        raise ValueError('Native-slot project traversal is not accepted')
    candidate = path if path.is_absolute() else root / path
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        raise ValueError('Native-slot project must be inside the repository') from None
    if not relative.parts or any(not re.fullmatch(r'[A-Za-z0-9_.-]+', part) for part in relative.parts):
        raise ValueError('Use safe ASCII repository-relative directory names')
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink() or current.exists() and current.resolve() != current.absolute():
            raise ValueError('Native-slot project may not cross a link or junction')
    resolved = candidate.resolve()
    if root not in resolved.parents:
        raise ValueError('Native-slot project escaped the repository')
    if absent and candidate.exists():
        raise FileExistsError('Native-slot scaffold requires an absent leaf directory')
    if not absent and not candidate.is_dir():
        raise ValueError('Native-slot project directory is unavailable')
    return root, candidate, relative.as_posix()


def scaffold(project_directory, *, name=None, display_name=None, root=ROOT):
    """Create a deterministic paddle prototype in a new repository leaf.

    Parents may exist. No existing file or directory is overwritten. A project
    consists of the six declared fixed files; version 1 does not accept custom
    build commands, extra asset paths or arbitrary dependency declarations.
    """
    root, path, relative = _directory(project_directory, root, absent=True)
    name = name or path.name
    display_name = display_name or name.replace('-', ' ').replace('_', ' ').title()
    manifest = {'schema_version': 1, 'route': 'native-slot', 'module_api': 1,
                'name': name, 'display_name': display_name}
    _manifest(manifest)
    template = root / 'app_slot/templates'
    contents = {name: (template / name).read_bytes() for name in PROJECT_FILES if name != 'native-slot.json'}
    contents['native-slot.json'] = (json.dumps(manifest, indent=2) + '\n').encode('utf-8')
    path.mkdir(parents=True, exist_ok=False)
    for filename, payload in contents.items():
        with (path / filename).open('xb') as output:
            output.write(payload)
    return inspect(relative, root=root)


def _manifest(value):
    if (set(value) != MANIFEST_FIELDS or type(value.get('schema_version')) is not int
            or value['schema_version'] != 1 or value.get('route') != 'native-slot'
            or type(value.get('module_api')) is not int or value['module_api'] != 1
            or not isinstance(value.get('name'), str)
            or not re.fullmatch(r'[a-z][a-z0-9_-]{0,31}', value['name'])
            or not isinstance(value.get('display_name'), str)
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _-]{0,47}', value['display_name'])):
        raise ValueError('Unsupported native-slot manifest identity, API or fields')
    return value


def inspect(project_directory, *, root=ROOT):
    """Validate one fixed-layout module and report its exact source pins."""
    root, path, relative = _directory(project_directory, root)
    if set(item.name for item in path.iterdir()) != set(PROJECT_FILES):
        raise ValueError('Native-slot projects require exactly the six declared files')
    pins = {}
    for name in PROJECT_FILES:
        item = path / name
        if item.is_symlink() or not item.is_file() or item.resolve() != item.absolute():
            raise ValueError('Native-slot sources must be ordinary repository files')
        raw = item.read_bytes()
        if not 0 < len(raw) <= 128 * 1024 or b'\0' in raw:
            raise ValueError('Native-slot source exceeds its text bounds')
        raw.decode('utf-8')
        pins[f'{relative}/{name}'] = _sha(raw)
    manifest = _manifest(_object((path / 'native-slot.json').read_bytes()))
    return {'route': 'native-slot', 'title_id': TITLE, 'port': PORT,
            'project_directory': relative, 'application': manifest,
            'module_sha256': _sha(_canonical(pins)), 'source_files': list(pins),
            'source_sha256': pins, 'limitations': list(LIMITATIONS)}


def _image(root):
    value = _object((root / 'toolchain.lock.json').read_bytes())
    image = value.get('image')
    if not isinstance(image, str) or not re.fullmatch(r'vitasdk/vitasdk@sha256:[0-9a-f]{64}', image):
        raise ValueError('Native-slot builds require the pinned VitaSDK digest')
    return image


def _run(root, image, arguments, log, *, timeout_s=180):
    container = 'vita-native-slot-' + uuid.uuid4().hex
    command = ['docker', 'run', '--rm', '--name', container, '--network', 'none', '--mount',
               f'type=bind,source={root},target=/workspace', '--workdir', '/workspace',
               image, *arguments]
    # Every tool invocation is an argv list with shell=False. Even a failed
    # developer build retains its output, without executing project strings.
    with log.open('wb') as output:
        output.write(f'Owned native-slot build container: {container}\n'.encode('ascii'))
        output.flush()
        try:
            result = subprocess.run(command, cwd=root, stdout=output, stderr=subprocess.STDOUT,
                                    shell=False, check=False, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            output.write(b'\nNative-slot command timed out; removing its uniquely owned container.\n')
            output.flush()
            cleanup = False
            try:
                removed = subprocess.run(['docker', 'rm', '--force', container], cwd=root,
                                         stdout=output, stderr=subprocess.STDOUT, shell=False,
                                         check=False, timeout=15)
                cleanup = removed.returncode == 0
            except (subprocess.TimeoutExpired, OSError):
                output.write(b'\nOwned-container cleanup did not complete.\n')
            raise RuntimeError(f'Native-slot command timed out; owned-container cleanup '
                               f'{"confirmed" if cleanup else "unconfirmed"}; inspect {log.name}') from None
    if result.returncode:
        raise RuntimeError(f'Native-slot command failed; inspect {log.name}')


def _evidence(root):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = root / 'evidence/native-slot' / (stamp + '-' + uuid.uuid4().hex)
    folder.mkdir(parents=True, exist_ok=False)
    return folder


def _framework_pins(root):
    pins = {}
    for relative in FRAMEWORK_FILES:
        path = root / relative
        if path.is_symlink() or not path.is_file() or path.resolve() != path.absolute():
            raise ValueError('Native-slot framework must be ordinary repository files')
        pins[relative] = _sha(path.read_bytes())
    return pins


def _compiler_snapshot(root, pins, destination):
    """Expose only declared pinned inputs to the offline compiler container.

    GCC dependency records do not track assembler .incbin/.include directives.
    The original repository is therefore never mounted into these containers.
    Host tests and native compilation receive independent fresh snapshots so
    test-generated files cannot become implicit native application inputs.
    """
    destination.mkdir(parents=True, exist_ok=False)
    _verify_source_pins(root, pins)
    for relative in pins:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, target)
    _verify_source_pins(destination, pins)
    _verify_source_pins(root, pins)
    return destination


def _make_dependencies(raw):
    """Read actual GCC dependency output, including ordinary Make escapes.

    Compiler paths inside the container are POSIX paths. A backslash quotes one
    character, or joins a continued physical line. Targets before the first
    unescaped colon are ignored; generated phony rules are not requested.
    """
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8')
    target = True
    escaped = False
    token = ''
    values = []
    for character in raw:
        if escaped:
            if character not in ('\n', '\r'):
                token += character
            escaped = False
            continue
        if character == '\\':
            escaped = True
        elif target:
            if character == ':':
                target = False
                token = ''
        elif character.isspace():
            if token:
                values.append(token)
                token = ''
        else:
            token += character
    if escaped or target:
        raise ValueError('Malformed compiler dependency output')
    if token:
        values.append(token)
    if not values:
        raise ValueError('Compiler dependency output is empty')
    return values


def _ninja_dependencies(raw):
    """Read Ninja's actual stored dependencies, not a source-text include scan."""
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8')
    values = [line.strip() for line in raw.splitlines() if line.startswith('    ') and line.strip()]
    if not values:
        raise ValueError('Native compiler dependencies are unavailable')
    return values


def _verify_dependencies(dependencies, pins, required, *, cwd='/workspace'):
    repository = set()
    system = set()
    for entry in dependencies:
        if not isinstance(entry, str) or not entry or '\0' in entry or '\n' in entry or '\r' in entry:
            raise ValueError('Invalid compiler dependency path')
        path = posixpath.normpath(entry if entry.startswith('/') else posixpath.join(cwd, entry))
        if path == '/workspace' or path.startswith('/workspace/'):
            relative = path.removeprefix('/workspace/')
            if relative not in pins:
                raise ValueError('Undeclared native-slot repository dependency: ' + relative)
            repository.add(relative)
        else:
            # Other container files belong to the digest-pinned offline image.
            system.add(path)
    if not set(required) <= repository:
        raise ValueError('Compiler dependencies do not cover every declared translation unit')
    return {'verified': True, 'repository_files': sorted(repository),
            'repository_dependency_hashes': {name: pins[name] for name in sorted(repository)},
            'system_dependency_count': len(system), 'system_policy': 'digest-pinned offline toolchain image',
            'undeclared_repository_dependencies': []}


def check(project_directory, *, root=ROOT, evidence=None):
    """Run the module's actual deterministic host simulation under sanitizers.

    This has no network/device effects. Native application callbacks can be
    replaced by the developer; only app_sim.c/test_app.c are host compiled.
    """
    root = Path(root).resolve()
    info = inspect(project_directory, root=root)
    folder = Path(evidence) if evidence is not None else _evidence(root)
    folder.mkdir(parents=True, exist_ok=True)
    relative = info['project_directory']
    image = _image(root)
    pins = {**info['source_sha256'], **_framework_pins(root)}
    config = _config(root, info['application'])
    pins[config] = _sha((root / config).read_bytes())
    compiler_root = _compiler_snapshot(root, pins, folder / 'host-compiler-root')
    test_directory = compiler_root / 'build/native-slot-host' / info['module_sha256']
    test_directory.mkdir(parents=True, exist_ok=True)
    binary = test_directory.relative_to(compiler_root).as_posix() + '/app-tests'
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-pedantic', '-g',
             '-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    dependencies = []
    objects = []
    dep_hashes = {}
    for name in ('app_sim', 'test_app'):
        base = test_directory.relative_to(compiler_root).as_posix() + '/' + name
        dep = base + '.d'
        obj = base + '.o'
        _run(compiler_root, image, ['cc', *flags, '-MMD', '-MF', dep, '-c', f'{relative}/{name}.c', '-o', obj],
             folder / f'application-host-{name}-build.log')
        raw = (compiler_root / dep).read_bytes()
        dependencies += _make_dependencies(raw)
        dep_hashes[name] = _sha(raw)
        shutil.copyfile(compiler_root / dep, folder / f'application-host-{name}.d')
        objects.append(obj)
    observed = _verify_dependencies(dependencies, pins,
                                    (f'{relative}/app_sim.c', f'{relative}/test_app.c'))
    observed['compiler_dependency_sha256'] = dep_hashes
    # No generated application test binary runs until its actual compiler
    # dependencies are declared and still match the reviewed source snapshot.
    _verify_source_pins(root, pins)
    _verify_source_pins(compiler_root, pins)
    _run(compiler_root, image, ['cc', *flags, *objects, '-lm', '-o', binary], folder / 'application-host-build.log')
    _run(compiler_root, image, [binary], folder / 'application-host-tests.log')
    _verify_source_pins(root, pins)
    _verify_source_pins(compiler_root, pins)
    report = {'route': 'native-slot', 'result': 'passed', 'module_sha256': info['module_sha256'],
              'source_sha256': info['source_sha256'], 'compiled_source_sha256': pins,
              'dependencies_verified': True, 'dependency_report': observed, 'evidence_directory': str(folder),
              'compiler_input_isolation': 'only declared pinned repository files; original repository not mounted',
              'compiler_snapshot': str(compiler_root),
              'acceptance': 'deterministic host simulation; physical inputs and device runtime pending'}
    (folder / 'host-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def _config(root, application):
    payload = ('/* Immutable generated native-slot configuration, API 1. */\n'
               f'#define APP_SLOT_NAME "{application["display_name"]}"\n'
               f'#define APP_SLOT_SLUG "{application["name"]}"\n'
               '#define APP_SLOT_API 1\n').encode('ascii')
    directory = root / '.devloop-private/native-slot/config' / _sha(payload)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'app_slot_config.h'
    if path.exists():
        if path.is_symlink() or path.read_bytes() != payload:
            raise ValueError('Immutable native-slot configuration was modified')
    else:
        with path.open('xb') as output:
            output.write(payload)
    return path.relative_to(root).as_posix()


def _verify_source_pins(root, pins):
    for relative, digest in pins.items():
        path = root / relative
        if not path.is_file() or path.is_symlink() or _sha(path.read_bytes()) != digest:
            raise ValueError('Native-slot compiled sources changed during the build')


def _publish(root, candidate_root, expected_sha, backup, *, validator=None):
    if validator is None:
        from workbench.native_package import load_candidate
        validator = load_candidate
    # Normalize and validate the isolated candidate BEFORE touching dist.
    candidate, files = validator(expected_sha, root=candidate_root)
    if len(files) != 8:
        raise ValueError('Native-slot normalized installer layout differs')
    source = candidate_root / 'dist/native-lab'
    destination = root / 'dist/native-lab'
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup.parent.mkdir(parents=True, exist_ok=True)
    moved = False
    if destination.exists():
        destination.rename(backup)
        moved = True
    try:
        source.rename(destination)
        published, _ = validator(expected_sha, root=root)
        if published != candidate:
            raise ValueError('Published native-slot candidate differs from validated snapshot')
    except Exception:
        if destination.exists():
            destination.rename(backup.parent / 'failed-candidate')
        if moved:
            backup.rename(destination)
        raise
    return candidate, str(backup) if moved else None


def build(project_directory, version='01.02', *, root=ROOT):
    """Host-check, compile and atomically publish a fixed-slot native candidate.

    Returns the complete source-bound build report. Prior candidate directories
    are retained as private rollback evidence. Device acceptance is pending.
    """
    if not isinstance(version, str) or not re.fullmatch(r'[0-9]{2}\.[0-9]{2}', version):
        raise ValueError('Choose a canonical Vita version NN.NN')
    root = Path(root).resolve()
    info = inspect(project_directory, root=root)
    folder = _evidence(root)
    host = check(info['project_directory'], root=root, evidence=folder)
    config = _config(root, info['application'])
    pins = {**info['source_sha256'], **_framework_pins(root)}
    pins[config] = _sha((root / config).read_bytes())
    if pins != host['compiled_source_sha256']:
        raise ValueError('Native-slot inputs changed after host verification')
    fingerprint = {'route': 'native-slot', 'module_api': 1, 'version': version, 'source_sha256': pins}
    build_id = _sha(_canonical(fingerprint))
    build_relative = f'build/native-slot/{build_id}'
    compiler_root = _compiler_snapshot(root, pins, folder / 'native-compiler-root')
    build_directory = compiler_root / build_relative
    image = _image(root)
    _run(compiler_root, image, ['cmake', '-S', 'app_slot', '-B', build_relative, '-G', 'Ninja',
                       '-DCMAKE_BUILD_TYPE=Release', f'-DSLOT_PROJECT={info["project_directory"]}',
                       f'-DSLOT_CONFIG={Path(config).parent.as_posix()}',
                       f'-DLAB_VERSION={version}', f'-DLAB_BUILD_ID={build_id}'], folder / 'configure.log')
    _run(compiler_root, image, ['cmake', '--build', build_relative, '--target', 'native_lab'],
         folder / 'native-build.log', timeout_s=300)
    _run(compiler_root, image, ['ninja', '-C', build_relative, '-t', 'deps'], folder / 'native-compiler-dependencies.log')
    dependency_raw = (folder / 'native-compiler-dependencies.log').read_bytes()
    compiled = ('app_slot/main.c', f'{info["project_directory"]}/app.c',
                f'{info["project_directory"]}/app_sim.c', 'lifecycle_lab/lab_core.c',
                'lifecycle_lab/lab_server.c', 'lifecycle_lab/lab_platform_vita.c')
    native_dependencies = _verify_dependencies(_ninja_dependencies(dependency_raw), pins, compiled,
                                                cwd='/workspace/' + build_relative)
    native_dependencies['compiler_dependency_sha256'] = _sha(dependency_raw)
    _verify_source_pins(root, pins)
    _verify_source_pins(compiler_root, pins)
    _run(compiler_root, image, ['cmake', '--build', build_relative, '--target', 'native_lab.vpk'],
         folder / 'native-package.log', timeout_s=300)
    _run(compiler_root, image, ['arm-vita-eabi-readelf', '-hlSW', f'{build_relative}/native_lab.velf'], folder / 'elf-layout.log')
    _run(compiler_root, image, ['arm-vita-eabi-nm', '-u', f'{build_relative}/native_lab'], folder / 'undefined-symbols.log')
    _verify_source_pins(root, pins)
    _verify_source_pins(compiler_root, pins)
    elf = (build_directory / 'native_lab').read_bytes()
    marker = ('VITA_NATIVE_LIFECYCLE_LAB:' + build_id).encode('ascii')
    if (len(elf) < 52 or elf[:7] != b'\x7fELF\x01\x01\x01'
            or struct.unpack_from('<H', elf, 18)[0] != 40 or marker not in elf):
        raise ValueError('Native-slot compiled ARM identity differs')
    payload = (build_directory / 'native_lab.vpk').read_bytes()
    from workbench.native_package import FILES, MAX_FILE
    with zipfile.ZipFile(build_directory / 'native_lab.vpk') as archive:
        if archive.read('eboot.bin') != (build_directory / 'native_lab.self').read_bytes():
            raise ValueError('Native-slot packaged SELF differs from compiled executable')
        if (set(archive.namelist()) != set(FILES[:-1]) or len(archive.infolist()) != 7
                or archive.testzip() is not None):
            raise ValueError('Native-slot VPK layout differs')
        entries = {name: {'bytes': len(archive.read(name)), 'sha256': _sha(archive.read(name))} for name in FILES[:-1]}
    if not 0 < len(payload) <= MAX_FILE:
        raise ValueError('Native-slot package exceeds fixed-adapter bounds')
    report = {'project': 'lifecycle_lab', 'title_id': TITLE, 'route': 'native-slot',
              'version': version, 'variant': 1, 'native_build_id': build_id,
              'application': info['application'], 'module_sha256': info['module_sha256'],
              'project_directory': info['project_directory'], 'module_api': 1,
              'package': {'file': 'native_lab.vpk', 'bytes': len(payload), 'sha256': _sha(payload)},
              'native_source_hashes': pins, 'native_fingerprint': fingerprint,
              'package_entries': entries, 'toolchain_image': image,
              'toolchain_lock_sha256': pins['toolchain.lock.json'], 'elf_sha256': _sha(elf),
              'self': {'authid': '0x2F00000000000001', 'compressed': False, 'native_identity_marker_verified': True},
              'created_utc': datetime.now(timezone.utc).isoformat(),
              'harness': {'project': 'lifecycle_lab', 'title_id': TITLE, 'port': PORT,
                          'status_schema': 'unchanged Lab protocol 1', 'checksum': 'independent CRC32 0xa2912082',
                          'selftest_passed': 'harness CRC AND app_init AND app_selftest AND sticky app_update health',
                          'paused': 'harness envelope only; application callbacks run independently'},
              'acceptance': {'host_application_simulation': 'passed', 'native_build_and_package': 'passed',
                             'device_install_launch_exit_redeploy': 'pending',
                             'device_application_behavior': 'pending', 'physical_input': 'pending'},
              'dependencies_verified': True,
              'compiler_dependencies': {'host': host['dependency_report'], 'native': native_dependencies},
              'compiler_input_isolation': {'verified': True,
                  'repository_inputs': 'only declared hash-pinned files',
                  'original_repository_mounted': False,
                  'host_and_native_snapshots': 'independent; native snapshot excludes host test outputs'},
              'host_evidence': {'directory': str(folder.relative_to(root)),
                                'report_sha256': _sha((folder / 'host-report.json').read_bytes())},
              'limitations': list(LIMITATIONS)}
    # An isolated snapshot lets the unmodified existing package adapter inspect
    # every real source pin and package before publication. Snapshots/old files
    # remain local ignored evidence; no phone source or token is included.
    candidate_root = folder / 'candidate-root'
    candidate_directory = candidate_root / 'dist/native-lab'
    candidate_directory.mkdir(parents=True)
    for relative in pins:
        target = candidate_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, target)
    (candidate_directory / 'native_lab.vpk').write_bytes(payload)
    raw_report = (json.dumps(report, indent=2) + '\n').encode('utf-8')
    (candidate_directory / 'build-report.json').write_bytes(raw_report)
    _verify_source_pins(root, pins)
    from workbench.session import exclusive
    backup = root / '.devloop-private/native-slot-candidate-backups' / folder.name / 'previous-native-lab'
    with exclusive():
        _verify_source_pins(root, pins)
        candidate, retained = _publish(root, candidate_root, report['package']['sha256'], backup)
    (folder / 'build-report.json').write_bytes(raw_report)
    publication = {'result': 'passed', 'candidate': candidate, 'prior_candidate_backup': retained,
                   'host_result': host['result'], 'device_mutations': 0, 'evidence_directory': str(folder)}
    (folder / 'publication.json').write_text(json.dumps(publication, indent=2) + '\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('scaffold', 'inspect', 'check', 'build'):
        item = commands.add_parser(name)
        item.add_argument('project_directory')
        if name == 'scaffold':
            item.add_argument('--name')
            item.add_argument('--display-name')
        if name == 'build':
            item.add_argument('--version', default='01.02')
    args = parser.parse_args()
    if args.command == 'scaffold':
        result = scaffold(args.project_directory, name=args.name, display_name=args.display_name)
    elif args.command == 'build':
        result = build(args.project_directory, args.version)
    else:
        result = globals()[args.command](args.project_directory)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    main()
