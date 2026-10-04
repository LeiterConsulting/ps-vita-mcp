"""Bounded human sleep/Wi-Fi observations; no forced wake or lost-lease replay.

After the first failed read, work heartbeats stop permanently for this job.
Only read-only probes continue. Wi-Fi restoration qualifies independently of
expiry only if reconnection and restored readback precede the last accepted
lease deadline, with no intervening activity. Human cause/visual confirmation
is retained separately.
"""
import argparse
import http.client
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workbench.runner import Device, Journal, check_identity, utc
from workbench.power import pack, validate
from workbench.session import exclusive
from workbench.watch_controls import scene

def recovery_checks(kind, before, after, seconds_to_deadline, offline_s, elapsed_since_dim_s=None):
    out = {
        'work_lease_cleared': after['lease_remaining_ms'] == 0,
        'dimming_cleared': after['dimmed'] is False,
        'brightness_restored': abs(after['brightness'] - before['brightness']) <= max(64, before['brightness'] // 100),
        'disconnect_observed': offline_s >= 2,
    }
    if kind == 'wifi':
        out['recovery_precedes_lease_expiry'] = seconds_to_deadline > 1
        # Compare inactivity progression, not just two increasing ages: an
        # intervening gesture could otherwise age beyond the earlier value.
        out['no_activity_since_dim'] = (elapsed_since_dim_s is not None
            and abs((after['idle_elapsed_ms'] - before['idle_elapsed_ms']) / 1000 - elapsed_since_dim_s) < .75)
    return out

def watch(kind, duration=1800):
    if kind not in ('sleep', 'wifi') or type(duration) is not int or not 30 <= duration <= 1800:
        raise ValueError('Choose sleep or wifi and a 30..1800 second window')
    build = json.loads((ROOT / 'dist/control/build-report.json').read_text())['build_id']
    j = Journal(ROOT, 'physical-' + kind)
    j.report.update(control_build=build, requested_s=duration, samples=[], sample_count=0,
                    complete_samples_log='samples.jsonl', human_cause_and_visual_confirmation='pending',
                    forced_wake=False, input_injection=False, heartbeat_replay=False)
    d = Device()
    config = d.control.configuration()
    # The configured native endpoint is independent of foreground DevLoop.
    import os
    port = int(os.environ.get('VITA_CONTROL_PORT', config['port'] + 1))
    if not 1 <= port <= 65535: raise ValueError('Invalid Control port')

    def wire(method, path, body=None):
        c = http.client.HTTPConnection(config['host'], port, timeout=2)
        try:
            c.request(method, path, body, {'Authorization': 'Bearer ' + config['token'], 'Connection': 'close'})
            r = c.getresponse(); raw = r.read(8193)
            if r.status != 200 or len(raw) > 8192 or r.getheader('Content-Type', '').split(';')[0] != 'application/json':
                raise RuntimeError('Observation reply rejected')
            result = json.loads(raw)
            if not isinstance(result, dict): raise RuntimeError('Observation reply is not an object')
            return result
        finally:
            c.close()

    renewed = 0
    deadline = 0
    submitted = False
    heartbeat_stopped = False
    offline = None
    dim = None
    dim_at = None
    original = None
    last_uptime = 0
    started = time.monotonic()

    def work(ttl, phase):
        nonlocal renewed, deadline
        sent = time.monotonic()
        receipt = j.mutation('work_lease', {'ttl_ms': ttl, 'idle_ms': 5000, 'dim_percent': 20, 'phase': phase},
                             lambda: validate(wire('POST', '/power/lease', pack(ttl, 5000, 20))))
        renewed = time.monotonic()
        # Send time is conservative: native acceptance cannot precede submission.
        deadline = sent + ttl / 1000
        return receipt

    with exclusive():
        try:
            baseline = d.control_status(); check_identity(baseline, build)
            last_uptime = baseline['uptime_ms']
            before = validate(wire('GET', '/power/status'))
            if before['lease_remaining_ms'] or before['dimmed']:
                raise RuntimeError('Another working lease is active')
            dev_before = d.status()
            if not dev_before['paused']: raise RuntimeError('Leave DevLoop paused')
            j.report.update(before_control=baseline, before_power=before, before_devloop=dev_before)
            submitted = True
            work(30000, 'begin')
            while time.monotonic() - started < duration:
                if (j.folder / 'stop.requested').exists():
                    j.report['result'] = 'stopped by operator; disconnect not qualified'
                    break
                try:
                    control = wire('GET', '/status')
                    p = validate(wire('GET', '/power/status'))
                except (OSError, http.client.HTTPException):
                    heartbeat_stopped = True
                    if offline is None:
                        offline = time.monotonic()
                        j.event('endpoint_unavailable', {'seconds_until_last_lease_deadline': round(deadline - offline, 3), 'heartbeat_renewal_stopped': True})
                        j.report['phase'] = 'offline; read-only recovery probes only'
                        j.save()
                        print(json.dumps({'phase': j.report['phase'], 'instruction': 'wake or reconnect the Vita manually; do not run Starter again'}), flush=True)
                    time.sleep(1)
                    continue
                check_identity(control, build)
                if control.get('app') != 'Vita Control' or control.get('abi') != 2 or control.get('version') not in ('0.3.1', '0.3.2', '0.3.3') or control['uptime_ms'] < last_uptime:
                    raise RuntimeError('Control identity changed or restarted')
                last_uptime = control['uptime_ms']
                now = time.monotonic()
                sample = {'utc': utc(), 'power': p, 'control': control}
                j.report['samples'] = (j.report['samples'] + [sample])[-64:]
                j.report['sample_count'] += 1
                with (j.folder / 'samples.jsonl').open('a', encoding='utf-8') as log: log.write(json.dumps(sample) + '\n')
                if original is None and p.get('motion_fresh') and not p['dimmed'] and 21 < p['brightness'] <= 65536:
                    original = p['brightness']
                    j.report['original_brightness'] = original
                if offline is not None:
                    if dim is None: raise RuntimeError('Endpoint was lost before a dimmed working baseline')
                    reference = {**dim, 'brightness': original}
                    checks = recovery_checks(kind, reference, p, deadline - now, now - offline, now - dim_at)
                    j.report.update(recovered_control=control, recovered_power=p, checks=checks,
                                    seconds_until_last_lease_deadline=round(deadline - now, 3),
                                    observed_offline_s=round(now - offline, 3))
                    dev_after = d.status()
                    j.report.update(after_devloop=dev_after, scene_preserved=scene(dev_before) == scene(dev_after))
                    checks['devloop_paused_scene_preserved'] = j.report['scene_preserved']
                    j.report['result'] = ('passed device disconnect/recovery readbacks; human cause/visual confirmation required'
                                          if all(checks.values()) else 'recovered; independent disconnect gate not fully qualified')
                    break
                if original is not None and p['dimmed'] and p.get('motion_fresh') and p['lease_remaining_ms'] > 15000:
                    if dim is None:
                        print(json.dumps({'phase': 'ready for manual ' + kind, 'evidence': str(j.folder / 'report.json')}), flush=True)
                    dim = p
                    dim_at = now
                    j.report.update(dimmed_baseline=p, phase='ready for manual ' + kind)
                elif not p['dimmed']:
                    dim = None
                if not heartbeat_stopped and now - renewed >= 10:
                    try:
                        work(30000, 'working-heartbeat')
                    except (OSError, http.client.HTTPException):
                        # A cut may coincide with renewal. Keep the earlier
                        # confirmed deadline, retain the uncertain receipt,
                        # and never replay this heartbeat.
                        heartbeat_stopped = True
                        offline = time.monotonic()
                        j.event('endpoint_unavailable_during_heartbeat', {
                            'seconds_until_last_confirmed_lease_deadline': round(deadline - offline, 3),
                            'heartbeat_renewal_stopped': True, 'replayed': False})
                        j.report['phase'] = 'offline; read-only recovery probes only'
                        print(json.dumps({'phase': j.report['phase'], 'instruction': 'wake or reconnect the Vita manually; do not run Starter again'}), flush=True)
                j.save()
                time.sleep(.25)
            else:
                j.report['result'] = 'bounded window expired without a qualified disconnect/recovery'
        except Exception as error:
            j.report.update(result='failed or interrupted observation', failure_type=type(error).__name__, failure=str(error)[:240])
        finally:
            if submitted:
                try:
                    identity = wire('GET', '/status'); check_identity(identity, build)
                    work(0, 'end')
                    time.sleep(.15)
                    j.report['cleanup_power'] = validate(wire('GET', '/power/status'))
                except Exception:
                    j.report['cleanup'] = 'unconfirmed; last accepted lease expires within 30 seconds; no replay'
            j.report['finished_utc'] = utc()
            j.save()
    print(json.dumps({'result': j.report['result'], 'evidence': str(j.folder / 'report.json'), 'checks': j.report.get('checks')}), flush=True)

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('kind', choices=['sleep', 'wifi']); p.add_argument('--duration', type=int, default=1800)
    a = p.parse_args(); watch(a.kind, a.duration)
