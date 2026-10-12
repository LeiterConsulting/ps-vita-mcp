"""The actual PC client reads and exits the actual C lab HTTP worker."""
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from resident.lifecycle_client import LifecycleClient, LifecycleRejected, LifecycleTransport


class ProducerClientContract(unittest.TestCase):
    def test_native_status_and_exit_receipts_match_strict_pc_client(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            token = 'd' * 32
            (folder / 'bridge.cfg').write_text(token + '\n', encoding='ascii')
            endpoint = {'host': '127.0.0.1', 'port': 17866, 'token': token}
            client = LifecycleClient(provider=lambda: endpoint)
            with (folder / 'server.log').open('wb') as output:
                process = subprocess.Popen([str(ROOT / 'build/native-lab-host/http-server'),
                                            directory, '17868'], stdout=output, stderr=output)
                try:
                    deadline = time.monotonic() + 5
                    while True:
                        try:
                            first = client.lab_status('a' * 64, '01.00')
                            break
                        except (LifecycleTransport, LifecycleRejected):
                            if process.poll() is not None or time.monotonic() >= deadline:
                                raise
                            time.sleep(.02)
                    time.sleep(.02)
                    second = client.lab_status('a' * 64, '01.00')
                    self.assertEqual(first['run'], second['run'])
                    self.assertEqual(second['pid'], process.pid)
                    self.assertGreater(second['frame'], first['frame'])
                    self.assertTrue(second['selftest_passed'])
                    self.assertEqual(second['variant'], 1)
                    ack = client.lab_exit(second)
                    self.assertEqual(ack['exit_expected_revision'], second['revision'])
                    self.assertEqual(ack['revision'], second['revision'] + 1)
                    self.assertTrue(ack['exiting'])
                    self.assertFalse(ack['exit_response_complete'])
                    self.assertEqual(process.wait(timeout=5), 0)
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=5)
            text = (folder / 'server.log').read_text()
            self.assertNotIn('AddressSanitizer', text)
            self.assertNotIn('runtime error:', text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
