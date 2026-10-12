"""Bounded, script-only iterations through the existing DevLoop 01.04 API.

No Control service, launch, capture, synthetic input, power lease or native
installation is involved.  The caller first opens DevLoop and pins its exact
build, process, run and paused revision.  The shared local Workbench lock is
held for the whole job.  It is not a native/remote scene lease: revision/hash
checks detect competing edits, but cannot remove another client's request race.

Each candidate is restored to the original paused scene before the next load,
preserving the original VM in DevLoop's single rollback slot.  Native fallback
retains the last Lua VM inactive; the protocol cannot unload it or preserve an
older rollback history.  Uncertain writes are inspected with GET only, never
replayed, and do not authorize subsequent cleanup or iteration.
"""
from __future__ import annotations

import hashlib
import importlib.util
import ipaddress
import math
import re
import sys
import time
import uuid
from pathlib import Path

from .runner import Journal, ROOT, WORKDIR, check_devloop_runtime, predicates, utc
from .session import exclusive

LIMITS = {'candidates': 8, 'source_bytes': 16384, 'checks': 8,
          'duration_s': [0.25, 30], 'warmup_s': [0, 3], 'aggregate_s': 120}
LIMITATIONS = [
    'Script-only: no launch, installation, screenshot, synthetic input or foreground-focus proof.',
    'No Control dependency: remote input/work leases, wake, screen brightness and keepawake are unsupported.',
    'No remote scene lease exists; the local lock and revision/hash checks cannot eliminate another client request race.',
    'Sleep, a process restart, endpoint drift or an uncertain mutation stops the session without replay.',
    'Native restoration retains the last Lua VM inactive; earlier rollback history cannot be preserved.',
    'Retain-best loads the selected source into a fresh VM paused; metrics describe its earlier measured run.'
]


class ForegroundDevice:
    """Dedicated existing foreground bridge; importing it does not load Control."""
    def __init__(self):
        sys.path.insert(0, str(ROOT / 'bridge'))
        name = 'vita_script_session_foreground_' + uuid.uuid4().hex
        spec = importlib.util.spec_from_file_location(name, ROOT / 'bridge/server.py')
        self.foreground = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.foreground)

    def freeze_endpoint(self):
        if not hasattr(self, '_script_session_endpoint'):
            self._script_session_endpoint = _Endpoint(self)
        self._script_session_endpoint.check()
        return dict(self._script_session_endpoint.pin)

    def check_endpoint(self):
        if hasattr(self, '_script_session_endpoint'): self._script_session_endpoint.check()

    def close_endpoint(self):
        if hasattr(self, '_script_session_endpoint'):
            self._script_session_endpoint.close()
            del self._script_session_endpoint

    def status(self):
        self.check_endpoint()
        return self.foreground.vita_status()

    def script(self):
        self.check_endpoint()
        return self.foreground.vita_script_status()
    def load(self, name, source, revision):
        self.check_endpoint()
        return self.foreground.vita_load_script(name, source, revision)

    def resume(self, revision):
        self.check_endpoint()
        return self.foreground.vita_run_experiment('resume', revision)

    def pause(self, revision):
        self.check_endpoint()
        return self.foreground.vita_run_experiment('pause', revision)

    def restore(self, action, revision):
        self.check_endpoint()
        return self.foreground.vita_script_control(action, revision)


