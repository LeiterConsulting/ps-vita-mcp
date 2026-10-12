"""Actual stdio MCP and CLI acceptance against the local HTTP session fixture.

Resident/Control configuration is deliberately unavailable.  These tests prove
public transport composition, not native Lua execution or physical Vita behavior.
Run: python -m unittest workbench.test_script_session_mcp -v
"""
import asyncio
from contextlib import asynccontextmanager
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import workbench.test_script_session as fixtures

ROOT = Path(__file__).resolve().parents[1]


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        # Reuse the complete actual-HTTP fixture without inheriting/re-running
        # its decision tests or duplicating the native protocol simulation.
        self.fixture = fixtures.SessionTests(methodName='test_native_scene_restored_world_unchanged_last_lua_inactive')
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root
        config = self.root / 'devloop.json'
        config.write_text(json.dumps(self.fixture.config), encoding='utf-8')
        self.env = {**os.environ, 'VITA_DEVLOOP_CONFIG': str(config),
                    'VITA_RESIDENT_CONFIG': str(self.root / 'missing-resident-config.json'),
                    'VITA_CONTROL_PORT': '0', 'VITA_WORKBENCH_ROOT': str(self.root),
                    'VITA_WORKBENCH_LOCK': str(self.root / 'shared-session.lock')}

    @asynccontextmanager
    async def mcp(self):
        parameters = StdioServerParameters(command=sys.executable,
                                           args=[str(ROOT / 'resident/bridge.py')], env=self.env,
                                           cwd=str(ROOT))
        async with stdio_client(parameters) as streams:
            async with ClientSession(*streams) as client:
                await client.initialize()
                yield client

    def value(self, result):
        self.assertFalse(result.isError, result)
        value = result.structuredContent or json.loads(next(c.text for c in result.content if c.type == 'text'))
        self.assertNotIn(fixtures.TOKEN, json.dumps(value))
        self.assertNotIn('127.0.0.1', json.dumps(value))
        return value

    def arguments(self, candidates=None, revision=10, **kwargs):
        return {'candidates': candidates or [fixtures.candidate()], 'expected_devloop_build': fixtures.BUILD,
                'expected_pid': 77, 'expected_run': fixtures.RUN, 'expected_revision': revision, **kwargs}

    def assert_no_control_calls(self):
        self.assertTrue(all(path in ('/status', '/script') for path in self.fixture.gets))
        self.assertTrue(all(path in ('/script', '/control') for path, _, _ in self.fixture.posts))
        self.assertTrue(all(header == 'Bearer ' + fixtures.TOKEN for header in self.fixture.incoming))

    def cli(self, *args):
        return subprocess.run([sys.executable, '-m', 'workbench.cli', *args], cwd=ROOT,
                              env=self.env, capture_output=True, timeout=30, check=False)

    def manifest(self, fields):
        path = self.root / 'script-session.json'
        raw = (json.dumps(fields, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        path.write_bytes(raw)
        return path, hashlib.sha256(raw).hexdigest()

    def test_catalog_40_tools_16_workbench_and_exact_session_schemas(self):
        async def run():
            async with self.mcp() as client:
                tools = (await client.list_tools()).tools
                self.assertEqual(len(tools), 40)
                self.assertEqual(sum(t.name.startswith('vita_workbench_') for t in tools), 16)
                self.assertEqual(sum(t.name.startswith('vita_control_') for t in tools), 13)
                self.assertEqual(sum(t.name.startswith('vita_resident_') for t in tools), 11)
                session = next(t for t in tools if t.name == 'vita_workbench_script_session')
                self.assertEqual(set(session.inputSchema['required']),
                                 {'candidates', 'expected_devloop_build', 'expected_pid', 'expected_run', 'expected_revision'})
                self.assertEqual(set(session.inputSchema['properties']),
                                 {'candidates', 'expected_devloop_build', 'expected_pid', 'expected_run',
                                  'expected_revision', 'retain_best', 'selection'})
                prepare = next(t for t in tools if t.name == 'vita_workbench_prepare_script_session')
                self.assertEqual(prepare.inputSchema['required'], ['expected_devloop_build'])
                for tool in (session, prepare):
                    self.assertFalse(tool.annotations.readOnlyHint)
                    self.assertFalse(tool.annotations.idempotentHint)
        asyncio.run(run())
        self.assertEqual(self.fixture.gets, [])
        self.assertEqual(self.fixture.posts, [])

    def test_prepare_and_two_candidate_session_restore_original_without_resident_or_control(self):
        self.fixture.baseline_lua()
        original = copy.deepcopy(self.fixture.current)
        async def run():
            async with self.mcp() as client:
                before = len(self.fixture.gets)
                self.assertTrue((await client.call_tool('vita_resident_status')).isError)
                self.assertEqual(len(self.fixture.gets), before)
                ready = self.value(await client.call_tool('vita_workbench_prepare_script_session',
                                                         {'expected_devloop_build': fixtures.BUILD, 'timeout_s': 2}))
                self.assertEqual(ready['result'], 'script_ready')
                self.assertTrue(ready['ready_for_script_reload'])
                self.assertFalse(ready['ready_for_input_trial'])
                self.assertEqual(ready['launch_submissions'], 0)
                self.assertEqual(ready['runtime_identity'], fixtures.PIN)
                self.assertEqual(self.fixture.posts, [])
                args = self.arguments([fixtures.candidate('low', 2), fixtures.candidate('high', 7)],
                                      revision=ready['expected_revision'], selection={'metric': 'score', 'direction': 'max'})
                report = self.value(await client.call_tool('vita_workbench_script_session', args))
                self.assertEqual(report['result'], 'passed', report)
                self.assertEqual(report['best']['name'], 'high')
                self.assertEqual([i['result'] for i in report['iterations']], ['accepted', 'accepted'])
                self.assertEqual(report['restoration'], 'original_scene_paused_verified')
                self.assertEqual(report['runtime_identity'], fixtures.PIN)
                self.assertEqual(report['input_actions'], 0)
                self.assertEqual(report['control_actions'], 0)
                self.assertNotIn('events', report)
                for item in args['candidates']: self.assertNotIn(item['source'], json.dumps(report))
                folder = Path(report['evidence_directory'])
                self.assertTrue((folder / 'report.json').is_file())
                events = [json.loads(line) for line in (folder / 'journal.jsonl').read_text().splitlines()]
                intents = [e for e in events if e['kind'] == 'mutation_intent']
                self.assertEqual(len(intents), len(self.fixture.posts))
                self.assertEqual(sum(e['kind'] == 'original_restored_paused' for e in events), 2)
        asyncio.run(run())
        self.assertEqual(self.fixture.current, original)
        self.assertTrue(self.fixture.paused)
        self.assertEqual(self.fixture.world, fixtures.WORLD)
        self.assert_no_control_calls()

    def test_mcp_lost_write_reconciles_get_only_without_replay_or_cleanup(self):
        self.fixture.drop_operation = 'load'
        async def run():
            async with self.mcp() as client:
                report = self.value(await client.call_tool('vita_workbench_script_session', self.arguments()))
                self.assertEqual(report['result'], 'unconfirmed', report)
                self.assertEqual(report['reconciliation'], 'expected_post_state_observed')
                self.assertEqual(report['restoration'], 'skipped_unconfirmed_or_drifted_no_further_mutation')
                self.assertEqual(report['mutation_submissions'], 1)
        asyncio.run(run())
        self.assertEqual([action for _, action, _ in self.fixture.posts], ['load'])
        self.assertTrue(self.fixture.paused)
        self.assertTrue(self.fixture.current['active'])
        self.assert_no_control_calls()

    def test_mcp_invalid_source_hash_extra_candidate_field_and_bad_pins_reject_before_http(self):
        async def run():
            async with self.mcp() as client:
                for fields in (self.arguments([fixtures.candidate(source_sha256='0' * 64)]),
                               self.arguments([fixtures.candidate(unknown=True)]),
                               {**self.arguments(), 'expected_devloop_build': 'invalid'}):
                    result = await client.call_tool('vita_workbench_script_session', fields)
                    self.assertTrue(result.isError)
                    self.assertNotIn(fixtures.TOKEN, ''.join(c.text for c in result.content if c.type == 'text'))
                bad = await client.call_tool('vita_workbench_prepare_script_session', {'expected_devloop_build': 'invalid'})
                self.assertTrue(bad.isError)
        asyncio.run(run())
        self.assertEqual(self.fixture.gets, [])
        self.assertEqual(self.fixture.posts, [])

    def test_cli_prepare_then_sha_pinned_session_restores_native_paused(self):
        prepared = self.cli('prepare-script', fixtures.BUILD, '--timeout', '2')
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        ready = json.loads(prepared.stdout)
        self.assertEqual(ready['result'], 'script_ready')
        self.assertEqual(ready['runtime_identity'], fixtures.PIN)
        self.assertFalse(ready['ready_for_input_trial'])
        self.assertEqual(self.fixture.posts, [])
        path, digest = self.manifest(self.arguments([fixtures.candidate('first'), fixtures.candidate('second', 5)],
                                                    revision=ready['expected_revision']))
        executed = self.cli('script-session', str(path), digest)
        self.assertEqual(executed.returncode, 0, executed.stdout + executed.stderr)
        report = json.loads(executed.stdout)
        self.assertEqual(report['result'], 'passed')
        self.assertEqual(len(report['iterations']), 2)
        self.assertEqual(report['restoration'], 'original_scene_paused_verified')
        self.assertFalse(self.fixture.current['active'])
        self.assertTrue(self.fixture.paused)
        self.assertEqual(self.fixture.world, fixtures.WORLD)
        self.assertNotIn(fixtures.TOKEN.encode(), executed.stdout)
        self.assert_no_control_calls()

    def test_cli_invalid_manifest_hash_and_extra_fields_reject_before_http(self):
        path, digest = self.manifest(self.arguments())
        wrong_hash = self.cli('script-session', str(path), '0' * 64)
        self.assertNotEqual(wrong_hash.returncode, 0)
        self.assertIn(b'Manifest hash differs', wrong_hash.stderr)
        for fields in ({**self.arguments(), 'unknown_manifest_field': True},
                       self.arguments([fixtures.candidate(unknown_candidate_field=True)]),
                       self.arguments([fixtures.candidate(source_sha256='0' * 64)])):
            path, digest = self.manifest(fields)
            result = self.cli('script-session', str(path), digest)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn(fixtures.TOKEN.encode(), result.stdout + result.stderr)
        self.assertEqual(self.fixture.gets, [])
        self.assertEqual(self.fixture.posts, [])


if __name__ == '__main__': unittest.main(verbosity=2)
