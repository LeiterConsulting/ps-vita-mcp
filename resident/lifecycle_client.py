"""Strict fixed-title native lifecycle transport. Mutations are never replayed."""
from __future__ import annotations

import http.client
import re

from workbench.native_package import PROJECT, TITLE, MAX_FILE, canonical, json_object, sha
from resident.launch_client import configuration

APP = 'Vita Native Lifecycle'
STATES = frozenset(('queued', 'dispatch_intent', 'running', 'installed_verified',
                    'submitted', 'native_rejected', 'refused', 'expired', 'unknown'))
# Fixed protocol reasons emitted by resident/native_install/service.c. Never
# retain arbitrary HTTP error bodies, including errors from other services.
REJECTION_REASONS = {
    'administrator_required': (403, 'authorization'),
    'not_initialized': (503, 'availability'),
    'policy_unavailable': (503, 'availability'),
    'reply_too_large': (500, 'availability'),
    'request_invalid': (400, 'request_validation'),
    'method_or_body_invalid': (400, 'request_validation'),
    'manifest_invalid': (400, 'request_validation'),
    'path_invalid': (400, 'request_validation'),
    'operation_invalid': (400, 'request_validation'),
    'path_or_body_invalid': (400, 'request_validation'),
    'upload_path_or_digest_invalid': (400, 'request_validation'),
    'upload_path_invalid': (400, 'request_validation'),
    'service_blocked_or_busy': (409, 'availability'),
    'identity_mismatch': (409, 'identity'),
    'manifest_or_stage_identity_mismatch': (409, 'identity'),
    'upload_identity_mismatch': (409, 'identity'),
    'request_expired': (408, 'expiry'),
    'stage_capacity': (507, 'capacity'),
    'attempt_capacity': (507, 'capacity'),
    'free_space_unavailable': (507, 'capacity'),
    'stage_exists_or_uncertain': (409, 'storage'),
    'stage_directory_failed': (507, 'storage'),
    'manifest_storage_uncertain': (507, 'storage'),
    'stage_missing_or_invalid': (404, 'storage'),
    'attempt_exists_or_uncertain': (409, 'storage'),
    'claim_storage_uncertain': (507, 'storage'),
    'attempt_missing_or_invalid': (404, 'storage'),
    'file_exists_or_uncertain': (409, 'storage'),
    'file_create_failed': (507, 'storage'),
    'file_upload_uncertain_retained_part': (422, 'storage'),
    'file_publication_uncertain': (507, 'storage'),
    'native_idle_policy_refused': (409, 'idle_policy'),
    'candidate_verification_failed': (422, 'verification'),
    'installed_title_not_verified_owned': (409, 'installed_ownership'),
    'installed_candidate_mismatch': (409, 'verification'),
}


def hex_pin(value, size):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(size) + '}', value) is not None


class LifecycleRejected(RuntimeError):
    def __init__(self, status, reason=None):
        if type(status) is not int or not 100 <= status <= 599:
            raise ValueError('Invalid native lifecycle HTTP status')
        self.status = status
        known = REJECTION_REASONS.get(reason) if isinstance(reason, str) else None
        self.reason = reason if known is not None and known[0] == status else None
        self.category = known[1] if self.reason is not None else 'unrecognized_rejection'
        self.diagnostic = {'http_status': status, 'reason': self.reason, 'category': self.category}
        super().__init__('Native lifecycle request rejected with HTTP ' + str(status)
                         + (': ' + self.reason if self.reason is not None else ''))


class LifecycleTransport(RuntimeError):
    pass


