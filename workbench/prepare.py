"""Prepare the foreground runtime without replaying launch or taking over a scene."""
import re
import time

from .power import WorkKeeper
from .runner import Device, Journal, WORKDIR, check_identity, check_devloop_runtime, devloop_runtime_identity, devloop_target_pid, utc
from .session import exclusive


def transport_unavailable(error):
    """Only a transport failure permits launch; auth/config/protocol failures do not."""
    return isinstance(error, OSError) or isinstance(error.__cause__, OSError)


def control_idle(value, expected):
    check_identity(value, expected)
    if value.get('app') != 'Vita Control' or value.get('abi') != 2:
        raise RuntimeError('Preparation requires matched ABI 2 Control')
    if type(value.get('uptime_ms')) is not int or value['uptime_ms'] < 0:
        raise RuntimeError('Control uptime is unavailable')
    for key in ('lease_remaining_ms', 'work_remaining_ms'):
        if type(value.get(key)) is not int or value[key] != 0:
            raise RuntimeError('Another input or work lease is active, or its state is unavailable')


def healthy(state, script, version):
    if state.get('app') != 'Vita DevLoop' or state.get('protocol') != 1 or state.get('version') != version:
        raise RuntimeError('DevLoop identity differs from the selected version')
    if any(type(state.get(key)) is not int or state[key] <= 0 for key in ('revision', 'frame')):
        raise RuntimeError('DevLoop has no valid sampled revision/frame')
    if state.get('paused') is not True or script.get('paused') is not True or script.get('faulted') is not False:
        raise RuntimeError('DevLoop must already be healthy and paused; preparation will not pause or replace a scene')
    if script.get('revision') != state['revision'] or script.get('version',version) != version or script.get('app','Vita DevLoop') != 'Vita DevLoop':
        raise RuntimeError('DevLoop status and script observations disagree')


