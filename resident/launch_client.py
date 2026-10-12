"""Control-free preparation; the future launch adapter is never inferred or retried.

Resident 0.1.2 does not implement this broker protocol. The installed plugin is
left untouched. The disabled 0.1.3 native qualification build still refuses launching.
Transport fixtures are not evidence of successful native app launching.
"""
from __future__ import annotations

import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


class BrokerUnavailable(RuntimeError):
    pass


class BrokerRejected(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(f'Launch broker rejected request with HTTP {code}')


def configuration():
    path = Path(os.environ.get('VITA_RESIDENT_CONFIG', str(ROOT / '.devloop-private/resident.json')))
    try:
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        host = ipaddress.IPv4Address(value['host'])
        if not (host.is_private or host.is_loopback) or host.is_unspecified or host.is_multicast:
            raise ValueError()
        if type(value['port']) is not int or not 1 <= value['port'] <= 65535 or not isinstance(value['token'], str) or not re.fullmatch('[0-9a-f]{32}', value['token']):
            raise ValueError()
        return {'host': str(host), 'port': value['port'], 'token': value['token']}
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise RuntimeError('Resident endpoint is not configured') from error


class BrokerClient:
    def __init__(self, provider=configuration):
        self.provider = provider
        self.endpoint = dict(provider())

    def check_endpoint(self):
        if self.provider() != self.endpoint:
            raise RuntimeError('Resident endpoint configuration changed')

    def request(self, path, body=None, *, inspect_original=False):
        if not inspect_original:
            self.check_endpoint()
        connection = http.client.HTTPConnection(self.endpoint['host'], self.endpoint['port'], timeout=7)
        try:
            raw = None if body is None else json.dumps(body, separators=(',', ':'), allow_nan=False).encode()
            connection.request('GET' if raw is None else 'POST', path, raw,
                               {'Authorization': 'Bearer ' + self.endpoint['token'],
                                'Content-Type': 'application/json', 'Connection': 'close'})
            response = connection.getresponse()
            data = response.read(8193)
            if response.status in (404, 405):
                raise BrokerUnavailable('Installed Resident has no qualified launch broker')
            if response.status not in (200, 202):
                raise BrokerRejected(response.status)
            if len(data) > 8192 or response.getheader('Content-Type', '').split(';')[0] != 'application/json':
                raise RuntimeError('Launch broker response exceeded its protocol bounds')
            value = json.loads(data)
            if not isinstance(value, dict):
                raise RuntimeError('Invalid launch broker response')
            return response.status, value
        except (OSError, http.client.HTTPException) as error:
            raise RuntimeError('Launch broker connection interrupted; inspect the attempt without replay') from error
        finally:
            connection.close()

    def status(self):
        _, value = self.request('/devloop-launch/status')
        if (value.get('app') != 'Vita Resident Launch Broker' or type(value.get('protocol')) is not int or value['protocol'] != 1
                or not isinstance(value.get('resident_build_id'), str) or not re.fullmatch('[0-9a-f]{64}', value['resident_build_id'])
                or not isinstance(value.get('instance_id'), str) or not re.fullmatch('[0-9a-f]{32}', value['instance_id'])
                or type(value.get('enabled')) is not bool or type(value.get('now_ms')) is not int or value['now_ms'] < 0):
            raise RuntimeError('Invalid launch broker identity')
        return value

    def offer(self, request):
        code, receipt = self.request('/devloop-launch', request)
        if code != 202:
            raise RuntimeError('Launch request did not receive queue acceptance')
        return receipt

    def inspect(self, attempt):
        return self.request('/devloop-launch/' + attempt, inspect_original=True)[1]


def _hex(value, size, reason):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{' + str(size) + '}', value):
        raise ValueError(reason)


def _transport_unavailable(error):
    # Foreground configuration failures use a distinct RuntimeError subclass;
    # an underlying missing-file error must never authorize app launching.
    return isinstance(error, OSError) or (type(error) is RuntimeError and
        isinstance(error.__cause__, (OSError, http.client.HTTPException)))


def prepare_script_session(expected_devloop_build, *, allow_launch=False,
                           expected_resident_build=None, expected_resident_instance=None,
                           timeout_s=15, device=None, broker=None, root=None):
    """Observe an open runtime, or explicitly request one future fixed-title launch.

    Polling is bounded; individual HTTP requests retain their socket deadlines.
    This function never edits Lua, installs a package, uses Control or changes
    power settings. A launch receipt cannot establish the installed app build.
    """
    from workbench.runner import Journal, WORKDIR, devloop_runtime_identity
    from workbench.session import exclusive
    from workbench.script_session import ForegroundDevice

    _hex(expected_devloop_build, 64, 'Pin the exact DevLoop native build')
    if type(allow_launch) is not bool or type(timeout_s) is not int or not 2 <= timeout_s <= 60:
        raise ValueError('Choose explicit launch intent and a 2..60 second timeout')
    if allow_launch:
        _hex(expected_resident_build, 64, 'Pin the future Resident broker build before launch')
        _hex(expected_resident_instance, 32, 'Pin the native Resident instance before launch')

    with exclusive():
        d = device or ForegroundDevice()
        j = Journal(root or WORKDIR, 'prepare-script-session')
        j.report.update(result='blocked', ready_for_script_reload=False, ready_for_input_trial=False,
                        allow_launch=allow_launch, launch_submissions=0, input_actions=0,
                        script_actions=0, native_installation='not performed',
                        keep_awake='not available without qualified Control',
                        expected_devloop_build=expected_devloop_build)
        j.save()
        deadline = time.monotonic() + timeout_s
        prior = None
        receipt = None
        attempt = None

        def observation():
            state = d.status()
            script = d.script()
            identity = devloop_runtime_identity(state, expected_devloop_build)
            if identity != devloop_runtime_identity(script, expected_devloop_build):
                raise RuntimeError('DevLoop status and script identities differ')
            if (state.get('paused') is not True or script.get('paused') is not True or script.get('faulted') is not False
                    or type(state.get('revision')) is not int or state['revision'] <= 0
                    or script.get('revision') != state['revision'] or type(state.get('frame')) is not int
                    or state['frame'] <= 0 or type(script.get('frame')) is not int or script['frame'] < state['frame']
                    or type(script.get('loaded')) is not bool or type(script.get('active')) is not bool
                    or script['active'] and not script['loaded']
                    or state.get('experiment') not in ('lua', 'tilt_playground')
                    or (state['experiment'] == 'lua') != script['active']
                    or not isinstance(script.get('name'), str) or not isinstance(script.get('sha256'), str)
                    or type(script.get('source_bytes')) is not int or not 0 <= script['source_bytes'] <= 16384
                    or script['loaded'] and (not re.fullmatch('[A-Za-z0-9_-]{1,32}', script['name'])
                                             or not re.fullmatch('[0-9a-f]{64}', script['sha256'])
                                             or not script['source_bytes'])
                    or not script['loaded'] and (script['name'] or script['sha256'] or script['source_bytes'])):
                raise RuntimeError('DevLoop must be healthy, sampled and already paused')
            return state, script, identity

        def owned_receipt(value, offer):
            if (not isinstance(value, dict) or any(value.get(k) != offer[k] for k in
                    ('attempt', 'title_id', 'expected_devloop_build', 'resident_build_id', 'instance_id'))
                    or value.get('state') not in ('queued', 'dispatch_intent', 'submitted', 'observed_script_only',
                                                 'native_rejected', 'unknown', 'cancelled_before_submission', 'expired_before_submission')):
                raise RuntimeError('Launch receipt does not match the pinned attempt')
            return {**{k: offer[k] for k in ('attempt', 'title_id', 'expected_devloop_build', 'resident_build_id', 'instance_id')},
                    'state': value['state']}

        try:
            foreground_endpoint = d.freeze_endpoint()
            try:
                prior = observation()
            except Exception as error:
                # Protocol/auth/build/running-scene failures never authorize launch.
                if not _transport_unavailable(error):
                    raise
                if not allow_launch:
                    raise RuntimeError('DevLoop is unavailable; launch intent was not supplied') from error
                b = broker or BrokerClient()
                if b.endpoint['host'] != foreground_endpoint['host']:
                    raise RuntimeError('DevLoop and launch broker must address the same Vita')
                baseline = b.status()
                if (baseline['resident_build_id'] != expected_resident_build
                        or baseline['instance_id'] != expected_resident_instance or not baseline['enabled']):
                    raise RuntimeError('Launch broker identity is unpinned or disabled')
                second = b.status()
                if (second['resident_build_id'] != baseline['resident_build_id'] or second['instance_id'] != baseline['instance_id']
                        or not second['enabled'] or second['now_ms'] < baseline['now_ms']):
                    raise RuntimeError('Launch broker changed before submission')
                d.check_endpoint()
                attempt = uuid.uuid4().hex
                offer = {'attempt': attempt, 'title_id': 'CHRS00003', 'expected_devloop_build': expected_devloop_build,
                         'resident_build_id': expected_resident_build, 'instance_id': expected_resident_instance,
                         'issued_ms': second['now_ms'], 'ttl_ms': 5000}
                j.event('launch_intent', offer)
                j.report.update(attempt=attempt, launch_submissions=1)
                j.save()
                try:
                    receipt = owned_receipt(b.offer(offer), offer)
                    j.event('launch_queue_receipt', {'receipt': receipt})
                except BrokerRejected:
                    raise
                except Exception as error:
                    if not _transport_unavailable(error):
                        raise
                    j.event('launch_reply_unconfirmed', {'failure_type': type(error).__name__, 'replayed': False})
                    receipt = owned_receipt(b.inspect(attempt), offer)
                while time.monotonic() < deadline:
                    b.check_endpoint()
                    current_broker = b.status()
                    if (current_broker['resident_build_id'] != expected_resident_build
                            or current_broker['instance_id'] != expected_resident_instance or not current_broker['enabled']):
                        raise RuntimeError('Launch broker restarted or changed after submission')
                    receipt = owned_receipt(b.inspect(attempt), offer)
                    if receipt['state'] in ('submitted', 'observed_script_only'):
                        break
                    if receipt['state'] in ('native_rejected', 'unknown', 'cancelled_before_submission', 'expired_before_submission'):
                        raise RuntimeError('Launch attempt ended without confirmed native submission')
                    time.sleep(.1)
                if receipt['state'] not in ('submitted', 'observed_script_only'):
                    raise RuntimeError('Launch attempt readiness timed out; do not replay')
                j.report['launch_receipt'] = receipt

            while time.monotonic() < deadline:
                try:
                    current = observation()
                except Exception as error:
                    if attempt is None or not _transport_unavailable(error):
                        raise
                    time.sleep(.1)
                    continue
                if prior is not None:
                    before_state, before_script, before_identity = prior
                    state, script, identity = current
                    if (identity != before_identity or state['revision'] != before_state['revision']
                            or any(script[key] != before_script[key] for key in ('sha256', 'name', 'source_bytes', 'loaded', 'active'))):
                        raise RuntimeError('DevLoop scene/session changed during preparation')
                    if state['frame'] > before_script['frame']:
                        j.report.update(result='script_ready', ready_for_script_reload=True,
                                        runtime_identity=identity, expected_revision=state['revision'],
                                        source_sha256=script.get('sha256'),
                                        foreground_mapping='native self-reported identity; no Control capture/input qualification')
                        break
                prior = current
                time.sleep(.1)
            if not j.report['ready_for_script_reload']:
                raise RuntimeError('Paused DevLoop did not show advancing frames before deadline')
        except Exception as error:
            j.report.update(result='blocked', failure_type=type(error).__name__)
            # Never reflect native errors, addresses, credentials or arbitrary source.
            j.report['failure'] = 'Preparation stopped; inspect the pinned attempt and runtime before another job'
        finally:
            d.close_endpoint()
        j.save()
        return {**j.report, 'evidence_directory': str(j.folder)}
