"""Exercise update guards and preserve activation/pairing boundaries."""
import hashlib
import json
import unittest
from test_staging import StageTests, BEFORE, EXPECTED
from stage import stage
from stage_update import stage_update, replacement


class UpdateTests(StageTests):
    # Reuse setup, but do not repeat the inherited first-install test suite.
    def test_replacement_preserves_pairing_and_every_other_config_byte(self):
        first = stage(self.root, EXPECTED)
        proposed = self.ftp.files['/ux0:/data/vita-resident/' + first['attempt'] + '/config.txt']
        self.ftp.files['/ur0:/tai/config.txt'] = proposed
        pairing = self.ftp.files['/ux0:/data/vita-resident/bridge.cfg']
        result = stage_update(self.root, hashlib.sha256(proposed).hexdigest(), first['plugin_path'])
        after = self.ftp.files['/ux0:/data/vita-resident/' + result['attempt'] + '/config.txt']
        self.assertEqual(after.replace(result['plugin_path'].encode(), first['plugin_path'].encode(), 1), proposed)
        self.assertEqual(self.ftp.files['/ur0:/tai/config.txt'], proposed)
        self.assertEqual(self.ftp.files['/ux0:/data/vita-resident/bridge.cfg'], pairing)
        self.assertTrue(result['active_config_unchanged'])
        self.assertTrue(all(v['read_back_checks'] == 2 for v in result['files'].values()))

    def test_update_pairing_mismatch_refuses_before_writes(self):
        first = stage(self.root, EXPECTED)
        self.ftp.files['/ux0:/data/vita-resident/bridge.cfg'] = b'bad\n'
        count = len(self.ftp.commands)
        with self.assertRaises(RuntimeError):
            stage_update(self.root, EXPECTED, first['plugin_path'])
        self.assertFalse(any(c in ['STOR', 'MKD', 'RNTO'] for c, p in self.ftp.commands[count:]))

    def test_update_missing_or_duplicated_line_refused(self):
        old = 'ux0:data/vita-resident/setup-' + '1'*12 + '-' + '2'*32 + '/vita_resident.suprx'
        new = old.replace('1'*12, '3'*12)
        for config in [BEFORE, BEFORE + (old+'\n'+old+'\n').encode(), ('*KERNEL\n'+old+'\n').encode()]:
            with self.assertRaises(ValueError):
                replacement(config, old, new)


if __name__ == '__main__':
    suite = unittest.TestSuite(UpdateTests(name) for name in UpdateTests.__dict__ if name.startswith('test_update') or name.startswith('test_replacement'))
    unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() or exit(1)
