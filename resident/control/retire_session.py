"""Retain one exact Control Starter guard after an explicitly confirmed normal reboot.

Only the Control Starter data marker is renamed. No modules or boot config are changed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from resident.stage import connect, endpoint, retrieve

GUARD = '/ux0:/data/vita-control/control-session.lock'


def identity(data):
    if data is None:
        return None
    if len(data) != 44:
        raise ValueError('Invalid Control Starter guard length')
    magic, mode, run, padding = struct.unpack('<II33s3s', data)
    if magic != 0x31534356 or mode != 1 or run[-1] or padding != b'\0' * 3 or not re.fullmatch(b'[0-9a-f]{32}', run[:-1]):
        raise ValueError('Invalid Control Starter guard identity')
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'mode': mode, 'run': run[:-1].decode('ascii')}


def snapshot(ftp):
    config = retrieve(ftp, '/ur0:/tai/config.txt', 16384)
    if retrieve(ftp, '/ux0:/tai/config.txt', 16384, absent=True) is not None:
        raise ValueError('An overriding ux0 boot config needs separate inspection')
    guard = retrieve(ftp, GUARD, 256, absent=True)
    return config, guard


def inspect_session():
    ftp = connect(endpoint(ROOT / '.devloop-private/ftp.json'))
    try:
        config, guard = snapshot(ftp)
        return {'active_config_sha256': hashlib.sha256(config).hexdigest(),
                'session_guard': identity(guard), 'module_actions': 'none', 'remote_writes': 'none',
                'reboot_confirmation': 'inspection is not proof of a reboot'}
    finally:
        ftp.close()


def retire(expected_guard, expected_package, expected_config, reboot_confirmed=False):
    if not reboot_confirmed:
        raise ValueError('Confirm a normal reboot before retiring a session guard')
    if not all(re.fullmatch('[0-9a-f]{64}', value) for value in (expected_guard, expected_package, expected_config)):
        raise ValueError('Exact guard, package and config SHA-256 values are required')
    build = json.loads((ROOT / 'dist/control/build-report.json').read_text(encoding='utf-8'))
    if build['version'] != '0.3.3' or build['starter_package']['sha256'] != expected_package:
        raise ValueError('Package identity differs from the Control Starter build report')
    attempt = uuid.uuid4().hex
    folder = ROOT / 'evidence/control' / ('starter-session-retirement-' + attempt)
    folder.mkdir(parents=True, exist_ok=False)
    retained = '/ux0:/data/vita-control/control-session.retired-' + attempt + '.lock'
    receipt = {'prepared_utc': datetime.now(timezone.utc).isoformat(), 'state': 'preflight',
               'normal_reboot': 'explicitly confirmed by user; not inferred from FTP',
               'package_sha256': expected_package, 'guard_sha256': expected_guard,
               'config_sha256': expected_config, 'retained_path': retained,
               'module_actions': 'none', 'active_config_unchanged': False}

    def save():
        (folder / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')

    ftp = connect(endpoint(ROOT / '.devloop-private/ftp.json'))
    try:
        config, guard = snapshot(ftp)
        if hashlib.sha256(config).hexdigest() != expected_config:
            raise ValueError('Active boot config differs')
        files = {entry['name']: entry for entry in build['starter_package']['files']}
        for name in ('eboot.bin', 'vita_control_kernel.skprx', 'vita_control.suprx', 'control_bootstrap_probe.suprx', 'sce_sys/param.sfo'):
            data = retrieve(ftp, '/ux0:/app/CHRS00011/' + name, 1024 * 1024)
            if len(data) != files[name]['bytes'] or hashlib.sha256(data).hexdigest() != files[name]['sha256']:
                raise ValueError('Installed Control Starter differs from the exact build')
        receipt['session_guard'] = identity(guard)
        if guard is None or receipt['session_guard']['sha256'] != expected_guard:
            raise ValueError('Session guard differs or is absent')
        (folder / 'control-session.lock.before').write_bytes(guard)
        (folder / 'config.active.txt').write_bytes(config)
        if retrieve(ftp, retained, 256, absent=True) is not None:
            raise ValueError('Retained destination already exists')
        receipt['state'] = 'verified; renaming exact guard after confirmed reboot'
        save()
        ftp.rename(GUARD, retained)
        if retrieve(ftp, retained, 256) != guard or retrieve(ftp, GUARD, 256, absent=True) is not None:
            raise ValueError('Guard retirement readback differs')
        config_after, _ = snapshot(ftp)
        if config_after != config:
            raise ValueError('Boot config changed during retirement')
        receipt['active_config_unchanged'] = True
        receipt['state'] = 'exact guard retained and original path absent; manual Control Starter launch ready'
        receipt['verified_utc'] = datetime.now(timezone.utc).isoformat()
        save()
        return receipt
    except Exception as error:
        receipt['state'] = 'failed or uncertain; inspect exact paths before any retry'
        receipt['failure_type'] = type(error).__name__
        save()
        raise RuntimeError('Control Starter session retirement failed or is uncertain; no module or boot config changes were made') from None
    finally:
        ftp.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--inspect', action='store_true')
    parser.add_argument('--guard-sha256')
    parser.add_argument('--package-sha256')
    parser.add_argument('--expected-config-sha256')
    parser.add_argument('--normal-reboot-confirmed', action='store_true')
    args = parser.parse_args()
    if args.inspect:
        print(json.dumps(inspect_session(), indent=2))
    else:
        if not all((args.guard_sha256, args.package_sha256, args.expected_config_sha256)):
            parser.error('Retirement requires the exact guard, package and active config SHA-256 values')
        print(json.dumps(retire(args.guard_sha256, args.package_sha256, args.expected_config_sha256, args.normal_reboot_confirmed), indent=2))
