"""Actual C lab worker over POSIX sockets, including response/close uncertainty."""
import http.client
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest

TOKEN = 'd' * 32
ROOT = Path(__file__).resolve().parents[1]


class LabHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        (self.folder / 'bridge.cfg').write_text(TOKEN + '\n')
        with socket.socket() as connection:
            connection.bind(('127.0.0.1', 0))
            self.port = connection.getsockname()[1]
        self.log = (self.folder / 'server.log').open('wb')
        self.process = subprocess.Popen([str(ROOT / 'build/native-lab-host/http-server'),
                                         str(self.folder), str(self.port)], stdout=self.log, stderr=self.log)
        self.state = self.await_status()

    def tearDown(self):
        if self.process.poll() is None:
            self.process.terminate()
        self.assertEqual(self.process.wait(timeout=10), 0)
        self.log.close()
        log = (self.folder / 'server.log').read_text()
        self.assertNotIn('AddressSanitizer', log)
        self.assertNotIn('runtime error:', log)
        self.temp.cleanup()

    def call(self, path='/status', body=None, token=TOKEN, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=4)
        raw = None if body is None else json.dumps(body).encode() if isinstance(body, dict) else body
        try:
            connection.request('GET' if raw is None else 'POST', path, raw,
                               {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json', **(headers or {})})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def await_status(self, revision=None, exiting=None):
        for _ in range(200):
            try:
                code, state = self.call()
                if (code == 200 and (revision is None or state['revision'] == revision)
                        and (exiting is None or state['exiting'] is exiting)):
                    return state
            except (OSError, http.client.HTTPException):
                pass
            if self.process.poll() is not None:
                self.log.flush()
                self.fail((self.folder / 'server.log').read_text())
            time.sleep(.01)
        self.fail('Native lab host status deadline')

    @staticmethod
    def pins(state):
        return {'expected_native_build_id': state['native_build_id'], 'expected_pid': state['pid'],
                'expected_run': state['run'], 'expected_revision': state['revision']}

    def test_status_identity_crc_and_advancing_frames(self):
        self.assertEqual(self.state['app'], 'Vita Native Lifecycle Lab')
        self.assertEqual(self.state['title_id'], 'VMCP00001')
        self.assertEqual(self.state['checksum'], 0xa2912082)
        self.assertTrue(self.state['selftest_passed'])
        self.assertTrue(self.state['paused'])
        self.assertFalse(self.state['exiting'])
        time.sleep(.03)
        later = self.await_status()
        self.assertGreater(later['frame'], self.state['frame'])
        self.assertEqual(later['pid'], self.process.pid)
        self.assertEqual(later['run'], self.state['run'])
        self.assertEqual(len(later['run']), 32)

    def test_authentication_json_and_all_four_pins(self):
        self.assertEqual(self.call(token='e' * 32)[0], 401)
        pins = self.pins(self.state)
        for field, value in [('expected_native_build_id', 'b' * 64), ('expected_pid', self.state['pid'] + 1),
                             ('expected_run', 'b' * 32), ('expected_revision', 7)]:
            self.assertEqual(self.call('/exit', {**pins, field: value})[0], 412)
        for body in [b'{}', b'[]', json.dumps({**pins, 'unknown': True}).encode(),
                     json.dumps({**pins, 'expected_pid': True}).encode(),
                     json.dumps({**pins, 'expected_revision': 1.0}).encode(),
                     (json.dumps(pins)[:-1] + ',"expected_pid":1}').encode(),
                     (json.dumps(pins) + ' trailing').encode()]:
            self.assertEqual(self.call('/exit', body)[0], 400)
        self.assertEqual(self.call('/exit', pins, headers={'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.await_status()['revision'], 1)
        self.assertIsNone(self.process.poll())

    def test_exit_ack_socket_close_before_main_cleanup(self):
        code, ack = self.call('/exit', self.pins(self.state))
        self.assertEqual(code, 200)
        self.assertEqual(ack['exit_response'], 'acknowledged')
        self.assertEqual(ack['exit_expected_revision'], 1)
        self.assertEqual(ack['revision'], 2)
        self.assertTrue(ack['exiting'])
        self.assertFalse(ack['exit_response_complete'])
        self.assertEqual(self.process.wait(timeout=5), 0)
        events = (self.folder / 'events.log').read_text().splitlines()
        self.assertEqual(events[-3:], ['socket-close', 'exit-main', 'listener-close'])

    def test_short_writes_complete_and_exit_normally(self):
        (self.folder / 'short-send').touch()
        self.assertEqual(self.call()[0], 200)
        self.assertEqual(self.call('/exit', self.pins(self.state))[0], 200)
        self.assertEqual(self.process.wait(timeout=5), 0)

    def test_failed_response_keeps_runtime_and_consumes_old_revision(self):
        (self.folder / 'fault-send').touch()
        with self.assertRaises((OSError, http.client.HTTPException)):
            self.call('/exit', self.pins(self.state))
        (self.folder / 'fault-send').unlink()
        state = self.await_status(2, exiting=False)
        self.assertFalse(state['exiting'])
        self.assertFalse(state['exit_response_complete'])
        self.assertEqual(self.call('/exit', self.pins(self.state))[0], 412)
        self.assertIsNone(self.process.poll())
        self.assertEqual(self.call('/exit', self.pins(state))[0], 200)
        self.assertEqual(self.process.wait(timeout=5), 0)

    def test_failed_socket_close_keeps_runtime_after_ack(self):
        (self.folder / 'fault-close').touch()
        code, ack = self.call('/exit', self.pins(self.state))
        self.assertEqual(code, 200)
        self.assertTrue(ack['exiting'])
        (self.folder / 'fault-close').unlink()
        state = self.await_status(2, exiting=False)
        self.assertFalse(state['exiting'])
        self.assertFalse(state['exit_response_complete'])
        self.assertEqual(self.call('/exit', self.pins(self.state))[0], 412)
        self.assertEqual(self.call('/exit', self.pins(state))[0], 200)
        self.assertEqual(self.process.wait(timeout=5), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
