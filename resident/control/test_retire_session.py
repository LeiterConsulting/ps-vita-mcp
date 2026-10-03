"""Exercise exact-session retirement using a local simulated FTP server."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests'))
from ftp_fixture import Fixture
import retire_session

CONFIG = b'*KERNEL\n# Fixture kernel section\n*main\n# Fixture shell section\n'
CONFIG_SHA = hashlib.sha256(CONFIG).hexdigest()


class RetirementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patch = patch.object(retire_session, 'ROOT', self.root)
        self.patch.start()
        self.ftp = Fixture()
        (self.root / '.devloop-private').mkdir()
        (self.root / 'dist/control').mkdir(parents=True)
        self.build = json.loads((ROOT / 'dist/control/build-report.json').read_text())
        (self.root / 'dist/control/build-report.json').write_text(json.dumps(self.build))
        (self.root / '.devloop-private/ftp.json').write_text(json.dumps({'host': '127.0.0.1', 'port': self.ftp.port}))
        self.ftp.directories.update(['/ur0:', '/ur0:/tai', '/ux0:/app', '/ux0:/app/CHRS00011', '/ux0:/data/vita-control'])
        self.ftp.files['/ur0:/tai/config.txt'] = CONFIG
        with zipfile.ZipFile(ROOT / 'dist/control/control_starter.vpk') as archive:
            for name in ('eboot.bin', 'vita_control_kernel.skprx', 'vita_control.suprx', 'control_bootstrap_probe.suprx', 'sce_sys/param.sfo'):
                self.ftp.files['/ux0:/app/CHRS00011/' + name] = archive.read(name)
        self.guard = struct.pack('<II33s3s', 0x31534356, 1, b'0123456789abcdef0123456789abcdef\0', b'\0' * 3)
        self.guard_sha = hashlib.sha256(self.guard).hexdigest()
        self.ftp.files[retire_session.GUARD] = self.guard

    def tearDown(self):
        self.patch.stop()
        self.ftp.close()
        self.temp.cleanup()

    def run_retirement(self, guard=None, config=None, confirmed=True):
        return retire_session.retire(guard or self.guard_sha, self.build['starter_package']['sha256'], config or CONFIG_SHA, confirmed)

    def assert_no_writes(self):
        self.assertFalse(any(c in ('STOR', 'MKD', 'RNTO', 'DELE', 'RMD') for c, _ in self.ftp.commands))

    def test_requires_explicit_reboot_confirmation(self):
        with self.assertRaises(ValueError):
            self.run_retirement(confirmed=False)
        self.assertFalse(self.ftp.commands)

    def test_inspection_has_no_writes_or_reboot_inference(self):
        result = retire_session.inspect_session()
        self.assertEqual(result['active_config_sha256'], CONFIG_SHA)
        self.assertEqual(result['session_guard']['sha256'], self.guard_sha)
        self.assertEqual(result['remote_writes'], 'none')
        self.assert_no_writes()

    def test_retains_exact_marker_without_config_or_module_actions(self):
        result = self.run_retirement()
        self.assertNotIn(retire_session.GUARD, self.ftp.files)
        self.assertEqual(self.ftp.files[result['retained_path']], self.guard)
        self.assertEqual(self.ftp.files['/ur0:/tai/config.txt'], CONFIG)
        self.assertTrue(result['active_config_unchanged'])
        self.assertFalse(any(c in ('STOR', 'MKD', 'DELE', 'RMD') for c, _ in self.ftp.commands))

    def test_changed_config_refuses_before_mutation(self):
        with self.assertRaises(RuntimeError):
            self.run_retirement(config='0' * 64)
        self.assert_no_writes()

    def test_unknown_guard_refuses_before_mutation(self):
        with self.assertRaises(RuntimeError):
            self.run_retirement(guard='0' * 64)
        self.assert_no_writes()

    def test_malformed_guard_refuses_before_mutation(self):
        self.ftp.files[retire_session.GUARD] = b'unknown'
        with self.assertRaises(RuntimeError):
            self.run_retirement()
        self.assert_no_writes()

    def test_overriding_config_refuses_before_mutation(self):
        self.ftp.files['/ux0:/tai/config.txt'] = CONFIG
        with self.assertRaises(RuntimeError):
            self.run_retirement()
        self.assert_no_writes()

    def test_changed_installed_proxy_refuses_before_mutation(self):
        self.ftp.files['/ux0:/app/CHRS00011/vita_control.suprx'] = b'other build'
        with self.assertRaises(RuntimeError):
            self.run_retirement()
        self.assert_no_writes()

    def test_lost_rename_is_recorded_and_not_replayed(self):
        self.ftp.fault = 'drop_rename'
        with self.assertRaises(RuntimeError):
            self.run_retirement()
        self.assertEqual(sum(c == 'RNTO' for c, _ in self.ftp.commands), 1)
        receipt = json.loads(next((self.root / 'evidence/control').glob('*/receipt.json')).read_text())
        self.assertIn('uncertain', receipt['state'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