class SessionStopped(RuntimeError):
    """Stable public failure code, without remote text or endpoint credentials."""
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class UncertainMutation(SessionStopped): pass
class RuntimeFault(SessionStopped): pass


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate(candidates, expected_devloop_build, expected_pid, expected_run,
             expected_revision, retain_best=False, selection=None):
    """Validate every source/predicate before any configuration or network read."""
    if not isinstance(expected_devloop_build, str) or not re.fullmatch('[0-9a-f]{64}', expected_devloop_build):
        raise ValueError('expected_devloop_build must be an exact lowercase SHA-256')
    if type(expected_pid) is not int or not 1 <= expected_pid <= 0x7fffffff:
        raise ValueError('expected_pid must be a positive native PID')
    if not isinstance(expected_run, str) or not re.fullmatch('[0-9a-f]{32}', expected_run):
        raise ValueError('expected_run must be the exact 32-hex native run token')
    if type(expected_revision) is not int or not 1 <= expected_revision < 0xffffffff:
        raise ValueError('expected_revision must be a positive revision with mutation headroom')
    if type(retain_best) is not bool:
        raise ValueError('retain_best must be boolean')
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= LIMITS['candidates']:
        raise ValueError('Supply 1..8 bounded candidate scenes')
    if selection is not None and (not isinstance(selection, dict) or set(selection) != {'metric', 'direction'} or
            not isinstance(selection['metric'], str) or not re.fullmatch('[A-Za-z0-9_]{1,24}', selection['metric']) or
            selection['direction'] not in ('min', 'max')):
        raise ValueError('selection requires only metric and direction (min or max)')
    normalized = []
    names = set()
    for item in candidates:
        if not isinstance(item, dict) or set(item) - {'name', 'source', 'source_sha256', 'duration_s', 'warmup_s', 'checks'}:
            raise ValueError('Unknown candidate fields')
        name = item.get('name')
        source = item.get('source')
        if not isinstance(name, str) or not re.fullmatch('[A-Za-z0-9_-]{1,32}', name) or name in names:
            raise ValueError('Candidate names must be unique 1..32 ASCII identifiers')
        names.add(name)
        if not isinstance(source, str): raise ValueError('Candidate source must be UTF-8 text')
        try: raw = source.encode('utf-8')
        except UnicodeError as error: raise ValueError('Candidate source must be valid UTF-8') from error
        digest = hashlib.sha256(raw).hexdigest()
        if not 0 < len(raw) <= LIMITS['source_bytes'] or any(v < 32 and v not in (9, 10, 13) for v in raw):
            raise ValueError('Candidate source must contain 1..16384 UTF-8 bytes without binary controls')
        if item.get('source_sha256') != digest:
            raise ValueError('Candidate source_sha256 differs from exact UTF-8 source bytes')
        duration = item.get('duration_s', 1)
        warmup = item.get('warmup_s', 0.25)
        if not _number(duration) or not 0.25 <= duration <= 30 or not _number(warmup) or not 0 <= warmup <= 3:
            raise ValueError('duration_s must be 0.25..30; warmup_s must be 0..3')
        checks = item.get('checks')
        if not isinstance(checks, list) or not 1 <= len(checks) <= 8:
            raise ValueError('Each candidate needs 1..8 metric predicates')
        for check in checks:
            if (not isinstance(check, dict) or set(check) - {'metric', 'min', 'max', 'equals'} or
                    not isinstance(check.get('metric'), str) or not re.fullmatch('[A-Za-z0-9_]{1,24}', check['metric']) or
                    not set(check) & {'min', 'max', 'equals'} or
                    any(not _number(value) for key, value in check.items() if key != 'metric') or
                    ('min' in check and 'max' in check and check['min'] > check['max'])):
                raise ValueError('Invalid finite metric predicate')
        normalized.append({'name': name, 'source': source, 'source_sha256': digest,
                           'source_bytes': len(raw), 'duration_s': duration, 'warmup_s': warmup,
                           'checks': [dict(check) for check in checks]})
    if sum(c['duration_s'] + c['warmup_s'] for c in normalized) > 120:
        raise ValueError('Aggregate warmup plus measurement must not exceed 120 seconds')
    return normalized, dict(selection) if selection is not None else None