class LifecycleClient:
    def __init__(self, provider=configuration):
        self.provider = provider
        self.endpoint = dict(provider())

    def check_endpoint(self):
        if self.provider() != self.endpoint:
            raise RuntimeError('Resident endpoint configuration changed')

    def request(self, method, path, raw=None, *, digest=None, lab=False):
        self.check_endpoint()
        if raw is not None and len(raw) > MAX_FILE:
            raise ValueError('Native lifecycle request exceeds its bound')
        connection = http.client.HTTPConnection(self.endpoint['host'],
                                               17868 if lab else self.endpoint['port'],
                                               timeout=15 if method == 'PUT' else 5)
        headers = {'Authorization': 'Bearer ' + self.endpoint['token'], 'Connection': 'close'}
        if raw is not None:
            headers['Content-Type'] = 'application/octet-stream' if method == 'PUT' else 'application/json'
        if digest is not None:
            headers['X-SHA256'] = digest
        try:
            connection.request(method, path, raw, headers)
            response = connection.getresponse()
            data = response.read(16385)
            if len(data) > 16384 or response.getheader('Content-Type', '').split(';')[0] != 'application/json':
                raise RuntimeError('Invalid native lifecycle response bounds or content type')
            if response.status not in (200, 201, 202):
                reason = None
                try:
                    rejected = json_object(data)
                    if (not lab and path.startswith('/native-lifecycle/')
                            and set(rejected) == {'app', 'protocol', 'error'} and rejected['app'] == APP
                            and type(rejected['protocol']) is int and rejected['protocol'] == 1
                            and isinstance(rejected['error'], str)):
                        reason = rejected['error']
                except (ValueError, UnicodeError, TypeError):
                    pass
                self.check_endpoint()
                raise LifecycleRejected(response.status, reason)
            try:
                value = json_object(data)
            except (ValueError, UnicodeError, TypeError):
                raise RuntimeError('Invalid native lifecycle JSON response') from None
            self.check_endpoint()
            return response.status, value
        except (OSError, http.client.HTTPException) as error:
            raise LifecycleTransport('Native lifecycle connection interrupted; inspect the original attempt') from error
        finally:
            connection.close()

    @staticmethod
    def _common(value):
        if value.get('app') != APP or type(value.get('protocol')) is not int or value['protocol'] != 1:
            raise RuntimeError('Invalid native lifecycle identity')

    def status(self):
        code, value = self.request('GET', '/native-lifecycle/status')
        self._common(value)
        if (code != 200 or value.get('project') != PROJECT or value.get('title_id') != TITLE
                or not hex_pin(value.get('resident_build_id'), 64) or not hex_pin(value.get('instance_id'), 32)
                or type(value.get('clock_ms')) is not int or value['clock_ms'] < 0
                or type(value.get('blocked')) is not bool
                or value.get('active_attempt') is not None and not hex_pin(value['active_attempt'], 32)
                or value.get('policy') != 'conservative_idle_only'
                or type(value.get('max_file_bytes')) is not int or value['max_file_bytes'] != MAX_FILE
                or type(value.get('max_total_bytes')) is not int or value['max_total_bytes'] != 16 * 1024 * 1024):
            raise RuntimeError('Invalid native lifecycle status')
        guard = value.get('guard')
        if (not isinstance(guard, dict) or type(guard.get('ready')) is not bool
                or guard.get('policy') != 'idle_shell_only' or guard.get('snapshot_atomic') is not False
                or guard.get('foreground_verified') is not False or guard.get('protected_ui_verified') is not False
                or type(guard.get('occupied_slots')) is not int or guard['occupied_slots'] < 0):
            raise RuntimeError('Invalid native lifecycle idle guard')
        installer = value.get('installer')
        if (not isinstance(installer, dict) or type(installer.get('ready')) is not bool
                or type(installer.get('paf_result')) is not int or type(installer.get('promoter_result')) is not int):
            raise RuntimeError('Invalid native installer availability')
        return value

    def inventory(self, expected_pid):
        code, value = self.request('GET', '/devloop-launch/inventory')
        entries = value.get('entries')
        if (code != 200 or value.get('app') != 'Vita Resident Launch Inventory'
                or type(value.get('protocol')) is not int or value['protocol'] != 1
                or value.get('available') is not True or type(value.get('enumeration_result')) is not int
                or value['enumeration_result'] < 0 or type(value.get('capacity')) is not int or value['capacity'] != 16
                or type(value.get('sampled_ms')) is not int or value['sampled_ms'] < 0
                or value.get('snapshot_atomic') is not False or value.get('foreground_verified') is not False
                or value.get('protected_ui_verified') is not False or value.get('capacity_limited') is not True
                or not isinstance(entries, list) or type(value.get('entries_reported')) is not int
                or len(entries) != value['entries_reported'] or len(entries) >= 16):
            raise RuntimeError('Invalid or potentially truncated native app inventory')
        pids, app_ids = set(), set()
        for item in entries:
            if (not isinstance(item, dict) or set(item) != {'app_id', 'pid', 'title_id', 'resolved'}
                    or item['resolved'] is not True or type(item['app_id']) is not int or item['app_id'] <= 0
                    or type(item['pid']) is not int or item['pid'] <= 0
                    or not isinstance(item['title_id'], str) or not re.fullmatch('[A-Z0-9]{9}', item['title_id'])
                    or item['pid'] in pids or item['app_id'] in app_ids):
                raise RuntimeError('Unresolved or duplicate native app inventory identity')
            pids.add(item['pid'])
            app_ids.add(item['app_id'])
        if len(entries) != 1 or entries[0]['title_id'] != TITLE or entries[0]['pid'] != expected_pid:
            raise RuntimeError('Native inventory does not exclusively match the owned lab PID')
        return value

    def stage(self, manifest):
        raw = canonical(manifest)
        if len(raw) > 4096:
            raise ValueError('Native stage manifest exceeds 4096 bytes')
        code, value = self.request('POST', '/native-lifecycle/stage', raw)
        if code != 201:
            raise RuntimeError('Native stage did not receive creation acknowledgement')
        return self._stage(value, manifest, sha(raw))

    def inspect_stage(self, attempt, manifest=None, manifest_sha256=None):
        if not hex_pin(attempt, 32):
            raise ValueError('Pin the exact native stage attempt')
        code, value = self.request('GET', '/native-lifecycle/stage/' + attempt)
        if code != 200:
            raise RuntimeError('Invalid native stage inspection acknowledgement')
        return self._stage(value, manifest, manifest_sha256)

    def _stage(self, value, manifest, digest):
        self._common(value)
        if (not hex_pin(value.get('stage_attempt'), 32) or not hex_pin(value.get('manifest_sha256'), 64)
                or not isinstance(value.get('manifest'), dict) or value.get('snapshot_atomic') is not False
                or type(value.get('complete')) is not bool
                or not isinstance(value.get('files'), list) or len(value['files']) != 8):
            raise RuntimeError('Invalid native stage observation')
        observed = value['manifest']
        if (observed.get('attempt') != value['stage_attempt']
                or sha(canonical(observed)) != value['manifest_sha256']
                or manifest is not None and observed != manifest
                or digest is not None and value['manifest_sha256'] != digest):
            raise RuntimeError('Native stage manifest differs from the submitted bytes')
        for index, item in enumerate(value['files']):
            if (not isinstance(item, dict) or set(item) != {'index', 'published', 'verified'}
                    or type(item['index']) is not int or item['index'] != index
                    or type(item['published']) is not bool or type(item['verified']) is not bool
                    or item['verified'] and not item['published']):
                raise RuntimeError('Invalid native staged-file observations')
        if value['complete'] != all(item['verified'] for item in value['files']):
            raise RuntimeError('Native stage completion disagrees with its files')
        return value

    def put_file(self, attempt, index, payload, manifest, digest):
        if not hex_pin(attempt, 32) or type(index) is not int or not 0 <= index < 8:
            raise ValueError('Pin an allowed native staged file')
        file = manifest['files'][index]
        if len(payload) != file['bytes'] or sha(payload) != file['sha256']:
            raise ValueError('Native staged payload differs from the manifest')
        code, value = self.request('PUT', f'/native-lifecycle/stage/{attempt}/files/{index}', payload,
                                   digest=file['sha256'])
        if code not in (200, 201):
            raise RuntimeError('Invalid native staged-file acknowledgement')
        return self._stage(value, manifest, digest)

    def operation(self, stage_attempt, operation, request):
        if not hex_pin(stage_attempt, 32) or operation not in ('install', 'launch'):
            raise ValueError('Choose a native install or launch stage')
        code, value = self.request('POST', f'/native-lifecycle/stage/{stage_attempt}/{operation}', canonical(request))
        if code != 202:
            raise RuntimeError('Native operation did not receive queue acknowledgement')
        return self._operation(value, request, stage_attempt, operation)

    def inspect_operation(self, attempt, request=None, stage_attempt=None, operation=None):
        if not hex_pin(attempt, 32):
            raise ValueError('Pin the original native operation attempt')
        code, value = self.request('GET', '/native-lifecycle/attempt/' + attempt)
        if code != 200:
            raise RuntimeError('Invalid native operation inspection acknowledgement')
        return self._operation(value, request, stage_attempt, operation)

    def _operation(self, value, request, stage_attempt, operation):
        self._common(value)
        if (not hex_pin(value.get('attempt'), 32) or not hex_pin(value.get('stage_attempt'), 32)
                or not hex_pin(value.get('manifest_sha256'), 64) or not hex_pin(value.get('resident_build_id'), 64)
                or not hex_pin(value.get('instance_id'), 32) or value.get('operation') not in ('install', 'launch')
                or value.get('state') not in STATES or type(value.get('dispatch_count')) is not int
                or not 0 <= value['dispatch_count'] <= 1
                or any(type(value.get(k)) is not int for k in ('issued_ms', 'expires_ms', 'native_result', 'operation_result', 'cleanup_result'))
                or not 0 <= value['issued_ms'] < value['expires_ms'] <= value['issued_ms'] + 30000
                or type(value.get('installed_verified')) is not bool or type(value.get('may_have_effects')) is not bool
                or type(value.get('native_invoked')) is not bool):
            raise RuntimeError('Invalid native operation receipt')
        if (request is not None and (any(value.get(k) != request[k] for k in
                                       ('attempt', 'manifest_sha256', 'resident_build_id', 'instance_id', 'issued_ms'))
                                     or value['expires_ms'] != request['issued_ms'] + request['ttl_ms'])
                or stage_attempt is not None and value['stage_attempt'] != stage_attempt
                or operation is not None and value['operation'] != operation):
            raise RuntimeError('Native operation receipt differs from the pinned intent')
        if value['state'] in ('installed_verified', 'submitted'):
            if (value['dispatch_count'] != 1 or value['native_result'] < 0 or value['operation_result'] < 0
                    or not value['may_have_effects'] or not value['native_invoked']
                    or value['cleanup_result'] != 0
                    or value['state'] == 'installed_verified' and (value['operation'] != 'install'
                                                                 or value['operation_result'] != 0
                                                                 or not value['installed_verified'])
                    or value['state'] == 'submitted' and (value['operation'] != 'launch'
                                                        or value['installed_verified'])):
                raise RuntimeError('Native success receipt lacks separate submission and verification proof')
        return value

    def lab_status(self, expected_build, expected_version):
        code, value = self.request('GET', '/status', lab=True)
        self._lab(value, expected_build, expected_version)
        if code != 200 or value['exiting']:
            raise RuntimeError('Native lab is exiting or unavailable')
        return value

    @staticmethod
    def _lab(value, expected_build, expected_version):
        fields = {'app', 'protocol', 'title_id', 'version', 'native_build_id', 'pid', 'run',
                  'revision', 'frame', 'sampled_ms', 'paused', 'selftest_passed', 'checksum', 'exiting',
                  'variant', 'exit_expected_revision', 'exit_response_complete'}
        if (set(value) not in (fields, fields | {'exit_response'})
                or value.get('app') != 'Vita Native Lifecycle Lab' or type(value.get('protocol')) is not int
                or value['protocol'] != 1 or value.get('title_id') != TITLE or value.get('version') != expected_version
                or value.get('native_build_id') != expected_build or not hex_pin(expected_build, 64)
                or not hex_pin(value.get('run'), 32)
                or any(type(value.get(k)) is not int or value[k] <= 0 for k in ('pid', 'revision', 'frame'))
                or type(value.get('sampled_ms')) is not int or value['sampled_ms'] < 0
                or type(value.get('checksum')) is not int or value['checksum'] < 0
                or type(value.get('variant')) is not int or not 1 <= value['variant'] <= 0xffffffff
                or type(value.get('exit_expected_revision')) is not int
                or not 0 <= value['exit_expected_revision'] <= 0xffffffff
                or value['exit_expected_revision'] > 0 and value['revision'] != value['exit_expected_revision'] + 1
                or value.get('paused') is not True or type(value.get('selftest_passed')) is not bool
                or type(value.get('exiting')) is not bool
                or type(value.get('exit_response_complete')) is not bool
                or value['exit_response_complete'] and not value['exiting']
                or value['exiting'] and value['exit_expected_revision'] == 0):
            raise RuntimeError('Invalid native lab runtime identity or observations')

    def lab_exit(self, state):
        body = {'expected_native_build_id': state['native_build_id'], 'expected_pid': state['pid'],
                'expected_run': state['run'], 'expected_revision': state['revision']}
        code, value = self.request('POST', '/exit', canonical(body), lab=True)
        self._lab(value, state['native_build_id'], state['version'])
        if (code != 200 or value.get('exit_response') != 'acknowledged' or value['exiting'] is not True
                or any(value[k] != state[k] for k in ('pid', 'run'))
                or value['variant'] != state['variant']
                or value['exit_expected_revision'] != state['revision'] or value['revision'] != state['revision'] + 1):
            raise RuntimeError('Native lab exit receipt differs from its owned runtime')
        return value
