"""Real FTP fault tests for disabled-only startup staging; no Vita contact."""
import json
from pathlib import Path
import tempfile
import unittest

from resident.autostart.stage import ACTIVE, BASE, FILES, PAIRING, proposal, sha, stage, validated
from tests.ftp_fixture import Fixture


class Staging(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ftp = Fixture()
        self.addCleanup(self.ftp.close)
        self.ftp.directories.update({'/ur0:', '/ur0:/tai', '/ux0:/data/vita-resident'})
        self.before = b'# retained\r\n*KERNEL\r\nur0:tai/storagemgr.skprx\r\n*main\r\nux0:data/vita-resident/setup-old/vita_resident.suprx\r\n*ALL\r\n# retained footer\r\n'
        self.ftp.files.update({ACTIVE: self.before, PAIRING: b'PRIVATE-TEST-PAIRING\n'})
        private = self.root / '.devloop-private'
        private.mkdir()
        (private / 'ftp.json').write_text(json.dumps({'host': '127.0.0.1', 'port': self.ftp.port}))
        dist = self.root / 'dist/autostart'
        dist.mkdir(parents=True)
        artifacts = {}
        for name in sorted(FILES):
            data = b'SCE\0' + name.encode() * 80
            (dist / name).write_bytes(data)
            artifacts[name] = {'bytes': len(data), 'sha256': sha(data)}
        source = self.root / 'source.c'
        source.write_text('unchanged source')
        self.report = {'version': '0.1.0', 'mode': 'experimental one-shot only',
                       'setup': 'setup-' + 'a' * 32,
                       'module_root': 'ux0:data/vita-autostart/setup-' + 'a' * 32 + '/',
                       'control_build_id': 'b' * 64, 'artifacts': artifacts,
                       'source_hashes': {'source.c': sha(source.read_bytes())},
                       'control_source_hashes': {'source.c': sha(source.read_bytes())}}
        self.write_report()

    def write_report(self):
        raw = json.dumps(self.report).encode()
        (self.root / 'dist/autostart/build-report.json').write_bytes(raw)
        self.report_sha = sha(raw)

    def run_stage(self):
        return stage(self.root, self.report_sha, sha(self.before))

    def assert_protected(self):
        self.assertEqual(self.ftp.files[ACTIVE], self.before)
        self.assertEqual(self.ftp.files[PAIRING], b'PRIVATE-TEST-PAIRING\n')
        self.assertNotIn(BASE + '/enable.once', self.ftp.files)
        mutations = [arg for cmd, arg in self.ftp.commands if cmd in ('STOR', 'RNTO')]
        self.assertTrue(all(arg.startswith(BASE + '/setup-' + 'a' * 32 + '/') for arg in mutations))
        self.assertFalse(any(cmd in ('DELE', 'RMD') for cmd, _ in self.ftp.commands))

    def test_success_disabled_with_two_readbacks(self):
        result = self.run_stage()
        self.assertIn('disabled', result['state'])
        self.assertTrue(result['active_config_unchanged'])
        self.assertTrue(result['pairing_unchanged'])
        self.assertEqual(len(result['files']), 7)
        self.assertTrue(all(item['read_back_checks'] == 2 for item in result['files'].values()))
        after = self.ftp.files[BASE + '/setup-' + 'a' * 32 + '/config.txt']
        added = (self.report['module_root'] + 'vita_autostart.suprx\r\n').encode()
        self.assertEqual(after.replace(added, b''), self.before)
        self.assert_protected()

    def test_existing_parent_is_allowed_but_fresh_setup_required(self):
        self.ftp.directories.add(BASE)
        self.ftp.directories.add(BASE + '/setup-' + 'a' * 32)
        with self.assertRaises(RuntimeError):
            self.run_stage()
        self.assertFalse(any(cmd == 'STOR' for cmd, _ in self.ftp.commands))
        self.assert_protected()

    def test_wrong_active_pin_no_mutations(self):
        with self.assertRaises(RuntimeError):
            stage(self.root, self.report_sha, '0' * 64)
        self.assertFalse(any(cmd in ('STOR', 'MKD') for cmd, _ in self.ftp.commands))

    def test_prior_activation_markers_block(self):
        for name in ('enable.once', 'enable.consumed', 'attempt.inflight'):
            with self.subTest(name=name):
                self.ftp.files[BASE + '/' + name] = b'old'
                with self.assertRaises(RuntimeError):
                    self.run_stage()
                del self.ftp.files[BASE + '/' + name]
        self.assertFalse(any(cmd in ('STOR', 'MKD') for cmd, _ in self.ftp.commands))

    def test_source_drift_before_contact(self):
        (self.root / 'source.c').write_text('changed')
        with self.assertRaises(ValueError):
            self.run_stage()
        self.assertEqual(self.ftp.commands, [])

    def test_artifact_drift_before_contact(self):
        (self.root / 'dist/autostart/vita_autostart.suprx').write_bytes(b'SCE\0changed')
        with self.assertRaises(ValueError):
            self.run_stage()
        self.assertEqual(self.ftp.commands, [])

    def test_report_drift_before_contact(self):
        with self.assertRaises(ValueError):
            stage(self.root, '0' * 64, sha(self.before))
        self.assertEqual(self.ftp.commands, [])

    def test_source_escape_before_contact(self):
        self.report['source_hashes'] = {'../outside': '0' * 64}
        self.write_report()
        with self.assertRaises(ValueError):
            self.run_stage()
        self.assertEqual(self.ftp.commands, [])

    def test_transport_fault_retains_receipt_without_replay(self):
        # One fixture per subcase preserves independent, fresh setup roots.
        for fault in ('truncate_upload', 'drop_upload', 'corrupt_part',
                      'unsupported_rename', 'drop_rename', 'oversize_read'):
            with self.subTest(fault=fault):
                self.ftp.fault = fault
                with self.assertRaises(RuntimeError):
                    self.run_stage()
                self.assert_protected()
                receipts = list((self.root / 'evidence/autonomy').glob('stage-*/deployment.json'))
                # Oversized preflight reads fail before creating a receipt.
                if fault != 'oversize_read':
                    saved = json.loads(receipts[-1].read_text())
                    self.assertIn('uncertain or incomplete', saved['state'])
                mutations_before = sum(cmd == 'STOR' for cmd, _ in self.ftp.commands)
                self.assertLessEqual(mutations_before, 1)
                # Rotate only local fixture/evidence between subcases.
                self.ftp.close()
                self.ftp = Fixture()
                self.addCleanup(self.ftp.close)
                self.ftp.directories.update({'/ur0:', '/ur0:/tai', '/ux0:/data/vita-resident'})
                self.ftp.files.update({ACTIVE: self.before, PAIRING: b'PRIVATE-TEST-PAIRING\n'})
                (self.root / '.devloop-private/ftp.json').write_text(json.dumps({'host': '127.0.0.1', 'port': self.ftp.port}))
                import shutil
                shutil.rmtree(self.root / 'evidence', ignore_errors=True)

    def test_config_proposal_rejects_duplicate_and_old_control(self):
        plugin = self.report['module_root'] + 'vita_autostart.suprx'
        for data in (self.before + b'ux0:data/vita-control/vita_control.suprx\n',
                     self.before + b'*main\nux0:data/vita-resident/another/vita_resident.suprx\n', self.before.replace(b'*main', b'*NPXS10015'),
                     self.before + plugin.encode() + b'\n'):
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    proposal(data, plugin)

    def test_repeated_main_sections_preserve_all_existing_bytes(self):
        before = self.before + b'*main\r\nur0:tai/shellbat.suprx\r\n'
        plugin = self.report['module_root'] + 'vita_autostart.suprx'
        after = proposal(before, plugin)
        self.assertEqual(after.replace((plugin + '\r\n').encode(), b'', 1), before)
        self.assertEqual(after.count(b'vita_autostart.suprx'), 1)


if __name__ == '__main__':
    unittest.main()