class _Endpoint:
    def __init__(self, device):
        self.module = device.foreground
        self.previous_configuration = self.module.configuration
        existing = getattr(device, '_script_session_endpoint', None)
        self.provider = existing.provider if existing is not None else self.module.configuration
        self.pin = self._read()
        self.module.configuration = lambda: dict(self.pin)

    def _read(self):
        try:
            value = self.provider()
            host = ipaddress.IPv4Address(value['host'])
            if (not (host.is_private or host.is_loopback) or host.is_unspecified or host.is_multicast or
                    type(value['port']) is not int or not 1 <= value['port'] <= 65535 or
                    not isinstance(value['token'], str) or not re.fullmatch('[0-9a-f]{32}', value['token'])):
                raise ValueError()
            return {'host': str(host), 'port': value['port'], 'token': value['token']}
        except Exception as error:
            raise SessionStopped('endpoint_configuration_invalid') from error

    def check(self):
        if self._read() != self.pin: raise SessionStopped('endpoint_configuration_changed')

    def close(self): self.module.configuration = self.previous_configuration


def _scene(script):
    return {key: script[key] for key in ('revision', 'sha256', 'name', 'source_bytes', 'loaded', 'active', 'paused', 'faulted')}


def _native(status):
    keys = ('parameters', 'ball', 'score', 'added_obstacles', 'mode')
    if any(key not in status for key in keys): raise SessionStopped('native_snapshot_invalid')
    return {key: status[key] for key in keys}


def _metrics(script):
    metrics = script.get('metrics')
    if (not isinstance(metrics, dict) or len(metrics) > 8 or
            any(not isinstance(k, str) or not re.fullmatch('[A-Za-z0-9_]{1,24}', k) or not _number(v)
                for k, v in metrics.items())):
        raise SessionStopped('metrics_invalid')
    return dict(metrics)


