"""Project isolation, current-byte session pins and installed launcher contracts."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.vita_app import create, install_skill, load, project_path, read_json, session_args


class Projects(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / 'app_tools').mkdir()
        (self.root / 'app_tools/lua_starter.lua').write_text(
            "return {update=function() vita.metric('ready',1) end,draw=function() end}", encoding='utf-8')

    def tearDown(self):
        self.temporary.cleanup()

    def prepare(self):
        return {'ready_for_script_reload': True, 'expected_revision': 9,
                'runtime_identity': {'app': 'Vita DevLoop', 'protocol': 1, 'version': '01.04',
                                     'title_id': 'CHRS00003', 'build_id': 'a' * 64,
                                     'pid': 123, 'run': 'b' * 32}}

    def test_new_is_private_and_does_not_replace_project(self):
        created = create('paddle', 'lua', root=self.root)
        path, value = load('paddle', root=self.root)
        self.assertEqual(created['device_mutations'], 0)
        self.assertEqual(path, self.root / '.devloop-private/vita-apps/paddle')
        before = (path / 'main.lua').read_bytes()
        with self.assertRaises(FileExistsError):
            create('paddle', 'lua', root=self.root)
        self.assertEqual((path / 'main.lua').read_bytes(), before)
        self.assertNotIn('expected_run', value)

    def test_paths_are_identifiers_and_reject_traversal(self):
        for slug in ('../escape', 'C:\\escape', 'nested/name', '.', '', 'UPPER', 'a' * 33):
            with self.subTest(slug=slug), self.assertRaises(ValueError):
                project_path(slug, root=self.root)

    def test_invalid_native_display_name_leaves_no_partial_project(self):
        with self.assertRaises(ValueError):
            create('native-paddle', 'native-slot', 'Name "with quotes"', root=self.root)
        self.assertFalse(project_path('native-paddle', root=self.root).exists())

    def test_linked_private_parent_cannot_redirect_projects_into_public_tree(self):
        public = self.root / 'public-projects'; public.mkdir()
        private = self.root / '.devloop-private'
        try:
            private.symlink_to(public, target_is_directory=True)
        except OSError:
            self.skipTest('Host does not permit creation of a test directory symlink')
        with self.assertRaises(ValueError): create('paddle', 'lua', root=self.root)
        self.assertEqual(list(public.iterdir()), [])

    def test_manifest_rejects_commands_and_invalid_checks(self):
        create('paddle', 'lua', root=self.root)
        path, value = load('paddle', root=self.root)
        for change in ({'command': 'delete'}, {'checks': [{'metric': 'ready', 'min': float('inf')}]},
                       {'checks': [{'metric': 'ready', 'min': 10, 'max': 1}]}, {'host_frames': True}):
            wrong = {**value, **change}
            # Standard JSON permits Infinity; our reader must refuse it.
            (path / 'vita-project.json').write_text(json.dumps(wrong), encoding='utf-8')
            with self.subTest(change=change), self.assertRaises(ValueError):
                load('paddle', root=self.root)

    def test_session_uses_current_bytes_and_fresh_preparation_pins(self):
        create('paddle', 'lua', root=self.root)
        first = session_args('paddle', self.prepare(), root=self.root)
        path, _ = load('paddle', root=self.root)
        (path / 'main.lua').write_text("return {update=function() end,draw=function() end}", encoding='utf-8')
        second = session_args('paddle', self.prepare(), root=self.root)
        self.assertNotEqual(first['candidates'][0]['source_sha256'], second['candidates'][0]['source_sha256'])
        self.assertEqual(second['expected_pid'], 123)
        self.assertEqual(second['expected_run'], 'b' * 32)
        self.assertEqual(second['expected_revision'], 9)
        self.assertFalse(second['retain_best'])
        for prep in (None, {}, {**self.prepare(), 'ready_for_script_reload': False},
                     {**self.prepare(), 'expected_revision': True}):
            with self.subTest(prep=prep), self.assertRaises(ValueError):
                session_args('paddle', prep, root=self.root)

    def test_json_duplicate_identity_is_rejected(self):
        path = self.root / 'duplicate.json'
        path.write_text('{"route":"lua","route":"native-slot"}', encoding='utf-8')
        with self.assertRaises(ValueError): read_json(path)

    def test_installed_launcher_works_outside_checkout_and_never_overwrites(self):
        target = self.root / 'local-skills/make-vita-app'
        result = install_skill(target, root=ROOT)
        self.assertEqual(result['name'], 'make-vita-app')
        self.assertEqual(json.loads((target / 'repository.json').read_text())['repository'], str(ROOT))
        env = {**os.environ}; env.pop('VITA_APP_REPO', None)
        launched = subprocess.run([sys.executable, str(target / 'scripts/vita_app.py'), '--help'],
                                  cwd=self.root, env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(launched.returncode, 0, launched.stderr)
        self.assertIn('session-args', launched.stdout)
        with self.assertRaises(FileExistsError): install_skill(target, root=ROOT)


if __name__ == '__main__': unittest.main()
