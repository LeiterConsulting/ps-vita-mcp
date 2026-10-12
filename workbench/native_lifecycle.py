"""Hash-bound native lab deployment, evaluation and graceful redeployment.

Only VMCP00001 is supported. Accepted applications, boot configuration and
Control are outside this runner. Every native mutation has a durable local
intent and an immutable native stage/operation identity. Unknown effects stop
the job; only GET reconciliation is retried. The native conservative idle guard
does not attest displayed foreground or absence of every protected UI.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time
import uuid

from .native_package import PROJECT, TITLE, canonical, json_object, load_candidate, sha
from resident.lifecycle_client import LifecycleClient, LifecycleTransport, LifecycleRejected, hex_pin
from resident.keep_awake_client import KeepAwakeClient, ResidentKeeper
from .runner import Journal, ROOT, WORKDIR, utc
from .session import exclusive

PLAN_FIELDS = {'protocol', 'job_id', 'project', 'title_id', 'candidate', 'resident_build_id',
               'instance_id', 'cycles', 'measurement_s', 'timeout_s'}
LIMITS = {'cycles': 3, 'measurement_s': [0.25, 10], 'timeout_s': [10, 180],
          'file_bytes': 8 * 1024 * 1024, 'total_bytes': 16 * 1024 * 1024}
LIMITATIONS = ['Only the dedicated VMCP00001 lab can be installed or launched.',
              'Conservative idle-shell policy; displayed foreground and protected UI are not attested.',
              'No Control/kernel loading, input, capture or boot-configuration changes; installer owns its temporary Promoter module.',
              'Resident 0.1.6 requires a bounded keep-awake lease during execution; legacy 0.1.5 has no automatic power protection. Saved sleep and brightness settings stay unchanged.',
              'No package uninstall, data migration, arbitrary app replacement or automatic rollback.',
              'SDK submission, installed-file hashes and live runtime acceptance are separate evidence.',
              'Unknown native effects or ownership drift stop all further mutations without replay.']


class Stopped(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class Unconfirmed(Stopped):
    pass


def _bounds(cycles, measurement_s, timeout_s):
    if type(cycles) is not int or not 1 <= cycles <= 3:
        raise ValueError('Choose 1..3 explicitly planned native cycles')
    if type(measurement_s) not in (int, float) or not 0.25 <= measurement_s <= 10:
        raise ValueError('Choose a 0.25..10 second measurement')
    if type(timeout_s) is not int or not 10 <= timeout_s <= 180:
        raise ValueError('Choose a 10..180 second lifecycle polling bound')


def _status(value, plan, *, idle=False):
    if (value['resident_build_id'] != plan['resident_build_id'] or value['instance_id'] != plan['instance_id']
            or value['blocked'] or value['active_attempt'] is not None):
        raise Stopped('resident_instance_changed_blocked_or_busy')
    if idle and not value['guard']['ready']:
        raise Stopped('native_idle_policy_not_ready')
    return value


def preview(expected_sha256, cycles=1, measurement_s=0.5, timeout_s=90, *, client=None, root=WORKDIR):
    _bounds(cycles, measurement_s, timeout_s)
    candidate, _ = load_candidate(expected_sha256, root=root)
    with exclusive():
        c = client or LifecycleClient()
        first = c.status()
        second = c.status()
        if (first['resident_build_id'] != second['resident_build_id'] or first['instance_id'] != second['instance_id']
                or second['clock_ms'] < first['clock_ms']):
            raise Stopped('resident_identity_changed_during_preview')
        plan = {'protocol': 1, 'job_id': uuid.uuid4().hex, 'project': PROJECT, 'title_id': TITLE,
                'candidate': candidate, 'resident_build_id': second['resident_build_id'],
                'instance_id': second['instance_id'], 'cycles': cycles,
                'measurement_s': measurement_s, 'timeout_s': timeout_s}
        ready = (not second['blocked'] and second['active_attempt'] is None
                 and second['guard']['ready'] and second['installer']['ready'])
        return {'plan': plan, 'plan_sha256': sha(canonical(plan)), 'ready': ready,
                'status': second, 'limits': LIMITS, 'limitations': LIMITATIONS,
                'device_mutations': 0}


def _validate(plan, digest, root):
    if (not isinstance(plan, dict) or set(plan) != PLAN_FIELDS or type(plan.get('protocol')) is not int
            or plan['protocol'] != 1 or plan.get('project') != PROJECT or plan.get('title_id') != TITLE
            or not hex_pin(plan.get('job_id'), 32) or not hex_pin(plan.get('resident_build_id'), 64)
            or not hex_pin(plan.get('instance_id'), 32) or not hex_pin(digest, 64)
            or sha(canonical(plan)) != digest):
        raise ValueError('Native lifecycle plan or SHA-256 differs')
    _bounds(plan['cycles'], plan['measurement_s'], plan['timeout_s'])
    if not isinstance(plan['candidate'], dict):
        raise ValueError('Native lifecycle candidate is unavailable')
    candidate, files = load_candidate(plan['candidate'].get('package_sha256'), root=root)
    if candidate != plan['candidate']:
        raise ValueError('Native lifecycle candidate changed after preview')
    return candidate, files


def _claim(root, plan, digest, folder):
    base = Path(root) / '.devloop-private/native-lifecycle-plans'
    base.mkdir(parents=True, exist_ok=True)
    path = base / (plan['job_id'] + '.json')
    # Exclusive creation is the local execute fence, including jobs that failed
    # before their first device write. A plan is never implicitly retried.
    with path.open('x', encoding='utf-8') as output:
        output.write(json.dumps({'plan_sha256': digest, 'evidence_directory': str(folder.resolve())}) + '\n')
        output.flush()
        os.fsync(output.fileno())


class _Job:
    def __init__(self, client, journal, plan, files):
        self.c, self.j, self.plan, self.files = client, journal, plan, files
        self.last_clock = 0
        self.uncertain = False
        self.runtime = None
        self.running_state = None
        self.deadline = time.monotonic() + plan['timeout_s']
        self.keeper = None
        self.pending_native = None

    def keep_awake(self, *, fresh=False):
        if self.keeper is not None:
            try:
                self.keeper.check(fresh=fresh)
            except Exception as error:
                if self.pending_native or self.runtime is not None and self.running_state is None:
                    self.uncertain = True
                    raise Unconfirmed('resident_keep_awake_lost_during_native_effect') from error
                raise Stopped('resident_keep_awake_no_longer_confirmed') from error

    def status(self, idle=False):
        self.keep_awake()
        self.c.check_endpoint()
        value = _status(self.c.status(), self.plan, idle=idle)
        if value['clock_ms'] < self.last_clock:
            raise Stopped('resident_clock_regressed')
        self.last_clock = value['clock_ms']
        if idle and value['guard']['occupied_slots'] == 0:
            self.running_state = False
        return value

    def event(self, kind, fields):
        return self.j.event(kind, fields)

    def mutate(self, operation, fields, call, reconcile):
        self.c.check_endpoint()
        self.keep_awake(fresh=True)
        self.event('mutation_intent', {'operation': operation, **fields})
        if operation in ('launch', 'graceful_exit'):
            # Submission is not runtime presence or absence. Keep a tri-state
            # until an independent owned-runtime or strict absence observation.
            self.running_state = None
        try:
            result = call()
        except LifecycleTransport as error:
            self.uncertain = True
            self.event('mutation_reply_unconfirmed', {'operation': operation, 'replayed': False})
            try:
                result = reconcile()
            except Exception:
                raise Unconfirmed(operation + '_outcome_unconfirmed') from error
            self.event('read_only_reconciliation', {'operation': operation, 'receipt': result,
                                                    'replayed': False})
            self.uncertain = False
        except LifecycleRejected:
            raise Stopped(operation + '_rejected') from None
        except Exception:
            self.uncertain = True
            raise Unconfirmed(operation + '_invalid_or_uncommitted_receipt') from None
        # A journal commit failure prevents any subsequent device mutation.
        try:
            self.event('mutation_receipt', {'operation': operation, 'receipt': result})
        except Exception:
            self.uncertain = True
            raise Unconfirmed(operation + '_receipt_journal_failed') from None
        return result

    def stage(self):
        status = self.status(idle=True)
        candidate = self.plan['candidate']
        manifest = {key: candidate[key] for key in ('project', 'title_id', 'version', 'native_build_id',
                                                   'package_sha256', 'package_bytes', 'files')}
        manifest.update(protocol=1, resident_build_id=self.plan['resident_build_id'],
                        instance_id=self.plan['instance_id'], attempt=uuid.uuid4().hex,
                        issued_ms=status['clock_ms'], ttl_ms=30000)
        digest = sha(canonical(manifest))
        self.j.report.update(stage_attempt=manifest['attempt'], manifest_sha256=digest, manifest=manifest)
        self.j.save()
        observed = self.mutate('create_stage', {'manifest': manifest, 'manifest_sha256': digest},
                               lambda: self.c.stage(manifest),
                               lambda: self.c.inspect_stage(manifest['attempt'], manifest, digest))
        for index, payload in enumerate(self.files):
            self.status()
            if observed['files'][index]['published']:
                raise Stopped('new_native_stage_already_has_payload')

            def reconcile_file(index=index):
                result = self.c.inspect_stage(manifest['attempt'], manifest, digest)
                if not result['files'][index]['published'] or not result['files'][index]['verified']:
                    raise Unconfirmed('file_publication_not_verified')
                return result

            observed = self.mutate('publish_stage_file', {'stage_attempt': manifest['attempt'],
                                                         'index': index, **manifest['files'][index]},
                                   lambda index=index, payload=payload: self.c.put_file(manifest['attempt'], index,
                                                                                     payload, manifest, digest),
                                   reconcile_file)
            if not observed['files'][index]['verified']:
                raise Unconfirmed('published_stage_file_not_verified')
        observed = self.c.inspect_stage(manifest['attempt'], manifest, digest)
        self.status()
        if not observed['complete']:
            raise Unconfirmed('native_stage_incomplete')
        self.event('stage_verified', {'stage_attempt': manifest['attempt'], 'manifest_sha256': digest,
                                     'files': candidate['files']})
        return manifest, digest

    def operation(self, operation, manifest, digest):
        status = self.status(idle=True)
        if operation == 'install' and not status['installer']['ready']:
            raise Stopped('native_installer_unavailable_or_owned_elsewhere')
        request = {'manifest_sha256': digest, 'resident_build_id': self.plan['resident_build_id'],
                   'instance_id': self.plan['instance_id'], 'attempt': uuid.uuid4().hex,
                   'issued_ms': status['clock_ms'], 'ttl_ms': 30000}
        observed = self.mutate(operation, {'stage_attempt': manifest['attempt'], 'request': request},
                               lambda: self.c.operation(manifest['attempt'], operation, request),
                               lambda: self.c.inspect_operation(request['attempt'], request,
                                                                 manifest['attempt'], operation))
        if observed['state'] in ('queued', 'dispatch_intent', 'running') or operation == 'launch':
            self.pending_native = operation
        expected = 'installed_verified' if operation == 'install' else 'submitted'
        while True:
            self.c.check_endpoint()
            try:
                self.keep_awake()
            except Stopped as error:
                if observed['state'] in ('queued', 'dispatch_intent', 'running'):
                    self.uncertain = True
                    raise Unconfirmed(operation + '_pending_when_keep_awake_lost') from error
                raise
            if observed['state'] == expected:
                if operation == 'install':
                    self.pending_native = None
                self.event('native_operation_verified', {'operation': operation, 'receipt': observed})
                return observed
            if observed['state'] in ('unknown', 'native_rejected', 'refused', 'expired'):
                self.uncertain = observed['state'] == 'unknown' or observed['may_have_effects']
                raise Unconfirmed(operation + '_native_outcome_unconfirmed') if self.uncertain else Stopped(operation + '_native_refused')
            if observed['state'] not in ('queued', 'dispatch_intent', 'running'):
                raise Unconfirmed(operation + '_unexpected_native_state')
            if time.monotonic() >= self.deadline:
                self.uncertain = True
                raise Unconfirmed(operation + '_polling_deadline_no_replay')
            time.sleep(0.1)
            try:
                observed = self.c.inspect_operation(request['attempt'], request, manifest['attempt'], operation)
            except LifecycleTransport:
                # A known request is never resubmitted. GET may be repeated while
                # the asynchronous native worker retains its own dispatch fence.
                continue

    def observe(self, previous=None, *, check_selftest=True):
        self.running_state = None
        before = self.status()
        candidate = self.plan['candidate']
        state = self.c.lab_status(candidate['native_build_id'], candidate['version'])
        inventory = self.c.inventory(state['pid'])
        after = self.status()
        if not before['clock_ms'] <= inventory['sampled_ms'] <= after['clock_ms']:
            raise Stopped('native_inventory_clock_outside_resident_observations')
        if previous is not None:
            if (any(state[k] != previous[k] for k in ('pid', 'run', 'native_build_id', 'revision'))
                    or state['sampled_ms'] < previous['sampled_ms'] or state['frame'] < previous['frame']):
                raise Stopped('native_lab_ownership_or_clock_changed')
        # An exact runtime/inventory match establishes ownership independently
        # from a failed test. Only this known failure may authorize graceful
        # cleanup; changed identity, malformed telemetry and unknown native
        # effects never authorize cleanup into another process.
        self.runtime = state
        self.pending_native = None
        self.running_state = True
        if check_selftest and not state['selftest_passed']:
            raise Stopped('native_lab_selftest_failed')
        return state

    def measure(self):
        previous = None
        while time.monotonic() < self.deadline:
            try:
                current = self.observe(previous)
            except LifecycleTransport:
                time.sleep(0.1)
                continue
            if previous is not None and current['frame'] > previous['frame']:
                break
            previous = current
            time.sleep(0.1)
        else:
            raise Unconfirmed('native_lab_runtime_not_observed')
        self.runtime = current
        first = current
        samples = []
        until = min(self.deadline, time.monotonic() + self.plan['measurement_s'])
        while time.monotonic() < until:
            time.sleep(min(0.1, max(0, until - time.monotonic())))
            previous = current
            current = self.observe(current)
            if current['frame'] <= previous['frame']:
                raise Stopped('native_lab_frames_stalled')
            if current['checksum'] != first['checksum']:
                raise Stopped('native_lab_selftest_checksum_changed')
            self.runtime = current
            samples.append({'frame': current['frame'], 'sampled_ms': current['sampled_ms'],
                            'selftest_passed': True, 'checksum': current['checksum']})
        if not samples:
            raise Unconfirmed('native_lab_measurement_deadline')
        self.event('runtime_evaluated', {'runtime_identity': {key: current[key] for key in
                                                              ('title_id', 'version', 'native_build_id', 'pid', 'run', 'revision')},
                                         'samples': samples, 'first_frame': first['frame'],
                                         'last_frame': current['frame'], 'passed': True})
        return {'samples': len(samples), 'selftest_passed': True, 'checksum': current['checksum'],
                'first_frame': first['frame'], 'last_frame': current['frame'],
                'runtime_identity': {key: current[key] for key in
                                     ('title_id', 'version', 'native_build_id', 'pid', 'run', 'revision')}}

    def wait_closed(self):
        # Native absence is a conservative idle-policy observation, not proof
        # of a displayed foreground. Require two stable observations.
        samples = 0
        self.running_state = None
        while time.monotonic() < self.deadline:
            status = self.status()
            absent = False
            try:
                self.c.lab_status(self.plan['candidate']['native_build_id'], self.plan['candidate']['version'])
            except LifecycleTransport:
                absent = True
            if absent and status['guard']['ready'] and status['guard']['occupied_slots'] == 0:
                samples += 1
                if samples >= 2:
                    self.runtime = None
                    self.pending_native = None
                    self.running_state = False
                    self.event('runtime_absent_observed', {'samples': samples, 'policy': status['guard']['policy'],
                                                          'foreground_verified': False, 'protected_ui_verified': False})
                    return {'exited': True, 'native_idle_samples': samples}
            else:
                samples = 0
            time.sleep(0.1)
        raise Unconfirmed('native_lab_exit_not_confirmed_no_replay')

    def exit(self, *, check_selftest=True):
        current = self.observe(self.runtime, check_selftest=check_selftest)
        self.runtime = current

        def reconcile_exit():
            self.wait_closed()
            return {'exited': True, 'reconciled_by_get_only': True}

        receipt = self.mutate('graceful_exit', {'runtime_identity': current},
                              lambda: self.c.lab_exit(current), reconcile_exit)
        if self.runtime is not None:
            self.wait_closed()
        return receipt


def execute(plan, plan_sha256, *, client=None, root=WORKDIR):
    candidate, files = _validate(plan, plan_sha256, root)
    with exclusive():
        journal = Journal(Path(root), 'native-lifecycle')
        journal.report.update(plan=plan, plan_sha256=plan_sha256, result='blocked', cycles=[],
                              limitations=LIMITATIONS, mutation_submissions=0,
                              accepted_applications_changed=False, boot_configuration_changed=False)
        _claim(root, plan, plan_sha256, journal.folder)
        # Preserve the exact transferred artifacts before any device mutation.
        for index, payload in enumerate(files):
            with (journal.folder / f'payload-{index}.bin').open('xb') as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
        job = _Job(client or LifecycleClient(), journal, plan, files)
        started = time.monotonic()
        try:
            identity = job.status(idle=True)
            advertised = identity.get('keep_awake_protocol') is not None or identity.get('keep_awake_port') is not None
            required = identity.get('resident_version') is not None and identity['resident_version'] != '0.1.5'
            if advertised or required:
                if (type(identity.get('keep_awake_protocol')) is not int or identity['keep_awake_protocol'] != 1
                        or type(identity.get('keep_awake_port')) is not int or identity['keep_awake_port'] != 17869):
                    raise Stopped('resident_keep_awake_capability_missing_or_invalid')
                job.keeper = ResidentKeeper(KeepAwakeClient(job.c.provider), journal.folder, plan['job_id'],
                                            max_duration_ms=1800000)
                # The dedicated lease worker has its own boot/session instance,
                # separately pinned from the native lifecycle broker instance.
                job.keeper.start(plan['resident_build_id'])
                job.keep_awake(fresh=True)
                journal.report['keep_awake'] = dict(job.keeper.result)
            else:
                journal.report['keep_awake'] = {'enabled': False, 'reason': 'legacy Resident has no lease capability'}
            manifest, digest = job.stage()
            prior_run = None
            for index in range(plan['cycles']):
                cycle = {'index': index, 'result': 'pending'}
                journal.report['cycles'].append(cycle)
                cycle['install_receipt'] = job.operation('install', manifest, digest)
                cycle['launch_receipt'] = job.operation('launch', manifest, digest)
                cycle['evaluation'] = job.measure()
                if cycle['evaluation']['runtime_identity']['run'] == prior_run:
                    raise Stopped('redeploy_retained_previous_runtime')
                prior_run = cycle['evaluation']['runtime_identity']['run']
                cycle['exit_receipt'] = job.exit()
                cycle['result'] = 'passed'
                journal.save()
            journal.report.update(result='passed', native_lab_left_running=False,
                                  retained_candidate=candidate, stage_retained=True)
        except Exception as error:
            known_failed_test = (isinstance(error, Stopped)
                                 and error.code in ('native_lab_selftest_failed', 'native_lab_selftest_checksum_changed')
                                 and job.runtime is not None and not job.uncertain)
            cleanup = None
            if known_failed_test:
                try:
                    cleanup = job.exit(check_selftest=False)
                    journal.report['failed_test_cleanup'] = {'result': 'owned_runtime_exited', 'receipt': cleanup}
                except Exception as cleanup_error:
                    job.uncertain = True
                    journal.report['failed_test_cleanup'] = {'result': 'unconfirmed_no_replay',
                                                            'failure_type': type(cleanup_error).__name__}
            result = ('unconfirmed' if isinstance(error, Unconfirmed) or job.uncertain
                      else 'failed_checks' if known_failed_test and cleanup is not None else 'blocked')
            journal.report.update(result=result,
                                  failure_code=error.code if isinstance(error, Stopped) else 'transport_or_local_failure',
                                  failure_type=type(error).__name__,
                                  native_lab_left_running=None if job.uncertain else job.running_state,
                                  last_verified_runtime=job.runtime,
                                  further_mutations='stopped; failed candidate is not automatically redeployed')
        finally:
            if job.keeper is not None:
                journal.report['keep_awake'] = job.keeper.stop()
                if (journal.report['result'] == 'passed'
                        and journal.report['keep_awake'].get('end') not in ('ended', 'already_inactive')):
                    journal.report.update(result='unconfirmed', failure_code='resident_keep_awake_end_unconfirmed',
                                          further_mutations='stopped; work completed but lease release requires inspection or expiry')
            journal.report['mutation_submissions'] = sum(event['kind'] == 'mutation_intent' for event in journal.report['events'])
            journal.report['elapsed_s'] = round(time.monotonic() - started, 3)
            journal.report['finished_utc'] = utc()
            journal.save()
        return {key: value for key, value in journal.report.items() if key != 'events'} | {'evidence_directory': str(journal.folder)}


def _durable_intents(folder, plan):
    """Recover the fsynced append-only intent stream, never the report cache.

    A process can die after journal fsync and before report replacement. A torn
    final JSONL record is not a complete committed intent; earlier complete
    records remain available for GET-only inspection.
    """
    path = folder / 'journal.jsonl'
    if not path.exists():
        return [], False
    with path.open('rb') as source:
        raw = source.read(16 * 1024 * 1024 + 1)
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError('Native lifecycle journal exceeds its recovery bound')
    lines = raw.splitlines(keepends=True)
    if len(lines) > 4096:
        raise ValueError('Native lifecycle journal has too many records')
    torn = bool(lines and not lines[-1].endswith(b'\n'))
    if torn:
        lines.pop()
    intents, stage, operation_ids = [], None, set()
    for line in lines:
        if len(line) > 65536:
            raise ValueError('Native lifecycle journal record exceeds its bound')
        event = json_object(line)
        if not isinstance(event.get('kind'), str) or not isinstance(event.get('utc'), str):
            raise ValueError('Native lifecycle journal record is invalid')
        if event['kind'] != 'mutation_intent':
            continue
        operation = event.get('operation')
        if operation == 'create_stage':
            manifest = event.get('manifest')
            if (stage is not None or not isinstance(manifest, dict)
                    or set(manifest) != {'protocol', 'project', 'title_id', 'version', 'native_build_id',
                                         'package_sha256', 'package_bytes', 'resident_build_id', 'instance_id',
                                         'attempt', 'issued_ms', 'ttl_ms', 'files'}
                    or not hex_pin(manifest.get('attempt'), 32)
                    or manifest.get('resident_build_id') != plan['resident_build_id']
                    or manifest.get('instance_id') != plan['instance_id']
                    or type(manifest.get('protocol')) is not int or manifest['protocol'] != 1
                    or type(manifest.get('issued_ms')) is not int or manifest['issued_ms'] < 0
                    or type(manifest.get('ttl_ms')) is not int or not 1 <= manifest['ttl_ms'] <= 30000
                    or any(manifest.get(k) != plan['candidate'].get(k) for k in
                           ('project', 'title_id', 'version', 'native_build_id', 'package_sha256',
                            'package_bytes', 'files'))
                    or event.get('manifest_sha256') != sha(canonical(manifest))):
                raise ValueError('Native lifecycle durable stage differs from its plan')
            stage = event
        elif operation in ('install', 'launch'):
            request = event.get('request')
            if (stage is None or event.get('stage_attempt') != stage['manifest']['attempt']
                    or not isinstance(request, dict)
                    or set(request) != {'manifest_sha256', 'resident_build_id', 'instance_id',
                                       'issued_ms', 'ttl_ms', 'attempt'}
                    or not hex_pin(request.get('attempt'), 32) or request['attempt'] in operation_ids
                    or request.get('manifest_sha256') != stage['manifest_sha256']
                    or request.get('resident_build_id') != plan['resident_build_id']
                    or request.get('instance_id') != plan['instance_id']
                    or type(request.get('issued_ms')) is not int or request['issued_ms'] < 0
                    or type(request.get('ttl_ms')) is not int or not 1 <= request['ttl_ms'] <= 30000):
                raise ValueError('Native lifecycle durable operation differs from its plan')
            operation_ids.add(request['attempt'])
        elif operation not in ('publish_stage_file', 'graceful_exit'):
            raise ValueError('Native lifecycle journal has an unknown mutation')
        intents.append(event)
    return intents, torn


def reconcile(job_id, *, client=None, root=WORKDIR):
    """Inspect an existing local job and its exact native identities using GET only."""
    if not hex_pin(job_id, 32):
        raise ValueError('Choose an existing native lifecycle job ID')
    with exclusive():
        claim = json_object((Path(root) / '.devloop-private/native-lifecycle-plans' / (job_id + '.json')).read_bytes())
        folder = Path(claim['evidence_directory']).resolve()
        base = (Path(root) / 'evidence/workbench').resolve()
        if base not in folder.parents:
            raise ValueError('Native job evidence is outside the Workbench directory')
        report = json_object((folder / 'report.json').read_bytes())
        plan = report['plan']
        if (plan['job_id'] != job_id or claim['plan_sha256'] != report['plan_sha256']
                or sha(canonical(plan)) != report['plan_sha256']):
            raise ValueError('Native job plan or claim differs')
        intents, torn = _durable_intents(folder, plan)
        c = client or LifecycleClient()
        result = {'job_id': job_id, 'original_result': report['result'], 'device_mutations': 0,
                  'status': c.status(), 'operation_observations': [], 'ownership_adopted': False,
                  'automatic_resume': False, 'evidence_directory': str(folder),
                  'intent_source': 'fsynced_journal_jsonl', 'durable_mutation_intents': len(intents),
                  'torn_final_record_ignored': torn}
        for event in intents:
            if event['operation'] == 'create_stage':
                result['stage'] = c.inspect_stage(event['manifest']['attempt'], event['manifest'],
                                                  event['manifest_sha256'])
            elif event['operation'] in ('install', 'launch'):
                result['operation_observations'].append(c.inspect_operation(event['request']['attempt'],
                                                                            event['request'], event['stage_attempt'],
                                                                            event['operation']))
        return result


def register(mcp, read_annotations, write_annotations):
    @mcp.tool(annotations=read_annotations)
    def vita_workbench_native_preview(expected_sha256: str, cycles: int = 1,
                                      measurement_s: float = 0.5, timeout_s: int = 90) -> dict:
        """Validate the fixed lifecycle-lab native package/build/source pins and inspect Resident's conservative idle guard. Returns an immutable hash-bound plan for 1..3 install/launch/selftest/graceful-exit cycles. No device writes; only VMCP00001 is supported. Native installation and runtime acceptance remain separate evidence."""
        return preview(expected_sha256, cycles, measurement_s, timeout_s)

    @mcp.tool(annotations=write_annotations)
    def vita_workbench_native_execute(plan: dict, plan_sha256: str) -> dict:
        """Execute a fresh preview exactly once: stage eight fixed hash-pinned files, install/verify, launch/observe exact build/PID/run, evaluate selftest and exit/redeploy the dedicated lab. Pins Resident's build/instance, journals before each write and retains artifacts/receipts. Resident 0.1.6 requires an automatically renewed, bounded keep-awake lease and ends it on completion/failure; legacy 0.1.5 has no lease protection. Saved sleep/brightness settings stay unchanged. Lost replies reconcile the original attempt with GET only; unresolved effects stop without replay or automatic rollback. Does not change accepted apps, Control, boot configuration, input or capture. Conservative idle-shell policy does not attest protected UI. Polling 10..180s plus socket deadlines."""
        return execute(plan, plan_sha256)

    @mcp.tool(annotations=read_annotations)
    def vita_workbench_native_reconcile(job_id: str) -> dict:
        """Inspect the retained plan, exact stage and install/launch receipts for an existing native lifecycle job using GET only. Never resubmits, exits, adopts uncertain ownership or resumes the job. Use after lost replies or process/network interruption."""
        return reconcile(job_id)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('preview')
    p.add_argument('sha256')
    p.add_argument('--cycles', type=int, default=1)
    p.add_argument('--measurement', type=float, default=0.5)
    p.add_argument('--timeout', type=int, default=90)
    p = commands.add_parser('execute')
    p.add_argument('manifest', help='Exact UTF-8 preview plan JSON, not the whole preview response')
    p.add_argument('sha256', help='SHA-256 of canonical plan JSON returned by preview')
    p = commands.add_parser('reconcile')
    p.add_argument('job_id')
    args = parser.parse_args()
    if args.command == 'preview':
        result = preview(args.sha256, args.cycles, args.measurement, args.timeout)
    elif args.command == 'execute':
        with Path(args.manifest).open('rb') as source:
            raw = source.read(16385)
        if not 0 < len(raw) <= 16384:
            raise ValueError('Native lifecycle plan exceeds 16 KiB')
        result = execute(json_object(raw), args.sha256)
    else:
        result = reconcile(args.job_id)
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result.get('ready') is True or result.get('result') == 'passed' or args.command == 'reconcile' else 1


if __name__ == '__main__':
    raise SystemExit(main())
