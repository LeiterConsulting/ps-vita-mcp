"""Prepare an immutable resident replacement, preserving pairing and active config."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid
from stage import ROOT, checked_upload, connect, endpoint, plugin_bytes, retrieve, save_plan, sha


def replacement(before: bytes, old: str, new: str) -> bytes:
    pattern = r'ux0:data/vita-resident/setup-[0-9a-f]{12}-[0-9a-f]{32}/vita_resident\.suprx'
    if not re.fullmatch(pattern, old) or not re.fullmatch(pattern, new) or old == new:
        raise ValueError('Expected distinct immutable resident paths')
    lines = before.splitlines(keepends=True)
    section = None
    matches = []
    for index, line in enumerate(lines):
        text = line.rstrip(b'\r\n').decode('utf-8')
        if text.startswith('*'):
            section = text
        if text == old:
            if section != '*main':
                raise ValueError('Resident line is outside SceShell')
            matches.append(index)
        elif ('vita_resident.suprx' in text or 'vita-resident/setup-' in text) and not text.startswith('#'):
            raise ValueError('Unexpected additional resident line')
    if len(matches) != 1:
        raise ValueError('Expected exactly one active resident line')
    index = matches[0]
    ending = lines[index][len(old):]
    lines[index] = new.encode('ascii') + ending
    after = b''.join(lines)
    if after.replace(new.encode('ascii'), old.encode('ascii'), 1) != before:
        raise ValueError('Update changed unrelated configuration')
    return after


def stage_update(root: Path, expected_config_sha256: str, old_plugin: str) -> dict:
    if not re.fullmatch('[0-9a-f]{64}', expected_config_sha256):
        raise ValueError('Exact active config hash is required')
    payload, report = plugin_bytes(root)
    private = json.loads((root / '.devloop-private/resident.json').read_text(encoding='utf-8'))
    if not re.fullmatch('[0-9a-f]{32}', private.get('token', '')):
        raise ValueError('Invalid saved pairing')
    ftp = connect(endpoint(root / '.devloop-private/ftp.json'))
    plan_path = None
    try:
        if retrieve(ftp, '/ux0:/tai/config.txt', 16384, absent=True) is not None:
            raise ValueError('Unexpected higher-precedence ux0 config')
        before = retrieve(ftp, '/ur0:/tai/config.txt', 16384)
        if sha(before) != expected_config_sha256:
            raise ValueError('Active config changed since inspection')
        pairing = (private['token'] + '\n').encode('ascii')
        if retrieve(ftp, '/ux0:/data/vita-resident/bridge.cfg', 34) != pairing:
            raise ValueError('Device pairing differs from saved pairing')
        attempt = 'setup-' + report['plugin']['sha256'][:12] + '-' + uuid.uuid4().hex
        native = 'ux0:data/vita-resident/' + attempt
        remote = '/ux0:/data/vita-resident/' + attempt
        after = replacement(before, old_plugin, native + '/vita_resident.suprx')
        evidence = root / 'evidence/resident' / attempt
        evidence.mkdir(parents=True, exist_ok=False)
        (evidence / 'config.txt.before-update').write_bytes(before)
        (evidence / 'config.txt.resident-proposed').write_bytes(after)
        files = {remote + '/vita_resident.suprx': payload, remote + '/config.txt.before-update': before, remote + '/config.txt': after}
        plan = {'prepared_utc': datetime.now(timezone.utc).isoformat(), 'version': report['version'], 'attempt': attempt,
                'vita_directory': native, 'plugin_path': native + '/vita_resident.suprx', 'previous_plugin_path': old_plugin,
                'plugin_sha256': sha(payload), 'build_report_sha256': sha((root / 'dist/resident/build-report.json').read_bytes()),
                'active_config_before_sha256': sha(before), 'proposed_config_sha256': sha(after),
                'pairing_preserved': True, 'active_config_unchanged': False, 'state': 'prepared; device writes pending',
                'files': {path: {'bytes': len(data), 'sha256': sha(data), 'read_back_checks': 0} for path, data in files.items()},
                'local_evidence': str(evidence)}
        plan_path = evidence / 'deployment.json'
        save_plan(plan_path, plan)
        ftp.mkd(remote)
        plan['state'] = 'staging; failures require inspection, never automatic replay'
        save_plan(plan_path, plan)
        for path, data in files.items():
            checked_upload(ftp, path, data)
            plan['files'][path]['read_back_checks'] = 2
            save_plan(plan_path, plan)
        if retrieve(ftp, '/ur0:/tai/config.txt', 16384) != before or retrieve(ftp, '/ux0:/data/vita-resident/bridge.cfg', 34) != pairing:
            raise ValueError('Active config or pairing changed during staging')
        plan['active_config_unchanged'] = True
        plan['state'] = 'verified staged replacement; manual config copy and reboot pending'
        save_plan(plan_path, plan)
        return plan
    except Exception as error:
        if plan_path is not None:
            plan['state'] = 'staging failed or outcome uncertain; inspect this attempt before any retry'
            plan['failure_type'] = type(error).__name__
            save_plan(plan_path, plan)
        raise RuntimeError('Resident update staging failed; active config was not written by this procedure') from error
    finally:
        ftp.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--expected-config-sha256', required=True)
    parser.add_argument('--old-plugin', required=True)
    arguments = parser.parse_args()
    print(json.dumps(stage_update(ROOT, arguments.expected_config_sha256, arguments.old_plugin), indent=2))