class _Job:
    def __init__(self, device, journal, pin):
        self.d = device
        self.j = journal
        self.pin = pin
        self.endpoint = _Endpoint(device)
        self.owned = None
        self.frame = 0
        self.sampled_ms = 0
        self.uncertain = False
        self.stopped = False
        self.original = None
        self.original_native = None
        self.scene_changed = False

    def _identity(self, value):
        try: check_devloop_runtime(value, self.pin)
        except Exception as error: raise SessionStopped('runtime_identity_changed_or_invalid') from error
        if (type(value.get('revision')) is not int or not 1 <= value['revision'] <= 0xffffffff or
                type(value.get('frame')) is not int or value['frame'] <= 0 or
                type(value.get('sampled_ms')) is not int or value['sampled_ms'] < 0 or
                value['frame'] < self.frame or value['sampled_ms'] < self.sampled_ms):
            raise SessionStopped('runtime_sample_regressed_or_invalid')
        self.frame = value['frame']
        self.sampled_ms = value['sampled_ms']

    def observe(self, check_owner=True):
        self.endpoint.check()
        status = self.d.status()
        self._identity(status)
        self.endpoint.check()
        script = self.d.script()
        self._identity(script)
        for key in ('loaded', 'active', 'paused', 'faulted', 'rollback_available'):
            if type(script.get(key)) is not bool: raise SessionStopped('script_snapshot_invalid')
        if (type(status.get('paused')) is not bool or script['revision'] != status['revision'] or
                script['paused'] != status['paused'] or (status.get('experiment') == 'lua') != script['active'] or
                type(script.get('source_bytes')) is not int or not 0 <= script['source_bytes'] <= 16384 or
                type(script.get('updates')) is not int or script['updates'] < 0 or
                not isinstance(script.get('name'), str) or not isinstance(script.get('sha256'), str) or
                (script['loaded'] and (not re.fullmatch('[A-Za-z0-9_-]{1,32}', script['name']) or
                                      not re.fullmatch('[0-9a-f]{64}', script['sha256']) or not script['source_bytes'])) or
                (not script['loaded'] and (script['active'] or script['name'] or script['sha256'] or script['source_bytes']))):
            raise SessionStopped('script_snapshot_invalid')
        _metrics(script)
        if check_owner:
            if self.owned is None: raise SessionStopped('scene_ownership_unconfirmed')
            expected = dict(self.owned)
            if (self.scene_changed and script['faulted'] and not self.owned['faulted'] and
                    script['paused'] and self.owned['active']):
                # The core pauses our own fault exactly once; no other revision is adopted.
                if script['revision'] == expected['revision'] + 1:
                    expected.update(revision=script['revision'], paused=True, faulted=True)
            if _scene(script) != expected:
                raise SessionStopped('scene_ownership_changed')
        return status, script

    def adopt_fault(self, script):
        if script['faulted']:
            if not script['paused'] or not self.owned['active']:
                raise SessionStopped('unexpected_fault_state')
            self.owned = _scene(script)
            raise RuntimeFault('candidate_runtime_fault')

    def mutation(self, operation, expected_scene, call, fields=None, reject_load=False):
        _, before = self.observe()
        if before['faulted'] and not self.owned['faulted']:
            self.adopt_fault(before)
        if self.owned['revision'] == 0xffffffff: raise SessionStopped('revision_exhausted')
        self.endpoint.check()
        revision = self.owned['revision']
        self.j.event('mutation_intent', {'operation': operation, 'expected_revision': revision, **(fields or {})})
        # A receipt journal failure also leaves the mutation uncertain. Never replay.
        try:
            receipt = call(revision)
        except Exception as error:
            if reject_load and isinstance(error, RuntimeError) and str(error).startswith('Vita HTTP 422:'):
                self.j.event('candidate_rejected', {'operation': operation, 'failure_type': type(error).__name__})
                self.observe()
                return None
            self._uncertain(operation, type(error).__name__, expected_scene)
        try:
            self._identity(receipt)
            if operation in ('pause', 'resume'):
                valid = (receipt.get('revision') == expected_scene['revision'] and
                         receipt.get('paused') is expected_scene['paused'] and
                         (receipt.get('experiment') == 'lua') == expected_scene['active'])
            else:
                valid = _scene(receipt) == expected_scene
            if not valid:
                raise SessionStopped('mutation_receipt_invalid')
            self.j.event('mutation_receipt', {'operation': operation, 'receipt': receipt})
        except Exception as error:
            self._uncertain(operation, type(error).__name__, expected_scene)
        self.owned = dict(expected_scene)
        self.scene_changed = True
        self.observe()
        return receipt

    def _uncertain(self, operation, failure_type, expected):
        self.uncertain = True
        self.scene_changed = True
        self.owned = None
        self.j.event('mutation_unconfirmed', {'operation': operation, 'failure_type': failure_type, 'replayed': False})
        try:
            _, script = self.observe(check_owner=False)
            observed = 'expected_post_state_observed' if _scene(script) == expected else 'different_state_observed'
            self.j.event('read_only_reconciliation', {'operation': operation, 'observation': observed,
                                                     'scene': _scene(script), 'ownership_adopted': False})
            self.j.report['reconciliation'] = observed
        except Exception as error:
            self.j.report['reconciliation'] = 'readback_unavailable_or_drifted'
            self.j.event('read_only_reconciliation', {'operation': operation, 'failure_type': type(error).__name__,
                                                     'ownership_adopted': False})
        raise UncertainMutation('mutation_outcome_unconfirmed_no_replay')

    def load(self, candidate):
        expected = {'revision': self.owned['revision'] + 1, 'sha256': candidate['source_sha256'],
                    'name': candidate['name'], 'source_bytes': candidate['source_bytes'],
                    'loaded': True, 'active': True, 'paused': True, 'faulted': False}
        return self.mutation('load_script', expected,
                             lambda rev: self.d.load(candidate['name'], candidate['source'], rev),
                             {'name': candidate['name'], 'source_sha256': candidate['source_sha256']}, reject_load=True)

    def control(self, action, target=None):
        expected = dict(target or self.owned)
        expected.update(revision=self.owned['revision'] + 1, paused=action != 'resume')
        if action == 'native': expected['active'] = False
        if action in ('pause', 'resume'):
            call = self.d.resume if action == 'resume' else getattr(self.d, 'pause', None)
            if call is None: call = lambda rev: self.d.foreground.vita_run_experiment('pause', rev)
        else: call = lambda rev: self.d.restore(action, rev)
        return self.mutation(action, expected, call)

    def restore_original(self):
        _, current = self.observe()
        if current['faulted']: self.owned = _scene(current)
        if self.original['loaded']:
            if self.scene_changed:
                # Equal source/name can still be a fresh VM. Restore the retained
                # original object, never infer VM identity from source equality.
                if (current.get('previous_sha256') != self.original['sha256'] or
                        current.get('previous_name') != self.original['name'] or not current['rollback_available']):
                    raise SessionStopped('original_rollback_vm_unavailable')
                target = dict(self.original)
                target['active'] = True
                self.control('rollback', target)
            if not self.original['active'] and self.owned['active']: self.control('native')
            if not self.owned['paused']: self.control('pause')
        elif self.owned['active']:
            self.control('native')
        elif not self.owned['paused']:
            self.control('pause')
        status, current = self.observe()
        if (not current['paused'] or current['active'] != self.original['active'] or
                (self.original['loaded'] and any(current[k] != self.original[k]
                                                for k in ('sha256', 'name', 'source_bytes', 'loaded'))) or
                _native(status) != self.original_native):
            raise SessionStopped('original_scene_restoration_differs')
        self.scene_changed = False
        self.j.event('original_restored_paused', {'scene': _scene(current),
                                                'native_world_unchanged': True})
        self.j.report['restoration'] = 'original_scene_paused_verified'

    def measure(self, candidate):
        self.control('resume')
        time.sleep(candidate['warmup_s'])
        _, first = self.observe()
        self.adopt_fault(first)
        if first['paused']: raise SessionStopped('candidate_execution_paused')
        started = time.monotonic()
        deadline = started + candidate['duration_s']
        samples = []
        previous = first
        while time.monotonic() < deadline:
            time.sleep(min(0.25, max(0, deadline - time.monotonic())))
            _, script = self.observe()
            self.adopt_fault(script)
            if script['paused'] or script['frame'] <= previous['frame'] or script['updates'] <= previous['updates']:
                raise SessionStopped('candidate_execution_not_advancing')
            samples.append({'frame': script['frame'], 'sampled_ms': script['sampled_ms'],
                            'updates': script['updates'], 'metrics': _metrics(script)})
            previous = script
        self.control('pause')
        _, final = self.observe()
        if final['faulted']: self.adopt_fault(final)
        if final['updates'] < previous['updates']: raise SessionStopped('candidate_execution_regressed')
        metrics = _metrics(final)
        checks = predicates(candidate['checks'], metrics)
        self.j.event('candidate_measurement', {'name': candidate['name'], 'samples': samples,
                                              'final_scene': _scene(final), 'metrics': metrics, 'checks': checks})
        return {'samples': len(samples), 'first_frame': first['frame'], 'last_frame': final['frame'],
                'first_updates': first['updates'], 'last_updates': final['updates'],
                'elapsed_s': round(time.monotonic() - started, 3), 'metrics': metrics,
                'checks': checks, 'accepted': all(c['passed'] for c in checks)}


