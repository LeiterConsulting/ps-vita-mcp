"""Demo-source proof through pinned Docker Lua and actual MCP HTTP fixtures.

Run: python tests/test_script_demo.py
No Vita is contacted. The real Lua engine test uses generated exact helper
sources, shared core/runtime/render stubs, ASAN/UBSAN and network-disabled Docker.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import prove_script_session as demo
from workbench.script_session import validate
import workbench.test_script_session as fixtures


class SourceTests(unittest.TestCase):
    def test_generated_candidates_exact_utf8_hashes_and_bounded_schema(self):
        items = demo.candidates()
        normalized, selection = validate(items, fixtures.BUILD, 77, fixtures.RUN, 10,
                                         selection={'metric': 'rate', 'direction': 'max'})
        self.assertEqual([i['name'] for i in normalized], ['steady', 'swift'])
        self.assertEqual(selection, {'metric': 'rate', 'direction': 'max'})
        for item in items:
            self.assertEqual(hashlib.sha256(item['source'].encode('utf-8')).hexdigest(), item['source_sha256'])
            self.assertEqual(item['duration_s'], 2)
            self.assertEqual(item['warmup_s'], .25)

    def test_proof_cannot_accept_partial_success_or_wrong_ranking(self):
        items = demo.candidates()
        manifest = {'candidates': items, 'expected_revision': 10, 'retain_best': False}
        report = {'runtime_identity': fixtures.PIN, 'requested_revision': 10,
                  'restoration': 'original_scene_paused_verified',
                  'best': {'index': 1, 'name': 'swift', 'source_sha256': items[1]['source_sha256']},
                  'iterations': [{'index': index, 'name': item['name'], 'source_sha256': item['source_sha256'],
                                  'accepted': True, 'result': 'accepted',
                                  'metrics': {'distance': distance, 'ticks': 121, 'speed': speed, 'elapsed': distance/speed, 'rate': speed},
                                  'first_frame': 100, 'last_frame': 220, 'first_updates': 0, 'last_updates': 120, 'samples': 8}
                                 for index, (item, speed, distance) in enumerate(zip(items, (60, 120), (300, 240)))]}
        self.assertTrue(all(demo.proof_checks(report, manifest, fixtures.PIN).values()))
        for mutate in (lambda value: value['iterations'].pop(),
                       lambda value: value['iterations'][0].update(accepted=False),
                       lambda value: value['iterations'][1]['metrics'].update(rate=40),
                       lambda value: value['iterations'][1]['metrics'].update(speed=float('nan')),
                       lambda value: value['best'].update(name='steady'),
                       lambda value: value.update(restoration='unconfirmed'),
                       lambda value: value['runtime_identity'].update(run='e'*32)):
            altered = copy.deepcopy(report)
            mutate(altered)
            self.assertFalse(all(demo.proof_checks(altered, manifest, fixtures.PIN).values()))

    def test_bad_build_rejects_before_stdio_or_evidence_creation(self):
        import asyncio
        with patch.object(demo, 'stdio_client', side_effect=AssertionError('must not start transport')):
            with self.assertRaises(ValueError): asyncio.run(demo.prove('invalid'))

    def test_ready_flag_without_exact_preparation_pin_does_not_authorize_job(self):
        prepared = {'result': 'script_ready', 'ready_for_script_reload': True, 'launch_submissions': 0,
                    'runtime_identity': fixtures.PIN, 'expected_revision': 10}
        self.assertEqual(demo.preparation_identity(prepared, fixtures.BUILD), fixtures.PIN)
        for mutate in (lambda value: value['runtime_identity'].update(build_id='d'*64),
                       lambda value: value['runtime_identity'].update(pid=True),
                       lambda value: value.update(expected_revision=True),
                       lambda value: value.update(launch_submissions=1)):
            altered = copy.deepcopy(prepared)
            mutate(altered)
            with self.assertRaises(RuntimeError): demo.preparation_identity(altered, fixtures.BUILD)


class RuntimeTests(unittest.TestCase):
    def test_exact_generated_sources_real_lua_preflight_update_draw_rank_and_restore(self):
        image = json.loads((ROOT / 'toolchain.lock.json').read_text())['image']
        self.assertRegex(image, r'^[a-z0-9./_-]+@sha256:[0-9a-f]{64}$')
        docker = shutil.which('docker')
        if docker is None:
            candidate = Path(r'C:\Program Files\Docker\Docker\resources\bin\docker.exe')
            if candidate.is_file(): docker = str(candidate)
        self.assertIsNotNone(docker, 'Pinned Docker host runtime is required for the real Lua test')
        relative = 'build/host/session-demo/' + uuid.uuid4().hex
        folder = ROOT / relative
        folder.mkdir(parents=True)
        items = demo.candidates()
        for item in items: (folder / (item['name'] + '.lua')).write_bytes(item['source'].encode('utf-8'))
        (folder / 'sources.json').write_text(json.dumps(items, indent=2) + '\n', encoding='utf-8')
        user = ['--user', f'{os.getuid()}:{os.getgid()}'] if os.name == 'posix' else []
        command = [docker, 'run', '--rm', '--network', 'none', *user, '--mount',
                   f'type=bind,source={ROOT},target=/workspace', '--workdir', '/workspace',
                   image, 'sh', 'scripts/test_script_demo.sh', relative]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=180)
        (folder / 'runtime.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        self.assertEqual(result.returncode, 0, (result.stdout + result.stderr)[-6000:])
        report = json.loads((folder / 'runtime-report.json').read_text())
        for item, speed, updates in zip(items, (60, 120), (300, 120)):
            measured = report[item['name']]
            self.assertEqual(measured['sha256'], item['source_sha256'])
            for key in ('distance', 'ticks', 'speed', 'elapsed', 'rate'): self.assertTrue(math.isfinite(measured[key]))
            self.assertAlmostEqual(measured['distance'], speed * updates/60, places=2)
            self.assertAlmostEqual(measured['elapsed'], updates/60, places=2)
            self.assertAlmostEqual(measured['rate'], speed, places=2)
            self.assertEqual(measured['speed'], speed)
            self.assertEqual(measured['ticks'], updates+1)
            self.assertEqual(measured['updates'], updates)
        self.assertGreater(report['steady']['distance'], report['swift']['distance'])
        self.assertGreater(report['swift']['rate'], report['steady']['rate'])
        self.assertEqual(report['selection_metric'], 'rate')
        self.assertEqual(report['best'], 'swift')
        self.assertTrue(report['original_vm_restored_paused'])
        self.assertTrue(report['native_world_unchanged'])


class HelperTransportTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SessionTests(methodName='test_native_scene_restored_world_unchanged_last_lua_inactive')
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        config = self.fixture.root / 'devloop.json'
        config.write_text(json.dumps(self.fixture.config), encoding='utf-8')
        self.env = {**os.environ, 'VITA_DEVLOOP_CONFIG': str(config),
                    'VITA_RESIDENT_CONFIG': str(self.fixture.root / 'missing-resident.json'),
                    'VITA_CONTROL_PORT': '0', 'VITA_WORKBENCH_ROOT': str(self.fixture.root),
                    'VITA_WORKBENCH_LOCK': str(self.fixture.root / 'proof.lock')}
        # HTTP still uses the complete transport fixture. Its scalar metric
        # adapter models elapsed movement; the separate real Lua test qualifies
        # these exact helper sources and callbacks rather than this simulation.
        original_vm = self.fixture.vm
        def vm(name, raw, score):
            result = original_vm(name, raw, score)
            speed = re.search(rb'local speed = (\d+)', raw)
            if speed: result['metrics'] = {'distance': 0, 'ticks': 0, 'speed': int(speed.group(1)), 'elapsed': 0, 'rate': 0}
            return result
        self.fixture.vm = vm
        original_snapshot = self.fixture.snapshot
        def snapshot(script=False):
            value = original_snapshot(script)
            current = self.fixture.current
            if current and 'speed' in current['metrics']:
                current['metrics']['distance'] = current['updates'] * current['metrics']['speed'] / 60
                current['metrics']['elapsed'] = current['updates'] / 60
                current['metrics']['rate'] = current['metrics']['distance'] / max(current['metrics']['elapsed'], .001)
                if script: value['metrics'] = dict(current['metrics'])
            return value
        self.fixture.snapshot = snapshot

    def test_actual_helper_stdio_prepare_run_rank_and_restore_without_control(self):
        executed = subprocess.run([sys.executable, str(ROOT / 'tools/prove_script_session.py'), fixtures.BUILD],
                                  cwd=ROOT, env=self.env, capture_output=True, timeout=30)
        self.assertEqual(executed.returncode, 0, executed.stdout + executed.stderr)
        report = json.loads(executed.stdout)
        self.assertEqual(report['result'], 'passed')
        self.assertTrue(report['proof_passed'])
        self.assertTrue(all(report['proof_checks'].values()))
        self.assertEqual(report['best']['name'], 'swift')
        self.assertFalse(self.fixture.current['active'])
        self.assertTrue(self.fixture.paused)
        self.assertEqual(self.fixture.world, fixtures.WORLD)
        manifest = Path(report['manifest_path']).read_bytes()
        self.assertEqual(hashlib.sha256(manifest).hexdigest(), report['manifest_sha256'])
        self.assertNotIn(fixtures.TOKEN.encode(), executed.stdout)
        self.assertTrue(all(path in ('/status', '/script') for path in self.fixture.gets))


if __name__ == '__main__': unittest.main(verbosity=2)
