"""Focused project/path, compiler-argv and publication recovery checks."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import vita_native_slot as slot


class NativeSlotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        shutil.copytree(slot.ROOT / 'app_slot/templates', self.root / 'app_slot/templates')
        for relative in slot.FRAMEWORK_FILES:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(slot.ROOT / relative, target)

    def tearDown(self):
        self.temporary.cleanup()

    def project(self):
        return slot.scaffold('.devloop-private/vita-apps/paddle/native-slot', name='paddle',
                             display_name='Vita Paddle', root=self.root)

    def test_scaffold_fixed_identity_and_hashes(self):
        result = self.project()
        self.assertEqual((result['route'], result['title_id'], result['port']), ('native-slot', 'VMCP00001', 17868))
        self.assertEqual(len(result['source_sha256']), 6)
        self.assertEqual(result, slot.inspect(result['project_directory'], root=self.root))
        with self.assertRaises(FileExistsError):
            self.project()

    def test_path_escape_and_shell_characters_refused(self):
        for path in ('../escape', 'a/../escape', 'a b', 'a;whoami', 'a$(whoami)', self.root.parent / 'outside'):
            with self.subTest(path=str(path)), self.assertRaises(ValueError):
                slot.scaffold(path, name='safe', root=self.root)

    def test_manifest_identity_and_unknown_commands_refused(self):
        result = self.project()
        path = self.root / result['project_directory'] / 'native-slot.json'
        original = json.loads(path.read_text())
        for change in ({'title_id': 'CHRS00003'}, {'build_command': 'whoami'},
                       {'module_api': True}, {'name': '../../app'}, {'display_name': 'x";system("x")'}):
            path.write_text(json.dumps({**original, **change}))
            with self.subTest(change=change), self.assertRaises(ValueError):
                slot.inspect(result['project_directory'], root=self.root)
        path.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError):
            slot.inspect(result['project_directory'], root=self.root)

    def test_extra_file_and_source_drift_are_observable(self):
        result = self.project()
        directory = self.root / result['project_directory']
        app = directory / 'app_sim.c'
        app.write_bytes(app.read_bytes() + b'\n/* changed source */\n')
        changed = slot.inspect(result['project_directory'], root=self.root)
        self.assertNotEqual(result['module_sha256'], changed['module_sha256'])
        (directory / 'unreviewed.h').write_text('extra')
        with self.assertRaises(ValueError):
            slot.inspect(result['project_directory'], root=self.root)

    def test_linked_source_refused(self):
        result = self.project()
        directory = self.root / result['project_directory']
        source = directory / 'app.c'
        original = directory.parent / 'external.c'
        source.rename(original)
        try:
            source.symlink_to(original)
        except OSError:
            self.skipTest('Host does not permit creation of a test symlink')
        with self.assertRaises(ValueError):
            slot.inspect(result['project_directory'], root=self.root)

    def test_container_commands_use_argv_and_disable_network(self):
        log = self.root / 'command.log'
        with patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            slot._run(self.root, slot._image(self.root), ['cc', 'project/app_sim.c', '-o', 'build/tests'], log)
        arguments = run.call_args.args[0]
        self.assertEqual(arguments[:4], ['docker', 'run', '--rm', '--name'])
        self.assertRegex(arguments[4], r'^vita-native-slot-[0-9a-f]{32}$')
        self.assertEqual(arguments[5:7], ['--network', 'none'])
        self.assertEqual(arguments[-4:], ['cc', 'project/app_sim.c', '-o', 'build/tests'])
        self.assertIs(run.call_args.kwargs['shell'], False)
        self.assertEqual(run.call_args.kwargs['timeout'], 180)

    def test_timeout_removes_only_the_uniquely_owned_container(self):
        log = self.root / 'timed-out.log'
        failure = subprocess.TimeoutExpired(['docker', 'run'], 180)
        removed = subprocess.CompletedProcess([], 0)
        with patch.object(subprocess, 'run', side_effect=[failure, removed]) as run:
            with self.assertRaisesRegex(RuntimeError, 'timed out; owned-container cleanup confirmed'):
                slot._run(self.root, slot._image(self.root), ['build/tests'], log)
        first, second = run.call_args_list
        owned_name = first.args[0][4]
        self.assertEqual(second.args[0], ['docker', 'rm', '--force', owned_name])
        self.assertEqual(second.kwargs['timeout'], 15)
        self.assertIs(second.kwargs['shell'], False)
        self.assertIn('uniquely owned container', log.read_text())

    def test_timeout_retains_unconfirmed_container_cleanup(self):
        failure = subprocess.TimeoutExpired(['docker'], 180)
        with patch.object(subprocess, 'run', side_effect=[failure, failure]):
            with self.assertRaisesRegex(RuntimeError, 'cleanup unconfirmed'):
                slot._run(self.root, slot._image(self.root), ['build/tests'], self.root / 'cleanup.log')

    def test_host_source_drift_stops_verification(self):
        result = self.project()
        calls = []
        def run(root, image, arguments, log):
            calls.append(arguments)
            log.write_text('test fixture')
            if '-MF' in arguments:
                dep = root / arguments[arguments.index('-MF') + 1]
                source = arguments[arguments.index('-c') + 1]
                dep.write_text(f'test.o: {source} {result["project_directory"]}/app_sim.h\n')
            if len(calls) == 2:
                path = root / result['project_directory'] / 'app_sim.c'
                path.write_bytes(path.read_bytes() + b'\n/* concurrent edit */\n')
        with patch.object(slot, '_run', side_effect=run), self.assertRaises(ValueError):
            slot.check(result['project_directory'], root=self.root)
        self.assertEqual(len(calls), 2)

    def test_make_dependencies_handle_continuations_and_escaped_spaces(self):
        raw = 'build/app.o: project/app.c \\\n project/app.h /workspace/project/escaped\\ space.h\n'
        self.assertEqual(slot._make_dependencies(raw),
                         ['project/app.c', 'project/app.h', '/workspace/project/escaped space.h'])

    def test_actual_dependency_allowlist_rejects_unpinned_repo_headers(self):
        pins = {'project/app.c': 'a' * 64, 'project/app.h': 'b' * 64}
        accepted = slot._verify_dependencies(['project/app.c', 'project/app.h', '/usr/include/math.h'],
                                              pins, ['project/app.c'])
        self.assertTrue(accepted['verified'])
        self.assertEqual(accepted['system_dependency_count'], 1)
        for header in ('/workspace/private/header.h', 'project/../private.h', '/workspace/project/escaped space.h'):
            with self.subTest(header=header), self.assertRaisesRegex(ValueError, 'Undeclared'):
                slot._verify_dependencies(['project/app.c', header], pins, ['project/app.c'])

    def test_native_dependency_output_covers_translation_units(self):
        raw = ('Owned native-slot build container: test\n'
               'CMakeFiles/native_lab.dir/app.c.obj: #deps 2, deps mtime 0 (VALID)\n'
               '    /workspace/project/app.c\n    /workspace/project/app.h\n\n')
        parsed = slot._ninja_dependencies(raw)
        self.assertEqual(parsed, ['/workspace/project/app.c', '/workspace/project/app.h'])
        with self.assertRaisesRegex(ValueError, 'every declared translation unit'):
            slot._verify_dependencies(parsed, {'project/app.c': 'a', 'project/app.h': 'b'},
                                      ['project/app.c', 'project/app_sim.c'])

    def test_compiler_snapshot_exposes_only_declared_pins(self):
        declared = self.root / 'declared.c'
        declared.write_bytes(b'int declared;\n')
        (self.root / 'private.bin').write_bytes(b'private unpinned bytes')
        pins = {'declared.c': slot._sha(declared.read_bytes())}
        snapshot = slot._compiler_snapshot(self.root, pins, self.root / 'isolated')
        self.assertEqual((snapshot / 'declared.c').read_bytes(), declared.read_bytes())
        self.assertFalse((snapshot / 'private.bin').exists())
        self.assertEqual([item.name for item in snapshot.iterdir()], ['declared.c'])

    def test_config_is_content_bound_and_immutable(self):
        application = self.project()['application']
        path = slot._config(self.root, application)
        self.assertEqual(path, slot._config(self.root, application))
        (self.root / path).write_text('changed')
        with self.assertRaises(ValueError):
            slot._config(self.root, application)

    def test_invalid_candidate_preserves_existing_dist(self):
        destination = self.root / 'dist/native-lab'
        destination.mkdir(parents=True)
        (destination / 'original.txt').write_bytes(b'original candidate')
        candidate = self.root / 'candidate'
        def invalid(*args, **kwargs):
            raise ValueError('candidate rejected before publication')
        with self.assertRaises(ValueError):
            slot._publish(self.root, candidate, 'a' * 64, self.root / 'backup/previous', validator=invalid)
        self.assertEqual((destination / 'original.txt').read_bytes(), b'original candidate')

    def test_post_publication_failure_restores_prior_candidate(self):
        destination = self.root / 'dist/native-lab'
        destination.mkdir(parents=True)
        (destination / 'original.txt').write_bytes(b'original candidate')
        candidate = self.root / 'candidate'
        candidate_files = candidate / 'dist/native-lab'
        candidate_files.mkdir(parents=True)
        (candidate_files / 'new.txt').write_bytes(b'new candidate')
        calls = []
        def validator(digest, *, root):
            calls.append(root)
            if len(calls) == 2:
                raise ValueError('post-publication validation failed')
            return {'exact': 'candidate'}, [b'x'] * 8
        backup = self.root / 'backup/previous'
        with self.assertRaises(ValueError):
            slot._publish(self.root, candidate, 'a' * 64, backup, validator=validator)
        self.assertEqual((destination / 'original.txt').read_bytes(), b'original candidate')
        self.assertEqual((backup.parent / 'failed-candidate/new.txt').read_bytes(), b'new candidate')


if __name__ == '__main__':
    unittest.main()
