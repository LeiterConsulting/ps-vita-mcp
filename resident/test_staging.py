"""Prove the activation boundary and failure behavior using a simulated FTP device."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from ftp_fixture import Fixture
from stage import proposal, stage, verify_existing

BEFORE = b'*main\r\nux0:data/VitaDB/vdb_daemon.suprx\r\n*KERNEL\r\nur0:tai/itls.skprx\r\n*main\r\nur0:tai/henkaku.suprx\r\n'
EXPECTED = hashlib.sha256(BEFORE).hexdigest()


class StageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / '.devloop-private').mkdir()
        (self.root / 'dist/resident').mkdir(parents=True)
        # Synthetic plugin/build manifest: this fixture tests transport/config behavior only.
        payload = b'SCE\0' + bytes(range(256)) * 32
        (self.root / 'dist/resident/vita_resident.suprx').write_bytes(payload)
        report = {'version': '0.1.2', 'plugin': {'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest(), 'module_attributes': 0}, 'source_hashes': {}, 'accepted_artifacts_preserved': {}}
        (self.root / 'dist/resident/build-report.json').write_text(json.dumps(report), encoding='utf-8')
        self.ftp = Fixture()
        self.ftp.directories.update(['/ur0:', '/ur0:/tai'])
        self.ftp.files['/ur0:/tai/config.txt'] = BEFORE
        (self.root / '.devloop-private/ftp.json').write_text(json.dumps({'host': '127.0.0.1', 'port': self.ftp.port}), encoding='utf-8')

    def tearDown(self):
        self.ftp.close()
        self.temp.cleanup()

    def assert_untouched(self):
        self.assertEqual(self.ftp.files['/ur0:/tai/config.txt'], BEFORE)
        self.assertFalse(any(command in ['DELE', 'RMD'] for command, _ in self.ftp.commands))
        self.assertFalse(any(command == 'STOR' and not path.startswith('/ux0:/data/vita-resident/') for command, path in self.ftp.commands))

    def test_stage_exact_one_line_and_pairing_without_activation(self):
        result = stage(self.root, EXPECTED)
        self.assert_untouched()
        self.assertTrue(result['active_config_unchanged'])
        proposed = self.ftp.files['/ux0:/data/vita-resident/' + result['attempt'] + '/config.txt']
        line = result['plugin_path'].encode() + b'\r\n'
        self.assertEqual(proposed.count(line), 1)
        self.assertEqual(proposed.replace(line, b''), BEFORE)
        self.assertTrue(proposed.startswith(b'*main\r\n' + line))
        token = json.loads((self.root / '.devloop-private/resident.json').read_text())['token']
        self.assertEqual(self.ftp.files['/ux0:/data/vita-resident/bridge.cfg'], (token + '\n').encode())
        for info in result['files'].values():
            self.assertEqual(info['read_back_checks'], 2)
        checked = verify_existing(self.root, Path(result['local_evidence']))
        self.assertEqual(checked['configuration'], 'unchanged; activation pending')
        # Read-only recovery also recognizes a manually copied proposal; never claims runtime.
        self.ftp.files['/ur0:/tai/config.txt'] = proposed
        checked = verify_existing(self.root, Path(result['local_evidence']))
        self.assertEqual(checked['configuration'], 'proposal present; runtime unverified')

    def test_config_change_and_precedence_refuse_before_device_writes(self):
        for mode in ['changed', 'ux0']:
            with self.subTest(mode=mode):
                if mode == 'changed':
                    expected = '0' * 64
                else:
                    expected = EXPECTED
                    self.ftp.files['/ux0:/tai/config.txt'] = b'*main\n'
                with self.assertRaises(RuntimeError):
                    stage(self.root, expected)
                self.assertFalse(any(command in ['STOR', 'MKD', 'RNTO'] for command, _ in self.ftp.commands))
                self.assertFalse((self.root / '.devloop-private/resident.json').exists())
                self.assert_untouched()

    def test_existing_root_refused_without_overwrite(self):
        self.ftp.directories.add('/ux0:/data/vita-resident')
        original = b'original-private-pairing'
        self.ftp.files['/ux0:/data/vita-resident/bridge.cfg'] = original
        with self.assertRaises(RuntimeError):
            stage(self.root, EXPECTED)
        self.assertEqual(self.ftp.files['/ux0:/data/vita-resident/bridge.cfg'], original)
        self.assertFalse(any(command == 'STOR' for command, _ in self.ftp.commands))
        self.assert_untouched()

    def test_corrupt_part_stops_without_retry_or_activation(self):
        self.ftp.fault = 'corrupt_part'
        with self.assertRaises(RuntimeError):
            stage(self.root, EXPECTED)
        self.assertEqual(sum(command == 'STOR' for command, _ in self.ftp.commands), 1)
        self.assertFalse(any(command == 'RNTO' for command, _ in self.ftp.commands))
        self.assert_untouched()
        self.assertTrue((self.root / '.devloop-private/resident.json').exists())
        with self.assertRaises(ValueError):
            stage(self.root, EXPECTED)
        self.assertEqual(sum(command == 'STOR' for command, _ in self.ftp.commands), 1)

    def test_lost_rename_reply_retains_recoverable_token_and_plan(self):
        self.ftp.fault = 'drop_rename'
        with self.assertRaises(RuntimeError):
            stage(self.root, EXPECTED)
        self.assertEqual(sum(command == 'STOR' for command, _ in self.ftp.commands), 1)
        plan = json.loads(next((self.root / 'evidence/resident').glob('*/deployment.json')).read_text())
        self.assertIn('uncertain', plan['state'])
        token = json.loads((self.root / '.devloop-private/resident.json').read_text())['token']
        self.assertEqual(self.ftp.files['/ux0:/data/vita-resident/bridge.cfg'], (token + '\n').encode())
        self.assert_untouched()

    def test_bad_proposal_does_not_strip_or_move_plugins(self):
        path = 'ux0:data/vita-resident/setup-' + '1' * 12 + '-' + '2' * 32 + '/vita_resident.suprx'
        self.assertEqual(proposal(BEFORE, path).replace(path.encode() + b'\r\n', b''), BEFORE)
        for before, plugin in [(b'*KERNEL\nexisting\n', path), (BEFORE + b'vita_resident.suprx\n', path), (BEFORE, 'ur0:tai/other.suprx'), (b'*main', path)]:
            with self.assertRaises(ValueError):
                proposal(before, plugin)


if __name__ == '__main__':
    unittest.main(verbosity=2)
