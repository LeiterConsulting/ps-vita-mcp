"""Observe isolated human controls without injecting input or changing DevLoop.

Leave native DevLoop paused. Each gesture follows a separate dim cycle; the
foreground telemetry distinguishes both sticks and both touch panels. Whole
device motion, another control, stale telemetry or a synthetic lease cannot
qualify a physical gesture. Human visual confirmation remains separate.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workbench.runner import Device, Journal, check_identity, utc
from workbench.power import lease, status
from workbench.session import exclusive

STEPS = (
    ('buttons', 'hold D-pad LEFT for eight seconds, then release', 1),
    ('left-stick', 'move only the left stick fully sideways for eight seconds, then release', 2),
    ('right-stick', 'move only the right stick fully sideways for eight seconds, then release', 2),
    ('front-touch', 'touch the bottom edge of the screen for eight seconds, then release', 4),
    ('rear-touch', 'touch only the rear panel for eight seconds, then release', 4),
)

def channels(sample):
    sticks = sample.get('sticks', {})
    if sample.get('controller_read', -1) <= 0 or any(type(sticks.get(k)) is not int or not 0 <= sticks[k] <= 255 for k in ('lx', 'ly', 'rx', 'ry')):
        raise RuntimeError('Invalid foreground controller readback')
    for panel in ('front', 'rear'):
        p = sample.get(panel, {})
        if p.get('read_result', -1) < 0 or not isinstance(p.get('contacts'), list):
            raise RuntimeError('Invalid foreground touch readback')
    return {
        'buttons': sample['buttons'] != 0,
        'left-stick': any(abs(sticks[k] - 128) > 16 for k in ('lx', 'ly')),
        'right-stick': any(abs(sticks[k] - 128) > 16 for k in ('rx', 'ry')),
        'front-touch': bool(sample['front']['contacts']),
        'rear-touch': bool(sample['rear']['contacts']),
    }

def matches(kind, sample):
    active = channels(sample)
    if not active[kind] or any(v for k, v in active.items() if k != kind):
        return False
    if kind == 'buttons':
        return sample['buttons'] == 128  # D-pad LEFT does not edit native DevLoop.
    if kind == 'front-touch':
        return all(p['y'] >= .90 for p in sample['front']['contacts'])  # Above 489px, outside the field ending at 474px.
    return True

def restoration(kind, power, original):
    bit = dict((s[0], s[2]) for s in STEPS)[kind]
    if kind in ('front-touch', 'rear-touch') and 'physical_touch_panels' in power:
        expected_panel = 1 if kind == 'front-touch' else 2
        if (power.get('touch_read_result', -1) < 0 or power['physical_touch_panels'] != expected_panel
                or power.get('touch_source_pid', 0) <= 0):
            return False
        if 'touch_diagnostics' in power:
            diagnostic = power['touch_diagnostics'][0 if kind == 'front-touch' else 1]
            if (diagnostic['reader_pid'] != power['touch_source_pid'] or not 1 <= diagnostic['native_contacts'] <= 8
                    or not diagnostic['source_ticks'] or not diagnostic['advances']
                    or not 0 <= power['touch_sample_ms'] - diagnostic['changed_ms'] <= 250):
                return False
    return (power.get('motion_fresh') is True and power['lease_remaining_ms'] > 0
            and not power['dimmed'] and power['idle_elapsed_ms'] < 1200
            and power['last_activity_flags'] == bit
            and abs(power['brightness'] - original) <= max(64, original // 100))

def gesture_decision(kind, raw, power, original):
    """Separate HTTP snapshots can straddle onset; neutral means keep observing.

    A wrong live channel or mixed power flags invalidates the dim cycle. A
    fresh neutral foreground snapshot alone cannot refute power activity.
    """
    bit = dict((s[0], s[2]) for s in STEPS)[kind]
    active = channels(raw)
    if power['last_activity_flags'] & (15 ^ bit) or any(v for k, v in active.items() if k != kind):
        return 'confounded'
    if active[kind] and not matches(kind, raw):
        return 'wrong gesture'
    if matches(kind, raw) and restoration(kind, power, original):
        return 'passed'
    return 'await paired sample'

def scene(s):
    return {k: s[k] for k in ('paused', 'mode', 'parameters', 'ball', 'score', 'added_obstacles')}

def watch(duration=1800, start_at='buttons'):
    if type(duration) is not int or not 30 <= duration <= 1800:
        raise ValueError('Observation must last 30..1800 seconds')
    if start_at not in [s[0] for s in STEPS]:
        raise ValueError('Unknown starting gesture')
    build = json.loads((ROOT / 'dist/control/build-report.json').read_text())['build_id']
    j = Journal(ROOT, 'physical-controls')
    j.report.update(control_build=build, requested_s=duration, start_at=start_at, gates=[], input_injection=False,
                    human_visual_confirmation='pending', samples=[], sample_count=0, complete_samples_log='samples.jsonl')
    d = Device()
    submitted = False
    renewed = 0
    index = [s[0] for s in STEPS].index(start_at)
    armed = False
    await_neutral = False
    original = None
    last_frame = None
    started = time.monotonic()

    def work(ttl, phase):
        nonlocal renewed
        j.mutation('work_lease', {'ttl_ms': ttl, 'idle_ms': 5000, 'dim_percent': 20, 'phase': phase},
                   lambda: lease(d.control, ttl, 5000, 20))
        renewed = time.monotonic()

    with exclusive():
        try:
            baseline = d.control_status()
            check_identity(baseline, build)
            before = status(d.control)
            if before['lease_remaining_ms'] or before['dimmed']:
                raise RuntimeError('Another work session is active')
            state = d.status()
            script = d.script()
            if state.get('version') not in ('01.02', '01.03') or not state['paused'] or script['active']:
                raise RuntimeError('Leave native DevLoop 01.02 or 01.03 paused for these gestures')
            j.report.update(before_control=baseline, before_power=before, before_devloop=state, before_script=script)
            submitted = True
            work(30000, 'begin')
            while time.monotonic() - started < duration:
                if (j.folder / 'stop.requested').exists():
                    j.report['result'] = 'stopped by operator; only recorded gates qualify'
                    break
                if time.monotonic() - renewed >= 10:
                    work(30000, 'working-heartbeat')
                control = d.control_status()
                check_identity(control, build)
                if control['uptime_ms'] < baseline['uptime_ms']:
                    raise RuntimeError('Control restarted during the physical test')
                raw = d.foreground.vita_read_input()
                if last_frame is not None and raw['frame'] <= last_frame:
                    raise RuntimeError('Foreground input telemetry stopped advancing')
                last_frame = raw['frame']
                active = channels(raw)
                p = status(d.control)
                sample = {'utc': utc(), 'power': p, 'input': raw, 'control_sample_ms': control['sample_ms']}
                j.report['sample_count'] += 1
                j.report['samples'] = (j.report['samples'] + [sample])[-64:]
                with (j.folder / 'samples.jsonl').open('a', encoding='utf-8') as log:
                    log.write(json.dumps(sample) + '\n')
                if original is None and p.get('motion_fresh') and not p['dimmed'] and 21 < p['brightness'] <= 65536:
                    original = p['brightness']
                    j.report['original_brightness'] = original
                kind, instruction, bit = STEPS[index]
                if await_neutral:
                    if not any(active.values()):
                        j.report['gates'][-1]['neutral_after_release'] = raw
                        await_neutral = False
                        index += 1
                        if index == len(STEPS):
                            j.report['result'] = 'passed requested isolated physical input readbacks, dim restoration and neutral release; human visual confirmation required'
                            break
                    j.save()
                    time.sleep(.2)
                    continue
                if original is not None and p['dimmed'] and p['lease_remaining_ms'] > 0 and not any(active.values()) and not armed:
                    armed = True
                    j.report['phase'] = 'ready for ' + kind
                    j.event('gesture_ready', {'activity': kind, 'instruction': instruction, 'power': p, 'frame': raw['frame']})
                    print(json.dumps({'phase': j.report['phase'], 'instruction': instruction, 'evidence': str(j.folder / 'report.json')}), flush=True)
                if armed and not p['dimmed'] and p['idle_elapsed_ms'] < 1200:
                    decision = gesture_decision(kind, raw, p, original)
                    if decision == 'passed':
                        proof = {'activity': kind, 'passed': True, 'restored_power': p, 'input': raw, 'utc': utc()}
                        j.report['gates'].append(proof)
                        j.event('gesture_observed', proof)
                        print(json.dumps({'phase': 'observed ' + kind, 'brightness': p['brightness'], 'next': 'release and wait for the next dim cycle'}), flush=True)
                        armed = False
                        await_neutral = True
                    elif decision != 'await paired sample':
                        armed = False
                        j.event('gesture_inconclusive', {'activity': kind, 'reason': decision, 'power': p, 'active_channels': active, 'input': raw})
                        print(json.dumps({'phase': 'repeat ' + kind + ' after the screen dims; another channel, movement or wrong gesture was seen', 'flags': p['last_activity_flags']}), flush=True)
                j.save()
                time.sleep(.2)
            else:
                j.report['result'] = 'bounded window expired; only recorded gates qualify'
            after = d.status()
            j.report['after_devloop'] = after
            j.report['scene_preserved'] = scene(state) == scene(after)
            if not j.report['scene_preserved']:
                raise RuntimeError('Physical gestures changed the original DevLoop scene')
        except Exception as error:
            j.report.update(result='failed or interrupted physical observation', failure_type=type(error).__name__, failure=str(error)[:240])
        finally:
            if submitted:
                try:
                    work(0, 'end')
                    time.sleep(.15)
                    j.report['cleanup_power'] = status(d.control)
                except Exception:
                    j.report['cleanup'] = 'unconfirmed; last accepted work lease expires within 30 seconds'
            j.report['finished_utc'] = utc()
            j.save()
    print(json.dumps({'result': j.report['result'], 'passed': [g['activity'] for g in j.report['gates']], 'evidence': str(j.folder / 'report.json')}), flush=True)

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--duration', type=int, default=1800)
    p.add_argument('--start-at', choices=[s[0] for s in STEPS], default='buttons')
    a = p.parse_args()
    watch(a.duration, a.start_at)
