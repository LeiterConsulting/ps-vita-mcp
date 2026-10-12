"""Explicit offline compiler proofs for undeclared host/native headers.

Run: python -m app_slot.test_dependency_integration
Requires the pinned Docker image already installed. Retains generated fixtures
and failure logs privately. No Vita requests and no candidate publication.
"""
import hashlib
from pathlib import Path
import unittest
import uuid
from unittest.mock import patch

from scripts import vita_native_slot as slot


class CompilerDependencyIntegration(unittest.TestCase):
    def fixture(self, which):
        relative = '.devloop-private/native-slot-dependency-proofs/' + uuid.uuid4().hex
        parent = slot.ROOT / relative
        info = slot.scaffold(relative + '/native-slot', name='dependency-proof',
                             display_name='Dependency Proof')
        (parent / 'undeclared.h').write_text('#define UNDECLARED_APPLICATION_RESULT 1\n', encoding='utf-8')
        path = parent / 'native-slot' / which
        raw = '#include "../undeclared.h"\n' + path.read_text(encoding='utf-8')
        if which == 'app.c':
            raw = raw.replace('return 1;}', 'return UNDECLARED_APPLICATION_RESULT;}', 1)
        path.write_text(raw, encoding='utf-8')
        return info['project_directory']

    def dist_pins(self):
        path = slot.ROOT / 'dist/native-lab'
        return {item.name: hashlib.sha256(item.read_bytes()).hexdigest()
                for item in path.iterdir() if item.is_file()} if path.is_dir() else {}

    def test_host_undeclared_header_rejected_before_test_execution(self):
        project = self.fixture('app_sim.c')
        folder = slot._evidence(slot.ROOT)
        with self.assertRaisesRegex(RuntimeError, 'command failed'):
            slot.check(project, evidence=folder)
        self.assertFalse((folder / 'application-host-tests.log').exists())
        self.assertIn('undeclared.h', (folder / 'application-host-app_sim-build.log').read_text())
        self.assertIn('No such file', (folder / 'application-host-app_sim-build.log').read_text())
        self.assertFalse((folder / 'host-compiler-root' / project).parent.joinpath('undeclared.h').exists())

    def test_native_only_undeclared_header_rejected_without_dist_change(self):
        project = self.fixture('app.c')
        prior = self.dist_pins()
        folder = slot._evidence(slot.ROOT)
        with patch.object(slot, '_evidence', return_value=folder):
            with self.assertRaisesRegex(RuntimeError, 'command failed'):
                slot.build(project, version='01.02')
        self.assertEqual(self.dist_pins(), prior)
        log = (folder / 'native-build.log').read_text()
        self.assertIn('undeclared.h', log)
        self.assertIn('No such file', log)

    def test_native_inline_incbin_cannot_read_unpinned_original_repository_bytes(self):
        relative = '.devloop-private/native-slot-dependency-proofs/' + uuid.uuid4().hex
        info = slot.scaffold(relative + '/native-slot', name='assembly-proof', display_name='Assembly Proof')
        blob_relative = relative + '/undeclared-assembly.bin'
        blob = slot.ROOT / blob_relative
        blob.write_bytes(b'UNPINNED_REPOSITORY_ASSEMBLER_INPUT_71d792b6')
        source = slot.ROOT / info['project_directory'] / 'app.c'
        assembly = ('\n__asm__(".pushsection .rodata\\n.incbin \\\"/workspace/' + blob_relative
                    + '\\\"\\n.popsection\\n");\n')
        source.write_text(source.read_text() + assembly)
        prior = self.dist_pins()
        folder = slot._evidence(slot.ROOT)
        with patch.object(slot, '_evidence', return_value=folder):
            with self.assertRaisesRegex(RuntimeError, 'command failed'):
                slot.build(info['project_directory'], version='01.02')
        self.assertEqual(self.dist_pins(), prior)
        self.assertFalse((folder / 'native-compiler-root' / blob_relative).exists())
        log = (folder / 'native-build.log').read_text()
        self.assertIn('undeclared-assembly.bin', log)
        self.assertIn('file not found', log.lower())


if __name__ == '__main__':
    unittest.main(verbosity=2)
