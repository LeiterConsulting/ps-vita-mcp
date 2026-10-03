"""Stage a fresh resident setup and a proposed tai configuration; never activate it."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import ftplib
import hashlib
import io
import json
from pathlib import Path
import re
import secrets
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bridge'))
from ftp_staging import endpoint


def sha(data):
    return hashlib.sha256(data).hexdigest()


def retrieve(ftp, path, limit, absent=False):
    data = bytearray()

    def accept(block):
        if len(data) + len(block) > limit:
            raise ValueError('FTP read exceeded its bound')
        data.extend(block)

    try:
        ftp.retrbinary('RETR ' + path, accept, blocksize=16384)
    except ftplib.error_perm as error:
        if absent and str(error).startswith('550'):
            return None
        raise
    return bytes(data)


def proposal(before: bytes, plugin: str) -> bytes:
    if not re.fullmatch(r'ux0:data/vita-resident/setup-[0-9a-f]{12}-[0-9a-f]{32}/vita_resident\.suprx', plugin):
        raise ValueError('Plugin path must be a fresh immutable setup path')
    text = before.decode('utf-8')
    if '\x00' in text or 'vita-resident/' in text or 'vita_resident.suprx' in text:
        raise ValueError('Config is invalid or already refers to the resident prototype')
    lines = before.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.rstrip(b'\r\n') == b'*main':
            if not line.endswith(b'\n'):
                raise ValueError('The *main header needs a line terminator')
            ending = b'\r\n' if line.endswith(b'\r\n') else b'\n'
            added = plugin.encode('ascii') + ending
            after = b''.join(lines[:i + 1] + [added] + lines[i + 1:])
            if after.replace(added, b'', 1) != before:
                raise ValueError('Proposal did not preserve every existing byte')
            return after
    raise ValueError('Active config has no SceShell *main section')


def plugin_bytes(root):
    report = json.loads((root / 'dist/resident/build-report.json').read_text(encoding='utf-8'))
    payload = (root / 'dist/resident/vita_resident.suprx').read_bytes()
    info = report['plugin']
    if not 0 < len(payload) <= 256 * 1024 or len(payload) != info['bytes'] or sha(payload) != info['sha256'] or payload[:4] != b'SCE\0' or report['version'] != '0.1.1' or info['module_attributes'] != 0:
        raise ValueError('Plugin bytes and build evidence do not match')
    for relative, expected in report['source_hashes'].items():
        if sha((root / relative).read_bytes()) != expected:
            raise ValueError('Rebuild after changing a recorded source: ' + relative)
    for relative, expected in report['accepted_artifacts_preserved'].items():
        if sha((root / relative).read_bytes()) != expected:
            raise ValueError('Previously accepted artifact changed')
    return payload, report


def save_plan(path, plan):
    path.write_text(json.dumps(plan, indent=2) + '\n', encoding='utf-8')


def checked_upload(ftp, path, data):
    # All callers operate inside a newly created exclusive resident root.
    if not path.startswith('/ux0:/data/vita-resident/') or '..' in path:
        raise ValueError('Upload escaped the resident setup directory')
    ftp.storbinary('STOR ' + path + '.part', io.BytesIO(data), blocksize=16384)
    if retrieve(ftp, path + '.part', len(data)) != data:
        raise ValueError('Part read-back mismatch')
    ftp.rename(path + '.part', path)
    if retrieve(ftp, path, len(data)) != data:
        raise ValueError('Final read-back mismatch')


def connect(config):
    ftp = ftplib.FTP(timeout=10)
    try:
        ftp.connect(config['host'], config['port'])
        ftp.login(config['username'], config['password'])
        ftp.trust_server_pasv_ipv4_address = False
        return ftp
    except BaseException:
        ftp.close()
        raise


def stage(root: Path, expected_config_sha256: str) -> dict:
    if not re.fullmatch('[0-9a-f]{64}', expected_config_sha256):
        raise ValueError('Exact expected active config SHA-256 is required')
    payload, report = plugin_bytes(root)
    config = endpoint(root / '.devloop-private/ftp.json')
    private = root / '.devloop-private/resident.json'
    if private.exists():
        raise ValueError('Resident pairing already exists; inspect the recorded deployment instead of restaging')
    ftp = connect(config)
    state = 'read-only preflight'
    plan_path = None
    try:
        if retrieve(ftp, '/ux0:/tai/config.txt', 16384, absent=True) is not None:
            raise ValueError('ux0 tai config takes precedence; this procedure requires the inspected ur0 config')
        before = retrieve(ftp, '/ur0:/tai/config.txt', 16384)
        if sha(before) != expected_config_sha256:
            raise ValueError('Active tai config changed since inspection')
        attempt = 'setup-' + report['plugin']['sha256'][:12] + '-' + uuid.uuid4().hex
        native_dir = 'ux0:data/vita-resident/' + attempt
        remote_dir = '/ux0:/data/vita-resident/' + attempt
        plugin = native_dir + '/vita_resident.suprx'
        after = proposal(before, plugin)
        token = secrets.token_hex(16)
        pairing = (token + '\n').encode('ascii')
        evidence = root / 'evidence/resident' / attempt
        evidence.mkdir(parents=True, exist_ok=False)
        (evidence / 'config.txt.before-resident').write_bytes(before)
        (evidence / 'config.txt.resident-proposed').write_bytes(after)
        plan_path = evidence / 'deployment.json'
        files = {
            '/ux0:/data/vita-resident/bridge.cfg': pairing,
            remote_dir + '/vita_resident.suprx': payload,
            remote_dir + '/config.txt.before-resident': before,
            remote_dir + '/config.txt': after,
        }
        plan = {
            'prepared_utc': datetime.now(timezone.utc).isoformat(), 'endpoint': f"{config['host']}:{config['port']}",
            'attempt': attempt, 'vita_directory': native_dir, 'plugin_path': plugin,
            'plugin_sha256': report['plugin']['sha256'], 'build_report_sha256': sha((root / 'dist/resident/build-report.json').read_bytes()),
            'active_config_before_sha256': sha(before), 'proposed_config_sha256': sha(after),
            'files': {path: {'bytes': len(data), 'sha256': sha(data), 'read_back_checks': 0} for path, data in files.items()},
            'activation': 'pending manual config copy and normal reboot', 'state': 'prepared; no device writes yet',
        }
        save_plan(plan_path, plan)
        # Save the token before any device writes so an uncertain outcome is recoverable.
        with private.open('x', encoding='utf-8') as handle:
            json.dump({'host': config['host'], 'port': 17866, 'token': token}, handle)
            handle.write('\n')
        state = 'creating exclusive resident root'
        plan['state'] = state
        save_plan(plan_path, plan)
        ftp.mkd('/ux0:/data/vita-resident')  # Existing root is a hard refusal.
        ftp.mkd('/ux0:/data/vita-resident/inbox')
        ftp.mkd(remote_dir)
        for path, data in files.items():
            state = 'staging ' + path
            plan['state'] = state
            save_plan(plan_path, plan)
            checked_upload(ftp, path, data)
            plan['files'][path]['read_back_checks'] = 2
            save_plan(plan_path, plan)
        state = 'verifying active config remains unchanged'
        if retrieve(ftp, '/ur0:/tai/config.txt', 16384) != before or retrieve(ftp, '/ux0:/tai/config.txt', 16384, absent=True) is not None:
            raise ValueError('Active configuration changed during staging; review before activating')
        plan['state'] = 'staged and read-back verified'
        plan['active_config_unchanged'] = True
        plan['verified_utc'] = datetime.now(timezone.utc).isoformat()
        save_plan(plan_path, plan)
        return {**plan, 'local_evidence': str(plan_path)}
    except Exception as error:
        if plan_path is not None:
            plan['state'] = 'uncertain or incomplete while ' + state
            plan['failure_type'] = type(error).__name__
            save_plan(plan_path, plan)
        raise RuntimeError(f'Resident staging failed while {state}. No retry, activation, overwrite or cleanup was performed. Inspect the saved deployment before continuing. Cause: {type(error).__name__}.') from error
    finally:
        ftp.close()


def verify_existing(root, plan_path):
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    ftp = connect(endpoint(root / '.devloop-private/ftp.json'))
    try:
        for path, expected in plan['files'].items():
            if not path.startswith('/ux0:/data/vita-resident/') or '..' in path or not 0 < expected['bytes'] <= 256 * 1024:
                raise ValueError('Invalid saved deployment path/size')
            for _ in range(2):
                data = retrieve(ftp, path, expected['bytes'])
                if sha(data) != expected['sha256'] or len(data) != expected['bytes']:
                    raise ValueError('Saved deployment read-back mismatch')
        if retrieve(ftp, '/ux0:/tai/config.txt', 16384, absent=True) is not None:
            raise ValueError('Unexpected ux0 tai config')
        active = sha(retrieve(ftp, '/ur0:/tai/config.txt', 16384))
        if active not in [plan['active_config_before_sha256'], plan['proposed_config_sha256']]:
            raise ValueError('Active tai config differs from both recorded copies')
        return {'attempt': plan['attempt'], 'read_back_checks_per_file': 2, 'active_config_sha256': active, 'configuration': 'proposal present; runtime unverified' if active == plan['proposed_config_sha256'] else 'unchanged; activation pending'}
    finally:
        ftp.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--expected-config-sha256')
    group.add_argument('--verify-existing', type=Path)
    args = parser.parse_args()
    try:
        result = verify_existing(ROOT, args.verify_existing) if args.verify_existing else stage(ROOT, args.expected_config_sha256)
        print(json.dumps(result, indent=2))
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
