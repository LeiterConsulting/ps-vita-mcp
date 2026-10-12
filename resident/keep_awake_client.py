"""Bounded Resident work leases; no status read renews a lease or wakes a Vita.

The dedicated listener keeps lease heartbeats separate from bulk file traffic.
Every mutation uses revision CAS and is sent once. A lost response stops work;
cleanup may only end the same owner after a fresh read, never replay a start.
"""
from __future__ import annotations

from datetime import datetime, timezone
import http.client
import json
import os
from pathlib import Path
import struct
import threading
import time
import uuid

from resident.launch_client import configuration
from resident.lifecycle_client import hex_pin
from workbench.native_package import json_object

APP = 'Vita Resident Keep Awake'
PORT = 17869
TTL_MS = 30000
MAX_DURATION_MS = 1800000


class KeepAwakeRejected(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__('Resident keep-awake request rejected with HTTP ' + str(status))


class KeepAwakeUnknown(RuntimeError):
    """An attempted effect has no trustworthy receipt and must not be replayed."""


class KeepAwakeLost(RuntimeError):
    pass


def pack(revision, ttl_ms, max_duration_ms, instance_id, lease_id, job_id):
    if (type(revision) is not int or not 0 <= revision < 0xffffffff
            or type(ttl_ms) is not int or ttl_ms != 0 and not 5000 <= ttl_ms <= TTL_MS
            or type(max_duration_ms) is not int
            or max_duration_ms != 0 and not 30000 <= max_duration_ms <= MAX_DURATION_MS
            or ttl_ms == 0 and max_duration_ms != 0
            or not all(hex_pin(value, 32) for value in (instance_id, lease_id, job_id))):
        raise ValueError('Invalid Resident lease revision, TTL, duration or ownership pins')
    return struct.pack('<8I32s32s32s', 0x31414b52, 1, revision, ttl_ms, max_duration_ms,
                       0, 0, 0, instance_id.encode('ascii'), lease_id.encode('ascii'), job_id.encode('ascii'))


def validate(value):
    integers = ('clock_ms', 'revision', 'remaining_ms', 'session_remaining_ms', 'last_tick_ms', 'tick_count')
    if (not isinstance(value, dict) or value.get('app') != APP
            or type(value.get('protocol')) is not int or value['protocol'] != 1
            or type(value.get('status')) is not int or value['status'] != 200 or value.get('error') is not None
            or 'error' not in value
            or type(value.get('port')) is not int or value['port'] != PORT
            or not hex_pin(value.get('resident_build_id'), 64) or not hex_pin(value.get('instance_id'), 32)
            or any(type(value.get(key)) is not int or value[key] < 0 for key in integers)
            or not 0 <= value['revision'] <= 0xffffffff or value['remaining_ms'] > TTL_MS
            or value['session_remaining_ms'] > MAX_DURATION_MS
            or value['remaining_ms'] > value['session_remaining_ms']
            or value['last_tick_ms'] > value['clock_ms']
            or type(value.get('tick_result')) is not int
            or not -0x80000000 <= value['tick_result'] <= 0x7fffffff
            or type(value.get('active')) is not bool
            or not isinstance(value.get('reason'), str) or not 1 <= len(value['reason']) <= 80):
        raise RuntimeError('Invalid Resident keep-awake status')
    if value['active']:
        if (not all(hex_pin(value.get(key), 32) for key in ('lease_id', 'job_id'))
                or value['remaining_ms'] == 0 or value['session_remaining_ms'] == 0):
            raise RuntimeError('Invalid active Resident lease owner or lifetime')
    elif (value.get('lease_id') is not None or value.get('job_id') is not None
          or value['remaining_ms'] != 0 or value['session_remaining_ms'] != 0):
        raise RuntimeError('Invalid inactive Resident lease state')
    return value


class KeepAwakeClient:
    def __init__(self, provider=configuration, *, port=PORT, timeout=2):
        self.provider = provider
        self.endpoint = dict(provider())
        self.port = port
        self.timeout = timeout
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('Invalid lease listener port')

    def check_endpoint(self):
        if self.provider() != self.endpoint:
            raise KeepAwakeLost('Resident endpoint configuration changed')

    def request(self, method, body=None):
        self.check_endpoint()
        connection = http.client.HTTPConnection(self.endpoint['host'], self.port, timeout=self.timeout)
        path = '/keep-awake/status' if method == 'GET' else '/keep-awake/lease'
        try:
            connection.request(method, path, body, {'Authorization': 'Bearer ' + self.endpoint['token'],
                                                   'Content-Type': 'application/octet-stream', 'Connection': 'close'})
            response = connection.getresponse()
            raw = response.read(8193)
            if response.status != 200:
                raise KeepAwakeRejected(response.status)
            if (len(raw) > 8192 or response.getheader('Content-Type', '').split(';')[0] != 'application/json'):
                raise RuntimeError('Invalid lease response bounds or content type')
            value = validate(json_object(raw))
            self.check_endpoint()
            return value
        except KeepAwakeRejected:
            raise
        except Exception as error:
            if method == 'POST':
                raise KeepAwakeUnknown('Resident lease reply unconfirmed; never replay the mutation') from error
            raise
        finally:
            connection.close()

    def status(self):
        return self.request('GET')

    def mutate(self, revision, ttl_ms, max_duration_ms, instance_id, lease_id, job_id, resident_build_id):
        body = pack(revision, ttl_ms, max_duration_ms, instance_id, lease_id, job_id)
        if not hex_pin(resident_build_id, 64):
            raise ValueError('Pin the exact Resident build ID')
        before = self.status()
        if (before['instance_id'] != instance_id or before['resident_build_id'] != resident_build_id
                or before['revision'] != revision):
            raise KeepAwakeLost('Resident lease instance, build or revision changed before mutation')
        if max_duration_ms:
            if before['active']:
                raise KeepAwakeLost('Another Resident work lease is active')
        elif (not before['active'] or before['lease_id'] != lease_id or before['job_id'] != job_id):
            raise KeepAwakeLost('Resident work lease owner changed or expired')
        value = self.request('POST', body)
        if (value['instance_id'] != instance_id or value['resident_build_id'] != resident_build_id
                or value['revision'] != revision + 1 or value['active'] != bool(ttl_ms)
                or ttl_ms and (value['lease_id'] != lease_id or value['job_id'] != job_id
                               or value['remaining_ms'] > ttl_ms or value['tick_result'] < 0)):
            raise KeepAwakeUnknown('Resident lease receipt differs; do not replay the mutation')
        return value


class ResidentKeeper:
    """A job owner with a 30-second renewable TTL and a fixed absolute ceiling.

    The thread owns only the lease endpoint. Work checks fail after heartbeat
    uncertainty, owner/instance drift, local expiry, or a dead renewal thread.
    No lease is restored after process death or reboot.
    """
    def __init__(self, client, folder, job_id, *, max_duration_ms=600000, interval=10):
        if (not hex_pin(job_id, 32) or type(max_duration_ms) is not int
                or not 30000 <= max_duration_ms <= MAX_DURATION_MS
                or not 0 < interval <= 10):
            raise ValueError('Invalid bounded Resident work lease')
        self.client, self.folder, self.job_id = client, Path(folder), job_id
        self.max_duration_ms, self.interval = max_duration_ms, interval
        self.lease_id = uuid.uuid4().hex
        self.end = threading.Event()
        self.lock = threading.RLock()
        self.thread = None
        self.value = None
        self.started = None
        self.observed = None
        self.failed = None
        self.expected_build = self.expected_instance = None
        self.result = {'enabled': False, 'ttl_ms': TTL_MS, 'max_duration_ms': max_duration_ms,
                       'job_id': job_id, 'lease_id': self.lease_id, 'renewals': 0, 'errors': []}

    def record(self, kind, **fields):
        self.folder.mkdir(parents=True, exist_ok=True)
        with (self.folder / 'resident-keep-awake.jsonl').open('a', encoding='utf-8') as output:
            output.write(json.dumps({'utc': datetime.now(timezone.utc).isoformat(), 'kind': kind, **fields},
                                    separators=(',', ':'), allow_nan=False) + '\n')
            output.flush()
            os.fsync(output.fileno())

    def _pin(self, value, *, owned=True):
        if value['resident_build_id'] != self.expected_build or value['instance_id'] != self.expected_instance:
            raise KeepAwakeLost('Resident lease instance or build changed')
        if owned and (not value['active'] or value['lease_id'] != self.lease_id or value['job_id'] != self.job_id
                      or value['tick_result'] < 0):
            raise KeepAwakeLost('Resident work lease expired, failed or changed owner')
        if self.value and value['clock_ms'] < self.value['clock_ms']:
            raise KeepAwakeLost('Resident lease clock regressed')
        return value

    def _send(self, ttl_ms, duration_ms=0):
        value = self.value
        self.record('lease_intent', revision=value['revision'], ttl_ms=ttl_ms, max_duration_ms=duration_ms,
                    instance_id=self.expected_instance, resident_build_id=self.expected_build,
                    lease_id=self.lease_id, job_id=self.job_id)
        try:
            if ttl_ms and self.end.is_set():
                raise KeepAwakeLost('Resident keeper stopped before lease submission')
            sent_at = time.monotonic()
            receipt = self.client.mutate(value['revision'], ttl_ms, duration_ms, self.expected_instance,
                                         self.lease_id, self.job_id, self.expected_build)
            self._pin(receipt, owned=bool(ttl_ms))
            self.record('lease_receipt', receipt=receipt)
        except Exception as error:
            self.record('lease_unconfirmed_or_rejected', ttl_ms=ttl_ms, failure_type=type(error).__name__,
                        replayed=False)
            raise
        # Native remaining_ms was sampled before the reply crossed the network.
        # Measuring from request start gives a conservative local expiry even
        # when a valid receipt was delayed or fragmented in transit.
        self.value, self.observed = receipt, sent_at
        return receipt

    def start(self, resident_build_id=None, instance_id=None):
        if self.started is not None:
            raise KeepAwakeLost('A Resident keeper cannot be started twice')
        with self.lock:
            self.started = time.monotonic()
            self.value = self.client.status()
            self.expected_build = resident_build_id or self.value['resident_build_id']
            self.expected_instance = instance_id or self.value['instance_id']
            self._pin(self.value, owned=False)
            if self.value['active']:
                raise KeepAwakeLost('Another Resident work lease is active')
            self._send(TTL_MS, self.max_duration_ms)
            self.result['enabled'] = True
            self.record('keeper_started', job_id=self.job_id, lease_id=self.lease_id)
            self.thread = threading.Thread(target=self._run, name='vita-resident-keep-awake', daemon=True)
            self.thread.start()
        return self.value

    def _run(self):
        while not self.end.wait(self.interval):
            with self.lock:
                try:
                    self._check_local()
                    self._send(TTL_MS)
                    self.result['renewals'] += 1
                except Exception as error:
                    self.failed = type(error).__name__
                    self.result['errors'].append(self.failed)
                    self.end.set()
                    return

    def _check_local(self):
        self.client.check_endpoint()
        now = time.monotonic()
        if (self.failed or not self.result['enabled'] or self.observed is None
                or now < self.observed or now < self.started
                or (now - self.observed) * 1000 >= self.value['remaining_ms']
                or (now - self.started) * 1000 >= self.max_duration_ms):
            raise KeepAwakeLost('Resident work lease is no longer confirmed')

    def check(self, *, fresh=False):
        with self.lock:
            self._check_local()
            if not self.thread or not self.thread.is_alive() or self.end.is_set():
                raise KeepAwakeLost('Resident renewal worker stopped')
            if fresh:
                sent_at = time.monotonic()
                value = self._pin(self.client.status())
                if value['revision'] != self.value['revision']:
                    raise KeepAwakeLost('Resident lease revision changed outside this keeper')
                self.value, self.observed = value, sent_at
                self._check_local()
            return dict(self.value)

    def stop(self):
        self.end.set()
        if self.thread:
            self.thread.join(timeout=self.client.timeout * 2 + 1)
        if self.thread and self.thread.is_alive():
            self.result['end'] = 'unconfirmed; expires within 30 seconds of last accepted renewal'
            return self.result
        with self.lock:
            if self.expected_instance is None:
                self.result['end'] = 'not_started'
                return self.result
            try:
                # A fresh GET may reconcile an uncertain accepted renewal/start.
                # Only the same owner can be ended, using its new revision CAS.
                observed = self._pin(self.client.status(), owned=False)
                if not observed['active']:
                    self.result['end'] = 'already_inactive'
                elif observed['lease_id'] != self.lease_id or observed['job_id'] != self.job_id:
                    self.result['end'] = 'owner_changed; no mutation'
                else:
                    self.value = observed
                    self._send(0)
                    self.result['end'] = 'ended'
            except Exception as error:
                self.result['end'] = 'unconfirmed; expires within 30 seconds of last accepted renewal'
                self.result['errors'].append(type(error).__name__)
        return self.result


def register(mcp, configuration, read_annotations, write_annotations):
    def client():
        return KeepAwakeClient(configuration)

    @mcp.tool(annotations=read_annotations)
    def vita_resident_keep_awake_status() -> dict:
        """Inspect the Resident lease, owner, revision and tick results. GET never renews or wakes a sleeping Vita. Requires Resident 0.1.6's dedicated listener."""
        return client().status()

    @mcp.tool(annotations=write_annotations)
    def vita_resident_keep_awake_begin(expected_revision: int, resident_build_id: str, instance_id: str,
                                      lease_id: str, job_id: str, max_duration_ms: int = 600000,
                                      ttl_ms: int = 30000) -> dict:
        """Start one admin-owned job lease from an inactive status. Supply fresh build/instance/revision and unique 32-hex lease/job IDs. TTL 5..30s; fixed total 30s..30min. Renew explicitly before TTL; no automatic retry after an uncertain reply."""
        if max_duration_ms == 0 or ttl_ms == 0:
            raise ValueError('Beginning a lease requires positive TTL and duration')
        return client().mutate(expected_revision, ttl_ms, max_duration_ms, instance_id, lease_id, job_id,
                               resident_build_id)

    @mcp.tool(annotations=write_annotations)
    def vita_resident_keep_awake_renew(expected_revision: int, resident_build_id: str, instance_id: str,
                                      lease_id: str, job_id: str, ttl_ms: int = 30000) -> dict:
        """Renew only this active lease owner with its current revision; the absolute deadline cannot move. Never retry an uncertain mutation; inspect status and end or let TTL expire."""
        if ttl_ms == 0:
            raise ValueError('Renewing a lease requires a positive TTL')
        return client().mutate(expected_revision, ttl_ms, 0, instance_id, lease_id, job_id, resident_build_id)

    @mcp.tool(annotations=write_annotations)
    def vita_resident_keep_awake_end(expected_revision: int, resident_build_id: str, instance_id: str,
                                    lease_id: str, job_id: str) -> dict:
        """End only the exact active owner with a fresh revision. Stops suspend timer refresh; normal configured sleep timing resumes. Never changes saved sleep or brightness settings."""
        return client().mutate(expected_revision, 0, 0, instance_id, lease_id, job_id, resident_build_id)


def _stop_command_tree(process):
    """Cancel only the live process tree started by this invocation."""
    import subprocess
    if os.name == 'nt':
        result = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], check=False,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        if result.returncode and process.poll() is None:
            raise KeepAwakeLost('Owned host command tree termination was not confirmed')
        process.wait(timeout=5)
    else:
        import signal
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        finally:
            # The group may still contain a child even after its leader exits.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=5)


