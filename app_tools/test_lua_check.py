"""Portable contract checks plus opt-in actual shared-runtime execution.

Run actual Lua cases with VITA_APP_TEST_DOCKER=1 using the digest-pinned SDK.
These tests open no sockets and do not read device credentials.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from app_tools.lua_check import ROOT, _docker_run, check


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='vita-app-lua-contract-')
        self.addCleanup(self.folder.cleanup)
        self.source = Path(self.folder.name) / 'test.lua'
        self.source.write_text('return {update=function() end,draw=function() end}', encoding='utf-8')

    def test_invalid_inputs_do_not_start_docker(self):
        bad = [dict(frames=0), dict(dt=float('nan')), dict(dt=.1),
               dict(inputs=[{'frame': 1, 'lx': 256}]),
               dict(inputs=[{'frame': 1, 'buttons': 2}]),
               dict(inputs=[{'frame': 1, 'lx': 0}, {'frame': 1, 'lx': 128}])]
        with patch('app_tools.lua_check.shutil.which', side_effect=AssertionError('Docker must not start')):
            for arguments in bad:
                with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                    check(self.source, [{'metric': 'ticks', 'min': 1}], **arguments)

    def test_missing_docker_is_blocked_and_retains_exact_source_identity(self):
        with patch('app_tools.lua_check.shutil.which', return_value=None):
            result = check(self.source, [{'metric': 'ticks', 'min': 1}])
        self.assertEqual(result['result'], 'blocked')
        self.assertEqual(result['failure_type'], 'docker_unavailable')
        self.assertEqual(result['source_sha256'], hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertEqual(result['device_mutations'], 0)
        self.assertFalse(result['native_identity_observed'])

    def test_binary_source_and_invalid_metric_predicate_refuse_before_docker(self):
        with patch('app_tools.lua_check.shutil.which', side_effect=AssertionError('Docker must not start')):
            for checks in ([], [{'metric': 'ticks', 'equals': True}], [{'metric': 'ticks', 'min': 2, 'max': 1}]):
                with self.subTest(checks=checks), self.assertRaises(ValueError):
                    check(self.source, checks)
            self.source.write_bytes(b'return {}\x00')
            with self.assertRaises(ValueError):
                check(self.source, [{'metric': 'ticks', 'min': 1}])

    def test_timed_out_container_is_removed_by_exact_owned_name(self):
        seen = []

        def run(command, **kwargs):
            seen.append(command)
            if len(seen) == 1:
                raise subprocess.TimeoutExpired(command, kwargs['timeout'])
            return subprocess.CompletedProcess(command, 0, '', '')

        with patch('app_tools.lua_check.subprocess.run', side_effect=run):
            with self.assertRaises(subprocess.TimeoutExpired):
                _docker_run('docker', 'image', [], ['/cache/test'], 1)
        name = seen[0][seen[0].index('--name') + 1]
        self.assertRegex(name, '^vita-app-lua-[0-9a-f]{32}$')
        self.assertEqual(seen[1], ['docker', 'rm', '--force', name])
        self.assertIn('none', seen[0])


@unittest.skipUnless(os.environ.get('VITA_APP_TEST_DOCKER') == '1',
                     'Set VITA_APP_TEST_DOCKER=1 for actual shared Lua runtime cases')
class ActualLuaTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='vita-app-lua-real-')
        self.addCleanup(self.folder.cleanup)

    def run_source(self, source, checks=None, **kwargs):
        path = Path(self.folder.name) / 'candidate.lua'
        path.write_text(source, encoding='utf-8', newline='\n')
        result = check(path, checks or [{'metric': 'ticks', 'min': 1}], **kwargs)
        self.assertNotEqual(result['result'], 'blocked', json.dumps(result, indent=2))
        self.assertNotIn('failure_type', result, json.dumps(result, indent=2))
        return result

    def test_original_paddle_starter_has_real_progress_collision_and_bounds(self):
        result = check(ROOT/'app_tools/lua_starter.lua', [
            {'metric': 'frames', 'equals': 120}, {'metric': 'seconds', 'min': 1.99, 'max': 2.01},
            {'metric': 'bounds_ok', 'equals': 1}, {'metric': 'collisions', 'min': 1},
            {'metric': 'score', 'min': 1}, {'metric': 'paddle_x', 'min': 90, 'max': 870},
            {'metric': 'ball_x', 'min': 48, 'max': 912}])
        self.assertEqual(result['result'], 'passed', json.dumps(result, indent=2))
        self.assertEqual(result['updates'], 120)
        self.assertEqual(result['max_draw_commands'], 6)
        self.assertEqual(result['draw_calls'], 720)
        self.assertTrue(all(result['invariants'].values()))
        self.assertGreater(result['peak_memory_bytes'], 0)

    def test_longer_attract_sequence_and_cross_restart_edge(self):
        sustained = check(ROOT/'app_tools/lua_starter.lua', [
            {'metric': 'collisions', 'min': 3}, {'metric': 'score', 'min': 2},
            {'metric': 'bounds_ok', 'equals': 1}], frames=360)
        self.assertEqual(sustained['result'], 'passed', json.dumps(sustained, indent=2))
        restarted = check(ROOT/'app_tools/lua_starter.lua', [
            {'metric': 'restarts', 'equals': 1}, {'metric': 'bounds_ok', 'equals': 1}],
            inputs=[{'frame': 10, 'buttons': 16384}, {'frame': 30, 'buttons': 0}])
        self.assertEqual(restarted['result'], 'passed', json.dumps(restarted, indent=2))
        self.assertTrue(sustained['build_cached'])
        self.assertEqual(sustained['sandbox_build_id'], restarted['sandbox_build_id'])

    def test_controller_values_persist_and_pressed_is_an_edge(self):
        result = self.run_source('''local edges=0
return {update=function(dt,i)
  if (i.pressed & vita.buttons.CROSS)~=0 then edges=edges+1 end
  vita.metric("edges",edges);vita.metric("axis",i.lx)
end,draw=function() vita.rect(24,100,4,4,vita.rgb(1,2,3)) end}''',
            [{'metric': 'edges', 'equals': 2}, {'metric': 'axis', 'equals': 128}], frames=10,
            inputs=[{'frame': 0, 'buttons': 16384, 'lx': 255},
                    {'frame': 5, 'buttons': 0, 'lx': 128}, {'frame': 7, 'buttons': 16384}])
        self.assertEqual(result['result'], 'passed', json.dumps(result, indent=2))
        self.assertEqual(result['draw_calls'], 10)
        self.assertEqual(result['inputs'][2]['lx'], 128)

    def test_app_predicate_and_missing_metric_fail_without_fabricated_values(self):
        result = self.run_source('return {update=function() vita.metric("ticks",3) end,draw=function() end}',
                                 [{'metric': 'ticks', 'min': 4}, {'metric': 'missing', 'min': 0}])
        self.assertEqual(result['result'], 'failed')
        self.assertEqual(result['phase'], 'run')
        self.assertFalse(result['checks'][0]['passed'])
        self.assertIsNone(result['checks'][1]['observed'])

    def test_syntax_error_is_rejected_during_actual_preflight(self):
        result = self.run_source('return {update=function( end}')
        self.assertEqual(result['result'], 'failed')
        self.assertEqual(result['phase'], 'load')
        self.assertEqual(result['observed_frames'], 0)
        self.assertTrue(result['load_error'])

    def test_instruction_budget_stops_real_runtime_loop(self):
        result = self.run_source('return {update=function(dt) if dt>0 then while true do end end end,draw=function() end}')
        self.assertEqual(result['result'], 'failed')
        self.assertEqual(result['phase'], 'runtime_fault')
        self.assertEqual(result['observed_frames'], 1)
        self.assertIn('instruction budget', result['runtime_error'])

    def test_allocator_and_draw_command_guards_reject_candidates(self):
        memory = self.run_source('local s=string.rep("x",2097152); return {update=function() end,draw=function() end}')
        self.assertEqual(memory['result'], 'failed')
        self.assertEqual(memory['phase'], 'load')
        self.assertIn('memory', memory['load_error'])
        drawing = self.run_source('return {update=function() end,draw=function() for n=1,257 do vita.rect(24,100,1,1,1) end end}')
        self.assertEqual(drawing['result'], 'failed')
        self.assertIn('drawing budget', drawing['load_error'])

    def test_filesystem_api_is_absent_in_actual_sandbox(self):
        result = self.run_source('return {update=function(dt) if dt>0 then io.open("never-written","w") end end,draw=function() end}')
        self.assertEqual(result['result'], 'failed')
        self.assertEqual(result['phase'], 'runtime_fault')
        self.assertIn('nil', result['runtime_error'])


if __name__ == '__main__':
    unittest.main()