def run_session(candidates, expected_devloop_build, expected_pid, expected_run, expected_revision,
                *, retain_best=False, selection=None, device=None, root=WORKDIR):
    """Deploy, run, measure and rank supplied scenes; restore the original paused.

    Candidate objects contain name, source, source_sha256, checks, and optional
    duration_s/warmup_s. Unknown fields, invalid pins and unbounded plans raise
    ValueError before network access. Other outcomes return a sanitized report.
    Selection is {metric, direction: min|max}; absent selection picks the first
    accepted candidate. Ties retain the earliest candidate. retain_best explicitly
    loads that source into a fresh paused VM after all candidates were evaluated.
    """
    candidates, selection = validate(candidates, expected_devloop_build, expected_pid, expected_run,
                                     expected_revision, retain_best, selection)
    pin = {'app': 'Vita DevLoop', 'protocol': 1, 'version': '01.04', 'title_id': 'CHRS00003',
           'pid': expected_pid, 'run': expected_run, 'build_id': expected_devloop_build}
    with exclusive():
        j = Journal(Path(root), 'script-session')
        j.report.update(runtime_identity=pin, requested_revision=expected_revision, retain_best=retain_best,
                        selection=selection, limits=LIMITS, limitations=LIMITATIONS,
                        iterations=[], best=None, mutation_submissions=0,
                        restoration='not_needed_no_scene_mutation', input_actions=0, control_actions=0,
                        readiness='script_runtime_only', result='blocked')
        job = None
        started = time.monotonic()
        try:
            job = _Job(device or ForegroundDevice(), j, pin)
            status, script = job.observe(check_owner=False)
            if script['revision'] != expected_revision or not script['paused'] or script['faulted']:
                raise SessionStopped('baseline_revision_changed_running_or_faulted')
            job.owned = _scene(script)
            job.original = _scene(script)
            job.original_native = _native(status)
            j.report['original_scene'] = job.original
            first_frame = script['frame']
            time.sleep(0.1)
            _, script = job.observe()
            if script['frame'] <= first_frame: raise SessionStopped('baseline_frame_not_advancing')
            for index, candidate in enumerate(candidates):
                iteration = {k: candidate[k] for k in ('name', 'source_sha256', 'source_bytes', 'duration_s', 'warmup_s')}
                iteration.update(index=index, result='pending', accepted=False)
                j.report['iterations'].append(iteration)
                try:
                    if job.load(candidate) is None:
                        iteration['result'] = 'syntax_or_preflight_rejected'
                    else:
                        iteration.update(job.measure(candidate))
                        iteration['result'] = 'accepted' if iteration['accepted'] else 'metric_checks_failed'
                except RuntimeFault:
                    iteration['result'] = 'runtime_fault'
                if job.scene_changed:
                    job.restore_original()
                if iteration['accepted']:
                    value = iteration['metrics'].get(selection['metric']) if selection else None
                    if selection and not _number(value):
                        iteration.update(accepted=False, result='selection_metric_missing')
                    else:
                        best = j.report['best']
                        better = best is None or (selection is not None and
                            (value < best['selection_value'] if selection['direction'] == 'min' else value > best['selection_value']))
                        if better:
                            j.report['best'] = {'index': index, 'name': candidate['name'],
                                                'source_sha256': candidate['source_sha256'], 'selection_value': value}
                j.save()
            if retain_best and j.report['best'] is not None:
                chosen = candidates[j.report['best']['index']]
                if job.load(chosen) is None: raise SessionStopped('best_candidate_reload_rejected')
                _, retained = job.observe()
                if not retained['paused']: raise SessionStopped('retained_candidate_not_paused')
                j.report['restoration'] = 'best_source_retained_fresh_vm_paused'
                j.report['retained_scene'] = _scene(retained)
                job.scene_changed = False
            j.report['result'] = 'passed' if j.report['best'] is not None else 'failed_checks'
        except Exception as error:
            j.report.update(result='unconfirmed' if isinstance(error, UncertainMutation) else 'blocked',
                            failure_code=error.code if isinstance(error, SessionStopped) else 'transport_or_local_failure',
                            failure_type=type(error).__name__)
            if j.report['iterations'] and j.report['iterations'][-1]['result'] == 'pending':
                j.report['iterations'][-1]['result'] = 'stopped'
            if job is not None: job.stopped = True
        finally:
            if job is not None:
                if job.scene_changed and job.original is not None:
                    if job.uncertain or job.stopped:
                        j.report['restoration'] = 'skipped_unconfirmed_or_drifted_no_further_mutation'
                    else:
                        try: job.restore_original()
                        except Exception as error:
                            j.report.update(result='unconfirmed', restoration='skipped_or_unconfirmed_no_replay',
                                            cleanup_failure_type=type(error).__name__)
                job.endpoint.close()
            j.report['mutation_submissions'] = sum(e['kind'] == 'mutation_intent' for e in j.report['events'])
            j.report['elapsed_s'] = round(time.monotonic() - started, 3)
            j.report['finished_utc'] = utc()
            j.save()
        # Journal receipts stay private. Public metadata never includes source,
        # endpoint/configuration, remote exception text or arbitrary reply fields.
        return {key: value for key, value in j.report.items() if key != 'events'} | {'evidence_directory': str(j.folder)}
