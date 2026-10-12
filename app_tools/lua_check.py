"""Check app Lua through the actual shared sandbox, using host fixtures only.

``check(path, checks, frames=120, dt=1/60, inputs=None)`` never contacts a
device. ``inputs`` is an optional ordered list of frame-indexed controller
changes; omitted fields retain their prior values, initially neutral.
Build outputs and immutable per-check snapshots live under ignored ``build/``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
KNOWN_BUTTONS = 1 | 8 | 16 | 32 | 64 | 128 | 256 | 512 | 4096 | 8192 | 16384 | 32768
LIMITATIONS = [
    'Actual shared Lua/core code; controller, clock and rendering are host fixtures.',
    'No Vita installation, runtime identity, display, physical-input or timing acceptance.',
    'The Lua callback instruction hook is not a wall-clock deadline for every C routine.',
]


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _validate_checks(checks):
    if not isinstance(checks, list) or not 1 <= len(checks) <= 8:
        raise ValueError('Supply 1..8 app-specific metric checks')
    for item in checks:
        if (not isinstance(item, dict) or set(item) - {'metric', 'min', 'max', 'equals'} or
                not isinstance(item.get('metric'), str) or
                not re.fullmatch('[A-Za-z0-9_]{1,24}', item['metric']) or
                not set(item) & {'min', 'max', 'equals'} or
                any(not _number(value) for key, value in item.items() if key != 'metric') or
                ('min' in item and 'max' in item and item['min'] > item['max'])):
            raise ValueError('Each metric check needs a valid name and finite min, max or equals')
    return [dict(item) for item in checks]


def _trace(inputs, frames):
    if inputs is None:
        inputs = []
    if not isinstance(inputs, list) or len(inputs) > 3600:
        raise ValueError('inputs must be a list of at most 3600 frame-indexed controller changes')
    current = {'buttons': 0, 'lx': 128, 'ly': 128, 'rx': 128, 'ry': 128}
    result = []
    previous = -1
    for item in inputs:
        if (not isinstance(item, dict) or set(item) - {'frame', *current} or
                type(item.get('frame')) is not int or not previous < item['frame'] < frames or
                len(item) < 2):
            raise ValueError('Controller trace frames must be unique, increasing and within the check')
        for key, value in item.items():
            if key == 'frame':
                continue
            if type(value) is not int or value < 0 or (key != 'buttons' and value > 255):
                raise ValueError('Controller values must be integer button masks or 0..255 stick axes')
            if key == 'buttons' and value & ~KNOWN_BUTTONS:
                raise ValueError('Controller buttons contain unsupported bits')
            current[key] = value
        previous = item['frame']
        result.append({'frame': previous, **current})
    return result


def _source_pins(repo):
    paths = [repo / name for name in (
        'app_tools/lua_check.c', 'scripts/test_vita_app_lua.sh', 'toolchain.lock.json',
        'devloop/core.c', 'devloop/script_runtime.c', 'devloop/sha256.c',
        'tests/render_stub.c', 'common/physics.c', 'common/math_helpers.c')]
    paths += list((repo / 'devloop').glob('*.h'))
    paths += list((repo / 'common').glob('*.h'))
    paths += list((repo / 'third_party/lua-5.4.9/src').glob('*.c'))
    paths += list((repo / 'third_party/lua-5.4.9/src').glob('*.h'))
    if not (repo / 'third_party/lua-5.4.9/src/lapi.c').is_file():
        raise ValueError('The pinned vendored Lua sources are missing')
    return {path.relative_to(repo).as_posix(): _sha(path.read_bytes()) for path in sorted(set(paths))}


def _identity(pins, image):
    return _sha(json.dumps({'image': image, 'sources': pins}, sort_keys=True,
                           separators=(',', ':')).encode('utf-8'))


def _docker_run(docker, image, mounts, arguments, timeout):
    name = 'vita-app-lua-' + uuid.uuid4().hex
    command = [docker, 'run', '--rm', '--name', name, '--network', 'none',
               '--read-only', '--tmpfs', '/tmp:rw,nosuid', '--cap-drop', 'ALL',
               '--security-opt', 'no-new-privileges', '--workdir', '/workspace']
    if os.name == 'posix':
        # With all capabilities dropped, container root cannot bypass ordinary
        # Linux bind-mount ownership. Write outputs as their invoking host owner.
        command += ['--user', f'{os.getuid()}:{os.getgid()}']
    for source, target, readonly in mounts:
        if ',' in str(source):
            raise ValueError('Docker bind paths containing commas are unsupported')
        value = f'type=bind,source={source},target={target}'
        command += ['--mount', value + (',readonly' if readonly else '')]
    command += [image, *arguments]
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        # Killing the CLI alone can leave its container running. Remove only
        # this exact helper-owned randomly named container before reporting.
        subprocess.run([docker, 'rm', '--force', name], capture_output=True, timeout=15)
        raise


def _build(repo, docker, image, pins, identity):
    output = repo / 'build/host/vita-app-lua' / identity
    output.mkdir(parents=True, exist_ok=True)
    binary = output / 'test_lua_check'
    marker = output / 'build.json'
    if marker.is_file() and binary.is_file():
        saved = json.loads(marker.read_text(encoding='utf-8'))
        if saved.get('identity') == identity and saved.get('binary_sha256') == _sha(binary.read_bytes()):
            return output, saved, True
    lock = output / 'build.lock'
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise RuntimeError('This exact sandbox build is already in progress; inspect its build.lock') from error
    os.close(descriptor)
    try:
        built = _docker_run(docker, image, [(repo, '/workspace', True), (output, '/output', False)],
                            ['sh', 'scripts/test_vita_app_lua.sh', '/output'], 180)
        (output / 'build.log').write_text(built.stdout + built.stderr, encoding='utf-8')
        if built.returncode or not binary.is_file():
            raise RuntimeError('Shared Lua sandbox build failed; inspect build.log')
        if _source_pins(repo) != pins:
            raise RuntimeError('Shared sandbox sources changed during the build; no cache published')
        saved = {'identity': identity, 'image': image, 'source_sha256': pins,
                 'binary_sha256': _sha(binary.read_bytes())}
        temporary = output / ('build-' + uuid.uuid4().hex + '.json')
        _json(temporary, saved)
        temporary.replace(marker)
        return output, saved, False
    finally:
        lock.unlink()


def _predicates(metrics, checks):
    result = []
    for item in checks:
        value = metrics.get(item['metric'])
        passed = _number(value)
        if passed:
            passed = (('min' not in item or value >= item['min']) and
                      ('max' not in item or value <= item['max']) and
                      ('equals' not in item or value == item['equals']))
        result.append({**item, 'observed': value, 'passed': bool(passed)})
    return result


def check(source_path, checks, frames=120, dt=1/60, inputs=None, *, repo=None):
    """Run one exact source snapshot with app-specific final-metric predicates.

    Invalid caller input raises ValueError. Missing/unavailable Docker reports
    ``blocked``. Runtime faults and unmet checks report ``failed``. A passed
    result is host-only; ``device_mutations`` is always zero.
    """
    checks = _validate_checks(checks)
    if type(frames) is not int or not 1 <= frames <= 3600:
        raise ValueError('frames must be an integer from 1 to 3600')
    if not _number(dt) or not 0 < dt <= .05:
        raise ValueError('dt must be finite and greater than zero, at most 0.05 seconds')
    trace = _trace(inputs, frames)
    source_path = Path(source_path).resolve()
    if not source_path.is_file() or not 1 <= source_path.stat().st_size <= 16384:
        raise ValueError('Source must be a file containing 1..16384 bytes')
    raw = source_path.read_bytes()
    try:
        raw.decode('utf-8')
    except UnicodeError as error:
        raise ValueError('Source must be valid UTF-8') from error
    if not 1 <= len(raw) <= 16384 or any(byte < 32 and byte not in (9, 10, 13) for byte in raw):
        raise ValueError('Source must be Lua text without binary control bytes')
    repo = Path(repo).resolve() if repo is not None else ROOT
    image = json.loads((repo / 'toolchain.lock.json').read_text(encoding='utf-8'))['image']
    if not isinstance(image, str) or not re.fullmatch(r'vitasdk/vitasdk@sha256:[0-9a-f]{64}', image):
        raise ValueError('Use the digest-pinned VitaSDK image from toolchain.lock.json')
    pins = _source_pins(repo)
    identity = _identity(pins, image)
    result = {'result': 'blocked', 'tier': 'host_shared_lua_runtime', 'device_mutations': 0,
              'native_identity_observed': False, 'source_sha256': _sha(raw), 'source_bytes': len(raw),
              'sandbox_build_id': identity, 'image': image, 'requested_frames': frames,
              'dt': dt, 'inputs': trace, 'limitations': list(LIMITATIONS)}
    docker = shutil.which('docker')
    if not docker:
        return {**result, 'failure_type': 'docker_unavailable'}
    started = time.monotonic()
    try:
        output, built, cached = _build(repo, docker, image, pins, identity)
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as error:
        result.update(failure_type='sandbox_build_unavailable', diagnostic=str(error)[:300],
                      elapsed_s=round(time.monotonic()-started, 3))
        log = repo / 'build/host/vita-app-lua' / identity / 'build.log'
        if log.is_file():
            # Keep the full local evidence and a bounded useful tail in CI's
            # returned failure, where a bare "inspect build.log" is opaque.
            result['build_log'] = str(log)
            with log.open('rb') as stream:
                stream.seek(max(0, log.stat().st_size - 4000))
                result['diagnostic_tail'] = stream.read().decode('utf-8', errors='replace')
        return result
    attempt = output / 'checks' / uuid.uuid4().hex
    attempt.mkdir(parents=True)
    (attempt / 'source.lua').write_bytes(raw)
    trace_text = ''.join(' '.join(str(event[key]) for key in ('frame', 'buttons', 'lx', 'ly', 'rx', 'ry')) + '\n'
                         for event in trace)
    (attempt / 'inputs.txt').write_text(trace_text, encoding='ascii')
    _json(attempt / 'request.json', {'source_sha256': result['source_sha256'], 'checks': checks,
                                   'frames': frames, 'dt': dt, 'inputs': trace})
    result.update(build_cached=cached, sandbox_binary_sha256=built['binary_sha256'],
                  evidence_directory=str(attempt))
    try:
        executed = _docker_run(docker, image, [(repo, '/workspace', True), (output, '/cache', True),
                                               (attempt, '/attempt', False)],
                               ['/cache/test_lua_check', '/attempt/source.lua', str(frames),
                                format(dt, '.17g'), '/attempt/inputs.txt', '/attempt/runtime.json'], 60)
        (attempt / 'runtime.log').write_text(executed.stdout + executed.stderr, encoding='utf-8')
        if executed.returncode:
            raise RuntimeError('Shared sandbox process failed; inspect runtime.log')
        observed = json.loads((attempt / 'runtime.json').read_text(encoding='utf-8'))
        runtime = observed['runtime']
        metrics = runtime['metrics']
        if not isinstance(metrics, dict) or any(not _number(value) for value in metrics.values()):
            raise RuntimeError('Shared sandbox reported invalid metrics')
        predicates = _predicates(metrics, checks)
        invariant_checks = {**observed['invariants'],
                            'source_hash_matches': observed['source_sha256'] == result['source_sha256'],
                            'snapshot_unchanged': _sha((attempt/'source.lua').read_bytes()) == result['source_sha256'],
                            'requested_frames_observed': observed['observed_frames'] == frames,
                            'sandbox_allocation_within_limit': runtime['peak_memory_bytes'] <= 1024*1024}
        healthy = (observed['load_status'] == 200 and observed['phase'] == 'run' and
                   runtime['loaded'] is True and runtime['active'] is True and runtime['faulted'] is False)
        passed = healthy and all(invariant_checks.values()) and all(item['passed'] for item in predicates)
        result.update(result='passed' if passed else 'failed', phase=observed['phase'],
                      load_status=observed['load_status'], load_error=observed['load_error']['error'],
                      runtime_error=runtime['error'], metrics=metrics, checks=predicates,
                      invariants=invariant_checks, updates=runtime['updates'], paused=runtime['paused'],
                      observed_frames=observed['observed_frames'], draw_calls=observed['draw_calls'],
                      max_draw_commands=observed['max_draw_commands'],
                      memory_bytes=runtime['memory_bytes'], peak_memory_bytes=runtime['peak_memory_bytes'])
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as error:
        result.update(result='failed', failure_type='sandbox_execution_failed', diagnostic=str(error)[:300])
    result['elapsed_s'] = round(time.monotonic()-started, 3)
    _json(attempt / 'report.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--checks', type=Path, required=True, help='JSON list of app-specific metric predicates')
    parser.add_argument('--frames', type=int, default=120)
    parser.add_argument('--dt', type=float, default=1/60)
    parser.add_argument('--inputs', type=Path, help='JSON list of ordered controller changes')
    args = parser.parse_args(argv)
    try:
        result = check(args.source, json.loads(args.checks.read_text(encoding='utf-8')),
                       frames=args.frames, dt=args.dt,
                       inputs=json.loads(args.inputs.read_text(encoding='utf-8')) if args.inputs else None)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result['result'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