def run_command(command, folder, *, client=None, max_duration_ms=600000):
    """Keep an awake Vita online during a bounded, possibly silent host build."""
    import subprocess
    if not command:
        raise ValueError('Provide a host command to run')
    keeper = ResidentKeeper(client or KeepAwakeClient(), folder, uuid.uuid4().hex,
                            max_duration_ms=max_duration_ms)
    process = None
    result = None
    try:
        keeper.start()
        keeper.check(fresh=True)
        process = subprocess.Popen(command, **({'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
                                                if os.name == 'nt' else {'start_new_session': True}))
        while process.poll() is None:
            keeper.check()
            time.sleep(0.1)
        keeper.check(fresh=True)
        result = {'returncode': process.returncode, 'job_id': keeper.job_id}
    finally:
        try:
            if process is not None and process.poll() is None:
                # Compiler/linker children are owned by this invocation.
                # Separate Docker-daemon container jobs need their own bound.
                _stop_command_tree(process)
        finally:
            ended = keeper.stop()
            if result is not None:
                result['keep_awake'] = ended
                if ended.get('end') not in ('ended', 'already_inactive'):
                    raise KeepAwakeLost('Host command finished but Resident lease end is unconfirmed')
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-duration-ms', type=int, default=600000)
    parser.add_argument('--journal-dir', type=Path, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    result = run_command(command, args.journal_dir, max_duration_ms=args.max_duration_ms)
    print(json.dumps(result, allow_nan=False))
    return result['returncode']


if __name__ == '__main__':
    raise SystemExit(main())
