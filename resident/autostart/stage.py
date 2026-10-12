"""Stage immutable one-shot startup files, without arming or activating them."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import ftplib
import io
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from resident.stage import connect, endpoint, retrieve, save_plan, sha

FILES = {'vita_autostart.suprx', 'autostart_shell_probe.suprx',
         'vita_control_kernel.skprx', 'vita_control.suprx'}
ACTIVE = '/ur0:/tai/config.txt'
PAIRING = '/ux0:/data/vita-resident/bridge.cfg'
BASE = '/ux0:/data/vita-autostart'


def pin(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
        raise ValueError('An exact lowercase SHA-256 is required')
    return value


def validated(root, expected_report):
    """Hold checked bytes before any FTP connection or mutation."""
    raw = (root / 'dist/autostart/build-report.json').read_bytes()
    if sha(raw) != pin(expected_report):
        raise ValueError('Autostart build report differs from the selected report')
    report = json.loads(raw)
    setup = report['setup']
    if (report['version'] != '0.1.0' or report['mode'] != 'experimental one-shot only'
            or not re.fullmatch(r'setup-[0-9a-f]{32}', setup)
            or report['module_root'] != 'ux0:data/vita-autostart/' + setup + '/'):
        raise ValueError('Unexpected startup identity/path')
    pin(report['control_build_id'])
    if set(report['artifacts']) != FILES:
        raise ValueError('Expected the two boot helpers and unchanged Control pair')
    payloads = {}
    for name, expected in report['artifacts'].items():
        data = (root / 'dist/autostart' / name).read_bytes()
        if (type(expected['bytes']) is not int or not 0 < len(data) <= 256 * 1024
                or len(data) != expected['bytes'] or sha(data) != pin(expected['sha256'])
                or data[:4] != b'SCE\0'):
            raise ValueError('Startup artifact differs: ' + name)
        payloads[name] = data
    for field in ('source_hashes', 'control_source_hashes'):
        if not report[field]:
            raise ValueError('Missing source pins')
        for relative, expected in report[field].items():
            target = (root / relative).resolve()
            if not target.is_relative_to(root.resolve()) or sha(target.read_bytes()) != pin(expected):
                raise ValueError('Recorded source differs; rebuild before staging')
    return payloads, report


def proposal(before, plugin):
    if not re.fullmatch(r'ux0:data/vita-autostart/setup-[0-9a-f]{32}/vita_autostart\.suprx', plugin):
        raise ValueError('Plugin path must match the compiled immutable root')
    text = before.decode('utf-8')
    if '\0' in text or 'vita-autostart/' in text:
        raise ValueError('Invalid config or an earlier autostart is already configured')
    lines = before.splitlines(keepends=True)
    section = None
    resident_index = None
    main_count = 0
    for index, raw in enumerate(lines):
        line = raw.decode('utf-8').strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('*'):
            section = line
            main_count += line == '*main'
        elif 'vita_control' in line or 'vita-control/' in line:
            raise ValueError('Existing Control boot entries require recovery before this experiment')
        elif 'vita_resident.suprx' in line:
            if section != '*main' or resident_index is not None:
                raise ValueError('Expected one Resident in SceShell')
            resident_index = index
    if resident_index is None or main_count == 0:
        raise ValueError('Expected one existing Resident in a SceShell section')
    raw = lines[resident_index]
    if not raw.endswith(b'\n'):
        raise ValueError('Resident line needs a terminator')
    ending = b'\r\n' if raw.endswith(b'\r\n') else b'\n'
    added = plugin.encode('ascii') + ending
    after = b''.join(lines[:resident_index + 1] + [added] + lines[resident_index + 1:])
    if after.replace(added, b'', 1) != before:
        raise ValueError('Existing configuration bytes were not preserved')
    return after


def upload(ftp, directory, name, data):
    if name not in FILES | {'config.txt', 'config.txt.before-autostart', 'enable.once'}:
        raise ValueError('Unexpected staged filename')
    if not re.fullmatch(re.escape(BASE) + r'/setup-[0-9a-f]{32}', directory):
        raise ValueError('Upload escaped the fresh setup directory')
    target = directory + '/' + name
    # Even in this exclusive directory, an unexpected partial file blocks retries.
    if (retrieve(ftp, target, len(data), absent=True) is not None
            or retrieve(ftp, target + '.part', len(data), absent=True) is not None):
        raise ValueError('Staged destination already exists; do not retry uncertain writes')
    ftp.storbinary('STOR ' + target + '.part', io.BytesIO(data), blocksize=16384)
    if retrieve(ftp, target + '.part', len(data)) != data:
        raise ValueError('Partial-file read-back mismatch')
    ftp.rename(target + '.part', target)
    if retrieve(ftp, target, len(data)) != data:
        raise ValueError('Final-file read-back mismatch')


def stage(root: Path, expected_report: str, expected_config: str):
    payloads, report = validated(root, expected_report)
    pin(expected_config)
    ftp = connect(endpoint(root / '.devloop-private/ftp.json'))
    receipt = None
    state = 'read-only preflight'
    try:
        if retrieve(ftp, '/ux0:/tai/config.txt', 16384, absent=True) is not None:
            raise ValueError('Unexpected overriding ux0 config')
        before = retrieve(ftp, ACTIVE, 16384)
        pairing = retrieve(ftp, PAIRING, 256)
        if sha(before) != expected_config or not pairing:
            raise ValueError('Active config changed or Resident pairing is unavailable')
        # Existing opt-in is unsafe even if this new setup will not activate it.
        for name in ('enable.once', 'enable.consumed', 'attempt.inflight'):
            if retrieve(ftp, BASE + '/' + name, 256, absent=True) is not None:
                raise ValueError('Prior startup marker requires inspection before staging')
        plugin = report['module_root'] + 'vita_autostart.suprx'
        after = proposal(before, plugin)
        directory = BASE + '/' + report['setup']
        files = {**payloads, 'config.txt.before-autostart': before, 'config.txt': after,
                 'enable.once': (report['control_build_id'] + '\n').encode('ascii')}
        evidence = root / 'evidence/autonomy' / ('stage-' + report['setup'])
        evidence.mkdir(parents=True, exist_ok=False)
        (evidence / 'config.txt.before-autostart').write_bytes(before)
        (evidence / 'config.txt.proposed').write_bytes(after)
        receipt = evidence / 'deployment.json'
        plan = {'prepared_utc': datetime.now(timezone.utc).isoformat(),
                'setup': report['setup'], 'module_root': report['module_root'],
                'build_report_sha256': expected_report, 'control_build_id': report['control_build_id'],
                'active_config_before_sha256': sha(before), 'proposed_config_sha256': sha(after),
                'files': {name: {'bytes': len(data), 'sha256': sha(data), 'read_back_checks': 0}
                          for name, data in files.items()},
                'activation': 'disabled; active config and active enable.once are untouched',
                'state': 'prepared; no device writes yet'}
        save_plan(receipt, plan)
        try:
            ftp.cwd(BASE)
        except ftplib.error_perm as error:
            if not str(error).startswith('550'):
                raise
            state = 'creating startup parent directory'
            plan['state'] = state
            save_plan(receipt, plan)
            ftp.mkd(BASE)
        state = 'creating exclusive immutable setup directory'
        plan['state'] = state
        save_plan(receipt, plan)
        ftp.mkd(directory)  # Collision is a hard refusal, never an overwrite.
        for name, data in files.items():
            state = 'staging ' + name
            plan['state'] = state
            save_plan(receipt, plan)
            upload(ftp, directory, name, data)
            plan['files'][name]['read_back_checks'] = 2
            save_plan(receipt, plan)
        state = 'verifying active configuration, pairing and opt-in remain unchanged'
        if (retrieve(ftp, ACTIVE, 16384) != before or retrieve(ftp, PAIRING, 256) != pairing
                or retrieve(ftp, '/ux0:/tai/config.txt', 16384, absent=True) is not None
                or retrieve(ftp, BASE + '/enable.once', 256, absent=True) is not None):
            raise ValueError('Active device state changed during staging')
        plan.update(state='staged and read-back verified; disabled', active_config_unchanged=True,
                    pairing_unchanged=True, verified_utc=datetime.now(timezone.utc).isoformat())
        save_plan(receipt, plan)
        return {**plan, 'local_evidence': str(receipt)}
    except Exception as error:
        if receipt is not None:
            plan.update(state='uncertain or incomplete while ' + state, failure_type=type(error).__name__)
            save_plan(receipt, plan)
        raise RuntimeError('Startup staging failed during ' + state + '. No replay, activation or cleanup performed; inspect the receipt. Cause: ' + type(error).__name__) from error
    finally:
        ftp.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-report-sha256', required=True)
    parser.add_argument('--active-config-sha256', required=True)
    args = parser.parse_args()
    result = stage(ROOT, args.build_report_sha256, args.active_config_sha256)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
