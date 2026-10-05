"""Real local HTTP disconnects with a simulated Vita; no hardware acceptance."""
import contextlib
import io
import json
import os
import struct
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import workbench.watch_disconnect as w

BUILD = 'a' * 64

class Disconnects(unittest.TestCase):
    def run_case(self, kind, lost_renewal=False):
        clock = SimpleNamespace(now=0.)
        posts = []
        ended = False
        state = dict(paused=True, mode='tilt+stick', parameters={}, ball={}, score=0, added_obstacles=0)
        offline_at = 10 if lost_renewal else 8
        online_at = 17 if lost_renewal else (53 if kind == 'sleep' else 15)
        def identity():
            return dict(app='Vita Control', version='0.3.1', abi=2, build_id=BUILD,
                        uptime_ms=100000 + int(clock.now * 1000), sample_ms=int(clock.now * 1000), lease_remaining_ms=0)
        def power():
            working = bool(posts and not ended and clock.now < online_at)
            return dict(app='Vita Work Power', abi=2, lease_remaining_ms=20000 if working else 0,
                        dimmed=working and clock.now >= 5, brightness=6877 if working and clock.now >= 5 else 34389,
                        motion_fresh=working, idle_elapsed_ms=int(clock.now * 1000) if kind == 'wifi' or clock.now < online_at else 100)
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                if offline_at <= clock.now < online_at and (not lost_renewal or len(posts) >= 2):
                    self.close_connection = True
                    return
                if self.path not in ('/status', '/power/status'): raise AssertionError('Unexpected read route')
                self.send(identity() if self.path == '/status' else power())
            def do_POST(self):
                nonlocal ended
                if self.path != '/power/lease': raise AssertionError('Unexpected mutation')
                raw = self.rfile.read(int(self.headers['Content-Length']))
                ttl = struct.unpack('<5I', raw)[2]
                posts.append(ttl)
                if ttl == 0: ended = True
                if ttl and lost_renewal and clock.now >= 10:
                    self.close_connection = True
                    return
                self.send(power())
            def send(self, value):
                raw = json.dumps(value).encode()
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        def advance(seconds): clock.now += seconds
        fake = SimpleNamespace(control=SimpleNamespace(configuration=lambda: dict(host='127.0.0.1', port=server.server_port - 1, token='d' * 32)),
                               control_status=identity, status=lambda: dict(state))
        try:
            with tempfile.TemporaryDirectory() as folder:
                root = Path(folder); dist = root / 'dist/control'; dist.mkdir(parents=True)
                (dist / 'build-report.json').write_text(json.dumps({'build_id': BUILD}))
                with patch.object(w, 'ROOT', root), patch.object(w, 'Device', lambda: fake), \
                     patch.object(w, 'exclusive', contextlib.nullcontext), \
                     patch.object(w, 'time', SimpleNamespace(monotonic=lambda: clock.now, sleep=advance)), \
                     patch.dict(os.environ, {'VITA_CONTROL_PORT': str(server.server_port)}), \
                     contextlib.redirect_stdout(io.StringIO()):
                    w.watch(kind, 90)
                report = json.loads(next((root / 'evidence/workbench').glob('*/report.json')).read_text())
        finally:
            server.shutdown(); server.server_close()
        return report, posts

    def test_wifi_recovery_before_expiry_without_input(self):
        report, posts = self.run_case('wifi')
        self.assertTrue(all(report['checks'].values()))
        self.assertTrue(report['result'].startswith('passed device'))
        self.assertEqual(posts, [30000, 0])
        self.assertGreater(report['seconds_until_last_lease_deadline'], 1)

    def test_sleep_recovery_after_expiry_without_forced_wake(self):
        report, posts = self.run_case('sleep')
        self.assertTrue(all(report['checks'].values()))
        self.assertFalse(report['forced_wake'])
        self.assertEqual(posts, [30000, 0])
        self.assertLess(report['seconds_until_last_lease_deadline'], 0)

    def test_disconnect_during_heartbeat_is_retained_not_replayed(self):
        report, posts = self.run_case('wifi', lost_renewal=True)
        self.assertTrue(all(report['checks'].values()))
        self.assertEqual(posts, [30000, 30000, 0])
        uncertain = [e for e in report['events'] if e['kind'] == 'mutation_unconfirmed']
        self.assertEqual(len(uncertain), 1)
        self.assertFalse(uncertain[0]['replayed'])

if __name__ == '__main__': unittest.main(verbosity=2)