def prepare(expected_control_build, expected_devloop_version='01.04', timeout_s=30,
            device=None, root=WORKDIR,expected_devloop_build=None):
    """Launch at most once, then prove readiness using separate runtime observations.

    The timeout bounds polling; an in-flight bridge request retains its own socket
    timeout. No input, script, install, module, or boot-config action is submitted.
    """
    if not isinstance(expected_control_build, str) or not re.fullmatch('[0-9a-f]{64}', expected_control_build):
        raise ValueError('Pin the exact Control build ID')
    if expected_devloop_version not in ('01.02', '01.03','01.04'):
        raise ValueError('Choose supported DevLoop version 01.02, 01.03 or 01.04')
    if expected_devloop_build is not None and (not isinstance(expected_devloop_build,str) or not re.fullmatch('[0-9a-f]{64}',expected_devloop_build)):
        raise ValueError('Pin an exact native DevLoop build ID')
    if type(timeout_s) is not int or not 2 <= timeout_s <= 60:
        raise ValueError('Preparation timeout must be 2..60 seconds')
    with exclusive():
        d = device or Device()
        j = Journal(root, 'prepare-devloop')
        j.report.update(control_build=expected_control_build, devloop_version=expected_devloop_version,
                        timeout_s=timeout_s, ready_for_lua_trial=False, ready_for_script_reload=False,
                        ready_for_input_trial=False, launch_submissions=0,
                        input_actions=0, script_actions=0, native_installation='not performed',
                        expected_devloop_build=expected_devloop_build,identity_limit='Native process identity has not yet been verified')
        keeper = WorkKeeper(d.control, j.folder)
        previous = None
        last_control_uptime = None
        launch_rejected = False
        runtime_pin = None
        started = time.monotonic()
        try:
            d.validate_devloop_endpoint()
            control_idle(d.control_status(), expected_control_build)
            try:
                state = d.status()
            except Exception as error:
                if not transport_unavailable(error):
                    raise
                state = None
                j.event('runtime_unavailable', {'failure_type': type(error).__name__})
            if state is not None:
                script=d.script();healthy(state,script,expected_devloop_version)
                runtime_pin=devloop_runtime_identity(state,expected_devloop_build);check_devloop_runtime(script,runtime_pin)
            control = d.control_status()
            control_idle(control, expected_control_build)
            last_control_uptime = control['uptime_ms']
            keeper.start(control)
            if state is None:
                def submit_launch():
                    j.report['launch_submissions'] += 1
                    return d.launch_devloop()
                try:
                    receipt = j.mutation('launch_devloop', {'title_id': 'CHRS00003'}, submit_launch)
                except Exception as error:
                    launch_rejected = not transport_unavailable(error)
                    j.report['launch_outcome'] = ('rejected or invalid launch exchange; runtime inspection only' if launch_rejected else
                                                  'unconfirmed; inspect runtime without repeating launch')
                    j.report['launch_failure_type'] = type(error).__name__
                else:
                    if (not isinstance(receipt, dict) or receipt.get('title_id') != 'CHRS00003' or
                            receipt.get('action') != 'launch' or type(receipt.get('native_result')) is not int or
                            receipt['native_result'] < 0):
                        launch_rejected = True
                        j.report['launch_outcome'] = 'rejected or invalid native receipt; runtime inspection only'
                    else:
                        j.report['launch_outcome'] = 'native receipt accepted; runtime observation pending'
            else:
                j.report['launch_outcome'] = 'already running; no launch submitted'
            if state is None:
                try:
                    png, screen = d.screen()
                    (j.folder / 'launch-screen.png').write_bytes(png)
                    j.report['launch_screen'] = screen
                except Exception as error:
                    j.report['launch_screen_failure_type'] = type(error).__name__
            deadline = started + timeout_s
            while time.monotonic() < deadline:
                d.validate_devloop_endpoint()
                control = d.control_status()
                check_identity(control, expected_control_build)
                if type(control.get('uptime_ms')) is not int or control['uptime_ms'] < last_control_uptime:
                    raise RuntimeError('Control restarted during preparation')
                last_control_uptime = control['uptime_ms']
                if type(control.get('lease_remaining_ms')) is not int or control['lease_remaining_ms'] != 0:
                    raise RuntimeError('Synthetic input appeared during preparation')
                try:
                    state = d.status()
                except Exception as error:
                    if not transport_unavailable(error):
                        raise
                    j.event('runtime_wait', {'failure_type': type(error).__name__})
                    time.sleep(min(.25, max(0, deadline-time.monotonic())))
                    continue
                script = d.script()
                healthy(state, script, expected_devloop_version)
                if runtime_pin is None and previous is None:runtime_pin=devloop_runtime_identity(state,expected_devloop_build)
                check_devloop_runtime(state,runtime_pin);check_devloop_runtime(script,runtime_pin)
                png, screen = d.screen()
                if type(screen.get('target_pid')) is not int or screen['target_pid'] <= 0:
                    raise RuntimeError('Capture has no valid foreground PID')
                if type(screen.get('sequence')) is not int or screen['sequence'] <= 0:
                    raise RuntimeError('Capture has no valid sequence')
                observation = {'revision': state['revision'], 'frame': state['frame'],
                               'source_sha256': script.get('sha256'), 'display_pid': screen['target_pid'],
                               'native_devloop_pid': devloop_target_pid(state),
                               'screen_sequence': screen.get('sequence')}
                filename = 'screen-1.png' if previous is None else 'screen-2.png'
                (j.folder / filename).write_bytes(png)
                observation['screen_file'] = filename
                j.event('runtime_observation', observation)
                if previous is not None:
                    if observation['display_pid'] != previous['display_pid']:
                        raise RuntimeError('Foreground PID changed during preparation')
                    if observation['screen_sequence'] <= previous['screen_sequence']:
                        raise RuntimeError('Capture sequence stopped advancing during preparation')
                    if (observation['revision'], observation['source_sha256']) != (previous['revision'], previous['source_sha256']):
                        raise RuntimeError('Experiment ownership changed during preparation')
                    if state['frame'] < previous['frame']:
                        raise RuntimeError('DevLoop restarted during preparation')
                    if state['frame'] > previous['frame']:
                        j.report['runtime'] = {'status': state, 'script': script, 'screen': screen}
                        j.report['runtime_identity']=runtime_pin
                        if launch_rejected:
                            raise RuntimeError('Native launch receipt failed; healthy runtime retained as separate evidence')
                        mapped=(observation['native_devloop_pid']==observation['display_pid'] and
                                previous['native_devloop_pid']==previous['display_pid'])
                        pinned=runtime_pin is not None and expected_devloop_build is not None
                        input_ready=mapped and pinned
                        j.report.update(result='ready' if input_ready else 'runtime_ready_build_unpinned' if mapped else 'runtime_ready_target_unverified',
                                        native_candidate_pin_verified=pinned,captured_target_mapped=mapped,
                                        ready_for_script_reload=True,ready_for_input_trial=input_ready,ready_for_lua_trial=input_ready,
                                        identity_limit='Native title/PID matches capture; caller candidate build and observed run are pinned for this job' if input_ready else
                                        'Native title/PID matches capture, but no caller candidate build pin was supplied; input trials are refused' if mapped else
                                        'Native 01.04 title/PID mapping is absent or differs from the capture; input trials are refused',
                                        foreground_evidence='native DevLoop title/PID matches captured foreground' if mapped else
                                        'DevLoop runtime is healthy; captured foreground is not mapped to the native app')
                        break
                previous = observation
                time.sleep(min(.25, max(0, deadline-time.monotonic())))
            else:
                raise RuntimeError('Timed out waiting for advancing paused DevLoop and stable foreground; inspect LiveArea without replaying launch')
        except Exception as error:
            j.report.update(result='blocked', failure_type=type(error).__name__, failure=str(error)[:240])
        finally:
            j.report['work_power'] = keeper.stop()
            j.report['elapsed_s'] = round(time.monotonic()-started, 3)
            j.report['finished_utc'] = utc()
            j.save()
        return {**j.report, 'evidence_directory': str(j.folder)}
