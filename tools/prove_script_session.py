"""Run two measured Lua candidates through actual stdio MCP, restoring the scene.

Requires an already-open, paused DevLoop 01.04 and an exact native build pin.
No launch, Control, installation, input or boot configuration changes occur.
Use --retain-best explicitly to leave the selected source fresh and paused.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import uuid
import re

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


def candidates():
    result = []
    for name, speed in [('steady', 60), ('swift', 120)]:
        source = f'''local distance, ticks, elapsed = 0, 0, 0
local speed = {speed}
local ink = vita.rgb(64,220,191)
return {{
  update = function(dt,input)
    distance = distance + speed*dt
    elapsed = elapsed + dt
    ticks = ticks + 1
    vita.metric("distance", distance)
    vita.metric("ticks", ticks)
    vita.metric("speed", speed)
    vita.metric("elapsed", elapsed)
    vita.metric("rate", distance/math.max(elapsed,0.001))
  end,
  draw = function()
    vita.rect(24,100,912,380,vita.rgb(20,32,49))
    vita.text(44,130,1,ink,"Autonomous script session: {name}")
    vita.circle(60 + distance%820,280,16,ink)
    vita.text(44,400,0.8,ink,"Measured movement; original scene restored after test")
  end
}}
'''
        result.append({'name': name, 'source': source,
                       'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                       'warmup_s': 0.25, 'duration_s': 2,
                       'checks': [{'metric': 'distance', 'min': 0.001}, {'metric': 'ticks', 'min': 5},
                                  {'metric': 'rate', 'min': speed*.99, 'max': speed*1.01}]})
    return result


def value(result):
    if result.isError:
        raise RuntimeError('MCP call rejected; inspect the local server log before another job')
    answer = result.structuredContent
    if answer is None:
        answer = json.loads(next(block.text for block in result.content if block.type == 'text'))
    if not isinstance(answer, dict):
        raise RuntimeError('MCP returned invalid report metadata')
    return answer


def preparation_identity(prepared, build):
    """Ready flags alone cannot authorize a differently pinned native session."""
    identity = prepared.get('runtime_identity')
    if (prepared.get('result') != 'script_ready' or prepared.get('ready_for_script_reload') is not True or
            type(prepared.get('launch_submissions')) is not int or prepared['launch_submissions'] != 0 or
            not isinstance(identity, dict) or identity.get('app') != 'Vita DevLoop' or
            type(identity.get('protocol')) is not int or identity['protocol'] != 1 or
            identity.get('version') != '01.04' or identity.get('title_id') != 'CHRS00003' or
            identity.get('build_id') != build or type(identity.get('pid')) is not int or identity['pid'] <= 0 or
            not isinstance(identity.get('run'), str) or not re.fullmatch('[0-9a-f]{32}', identity['run']) or
            type(prepared.get('expected_revision')) is not int or not 1 <= prepared['expected_revision'] < 0xffffffff):
        raise RuntimeError('Preparation did not verify the exact paused native session; no script job submitted')
    return dict(identity)


def proof_checks(report, manifest, identity):
    """Require both generated scenes, fresh execution, ranking and restoration."""
    observed = report.get('iterations')
    expected = manifest['candidates']
    complete = isinstance(observed, list) and len(observed) == len(expected)
    metrics = []
    accepted = complete
    advancing = complete
    if complete:
        for index, (actual, planned) in enumerate(zip(observed, expected)):
            if not isinstance(actual, dict):
                accepted = advancing = False
                continue
            values = actual.get('metrics', {})
            valid_metrics = (isinstance(values, dict) and all(type(values.get(key)) in (int, float) and
                            math.isfinite(values[key]) for key in ('distance', 'ticks', 'speed', 'elapsed', 'rate')))
            accepted = bool(accepted and actual.get('index') == index and actual.get('name') == planned['name'] and
                            actual.get('source_sha256') == planned['source_sha256'] and actual.get('accepted') is True and
                            actual.get('result') == 'accepted' and valid_metrics and values['distance'] > 0 and
                            values['elapsed'] > 0 and values['ticks'] >= 5 and values['speed'] == (60 if index == 0 else 120) and
                            math.isclose(values['rate'], values['speed'], rel_tol=.01))
            numeric_progress = all(type(actual.get(key)) is int for key in
                                   ('first_frame', 'last_frame', 'first_updates', 'last_updates', 'samples'))
            advancing = bool(advancing and numeric_progress and actual['samples'] > 0 and
                             actual['first_frame'] > 0 and actual['last_frame'] > actual['first_frame'] and
                             actual['first_updates'] >= 0 and actual['last_updates'] > actual['first_updates'])
            metrics.append(values if valid_metrics else {})
    faster = bool(accepted and len(metrics) == 2 and metrics[1]['rate'] > metrics[0]['rate'])
    best = report.get('best')
    best_matches = bool(isinstance(best, dict) and best.get('index') == 1 and best.get('name') == 'swift' and
                        best.get('source_sha256') == expected[1]['source_sha256'])
    restoration = report.get('restoration') == ('best_source_retained_fresh_vm_paused' if manifest['retain_best'] else
                                               'original_scene_paused_verified')
    if manifest['retain_best']:
        retained = report.get('retained_scene')
        restoration = bool(restoration and isinstance(retained, dict) and retained.get('name') == 'swift' and
                           retained.get('sha256') == expected[1]['source_sha256'] and retained.get('paused') is True and
                           retained.get('active') is True and retained.get('faulted') is False)
    return {'both_exact_candidates_accepted': accepted, 'fresh_execution_observed': advancing,
            'swift_rate_exceeds_steady': faster, 'swift_selected': best_matches,
            'expected_restoration_verified': restoration,
            'same_pinned_runtime': report.get('runtime_identity') == identity and
                                   report.get('requested_revision') == manifest['expected_revision']}


async def prove(build, retain_best=False):
    if not isinstance(build, str) or not re.fullmatch('[0-9a-f]{64}', build) or type(retain_best) is not bool:
        raise ValueError('Supply an exact native build SHA-256 and explicit boolean retention intent')
    evidence_root = Path(os.environ.get('VITA_WORKBENCH_ROOT', str(ROOT)))
    directory = evidence_root / '.devloop-private/script-session-proofs' / uuid.uuid4().hex
    directory.mkdir(parents=True)
    parameters = StdioServerParameters(command=sys.executable, args=[str(ROOT / 'resident/bridge.py')], env=dict(os.environ))
    async with stdio_client(parameters) as streams:
        async with ClientSession(*streams, read_timeout_seconds=timedelta(seconds=180)) as client:
            await client.initialize()
            prepared = value(await client.call_tool('vita_workbench_prepare_script_session', {'expected_devloop_build': build}))
            (directory / 'preparation.json').write_text(json.dumps(prepared, indent=2) + '\n', encoding='utf-8')
            if not prepared.get('ready_for_script_reload'):
                return {'result': 'blocked', 'launch_submissions': 0, 'evidence_directory': str(directory),
                        'failure': 'Open paused DevLoop 01.04 with the pinned build before running this proof'}
            identity = preparation_identity(prepared, build)
            manifest = {'candidates': candidates(), 'expected_devloop_build': build,
                        'expected_pid': identity['pid'], 'expected_run': identity['run'],
                        'expected_revision': prepared['expected_revision'], 'retain_best': retain_best,
                        'selection': {'metric': 'rate', 'direction': 'max'}}
            raw = (json.dumps(manifest, indent=2) + '\n').encode()
            (directory / 'manifest.json').write_bytes(raw)
            report = value(await client.call_tool('vita_workbench_script_session', manifest))
            checks = proof_checks(report, manifest, identity)
            result = {**report, 'manifest_sha256': hashlib.sha256(raw).hexdigest(),
                      'manifest_path': str(directory / 'manifest.json'), 'proof_checks': checks,
                      'measurement_note': 'Metrics are cumulative simulation observations; HTTP latency makes duration_s a polling window rather than an exact simulation or wall-clock interval. Ranking uses distance divided by observed simulation elapsed time.',
                      'proof_passed': report.get('result') == 'passed' and all(checks.values())}
            if report.get('result') == 'passed' and not result['proof_passed']:
                result.update(result='failed_proof', failure='The complete generated-scene proof did not meet its acceptance checks')
            (directory / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
            return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build', help='Exact DevLoop 01.04 native build SHA-256')
    parser.add_argument('--retain-best', action='store_true', help='Leave selected source fresh and paused instead of original scene')
    args = parser.parse_args()
    result = asyncio.run(prove(args.build, args.retain_best))
    print(json.dumps(result, indent=2))
    return 0 if result.get('result') == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
