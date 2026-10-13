"""Host HTTP deadline/resource regressions; no Vita contact or sleep proof."""
from __future__ import annotations

from contextlib import contextmanager
from http.server import ThreadingHTTPServer
import http.client
import io
from pathlib import Path
import socket
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from resident.http_deadline import DeadlineSocket
from resident.keep_awake_client import KeepAwakeClient, KeepAwakeUnknown, failure_diagnostic, pack
from resident.keep_awake_transport_client import KeepAwakeTransportClient
from resident.test_keep_awake_client import Fixture as LeaseFixture, TOKEN, INSTANCE, LEASE, JOB
from resident.test_keep_awake_transport_client import Fixture as TransportFixture

HTTPConnection = http.client.HTTPConnection


class IgnoreShutdown:
    """Model a platform where shutdown fails to interrupt a blocked receive."""
    def __init__(self, transport):
        self.transport = transport
        self.shutdown_calls = 0

    def __getattr__(self, name):
        return getattr(self.transport, name)

    def shutdown(self, how):
        self.shutdown_calls += 1


@contextmanager
def server_for(fixture):
    server = ThreadingHTTPServer(('127.0.0.1', 0), fixture.handler())
    server.daemon_threads = True
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def slow_connections(connections, delay=0.08):
    class SlowConnection(HTTPConnection):
        def connect(self):
            super().connect()
            self.original_socket = self.sock
            self.ignored_shutdown = IgnoreShutdown(self.sock)
            self.sock = self.ignored_shutdown
            connections.append(self)
            time.sleep(delay)
    return SlowConnection


class DeadlineTests(unittest.TestCase):
    def test_send_and_each_raw_read_receive_the_remaining_budget(self):
        transport = Mock()
        transport.makefile.return_value = io.BytesIO(b'abcdef')
        remaining = Mock(side_effect=[0.9, 0.8, 0.7, 0.6, 0.5, 0.4])
        wrapped = DeadlineSocket(transport, remaining)
        wrapped.sendall(b'request')
        with wrapped.makefile('rb', buffering=0) as stream:
            self.assertEqual(stream.readinto(bytearray(2)), 2)
            self.assertEqual(stream.readinto(bytearray(2)), 2)
        self.assertEqual([call.args[0] for call in transport.settimeout.call_args_list], [0.9, 0.7, 0.5])
        self.assertEqual(remaining.call_count, 6)  # Before and after every operation.
        transport.sendall.assert_called_once_with(b'request')

    def test_expired_send_and_read_do_not_start_blocking_io(self):
        transport = Mock()
        raw = Mock()
        transport.makefile.return_value = raw
        wrapped = DeadlineSocket(transport, Mock(side_effect=TimeoutError('expired')))
        with self.assertRaises(TimeoutError):
            wrapped.sendall(b'request')
        with wrapped.makefile('rb', buffering=0) as stream:
            with self.assertRaises(TimeoutError):
                stream.readinto(bytearray(1))
        transport.sendall.assert_not_called()
        raw.readinto.assert_not_called()
        raw.close.assert_called_once()

    def test_late_raw_read_is_not_returned_to_http_parser(self):
        class LateRaw(io.BytesIO):
            def readinto(self, buffer):
                time.sleep(0.03)
                return super().readinto(buffer)
        transport = Mock()
        raw = LateRaw(b'late')
        transport.makefile.return_value = raw
        deadline = time.monotonic() + 0.015
        def remaining():
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError('expired')
            return left
        with DeadlineSocket(transport, remaining).makefile('rb') as stream:
            with self.assertRaises(TimeoutError):
                stream.read(4)
        self.assertTrue(raw.closed)

    def test_makefile_keeps_original_socket_reference_until_response_closes(self):
        left, right = socket.socketpair()
        stream = None
        try:
            wrapped = DeadlineSocket(left, lambda: 0.2)
            stream = wrapped.makefile('rb')
            self.assertEqual(left._io_refs, 1)
            wrapped.close()  # HTTPConnection's Connection:close detachment.
            self.assertGreaterEqual(left.fileno(), 0)
            right.sendall(b'body\n')
            self.assertEqual(stream.readline(), b'body\n')
            stream.close()
            stream.close()
            self.assertEqual(left._io_refs, 0)
            self.assertEqual(left.fileno(), -1)
        finally:
            if stream is not None:
                stream.close()
            left.close()
            right.close()

    def test_stream_construction_failure_releases_original_makefile(self):
        transport = Mock()
        raw = Mock()
        transport.makefile.return_value = raw
        with patch('resident.http_deadline.io.BufferedReader', side_effect=RuntimeError('fixture')):
            with self.assertRaises(RuntimeError):
                DeadlineSocket(transport, lambda: 0.2).makefile('rb')
        raw.close.assert_called_once()

    def test_connect_and_header_drip_share_budget_even_when_shutdown_is_ignored(self):
        for client_type, fixture in [(KeepAwakeClient, LeaseFixture()),
                                     (KeepAwakeTransportClient, TransportFixture())]:
            fixture.drip = 'headers'
            connections = []
            with self.subTest(client=client_type.__name__), server_for(fixture) as server:
                config = {'host': '127.0.0.1', 'port': 17866, 'token': TOKEN}
                client = client_type(lambda: dict(config), port=server.server_port, timeout=0.16)
                started = time.monotonic()
                with patch('http.client.HTTPConnection', slow_connections(connections)), self.assertRaises(TimeoutError):
                    client.status()
                self.assertLess(time.monotonic() - started, 0.30)
                self.assertEqual(len(fixture.calls), 1)
                self.assertEqual(connections[0].original_socket.fileno(), -1)
                self.assertEqual(connections[0].original_socket._io_refs, 0)

    def test_body_drip_is_bounded_without_watchdog_delivery_and_resources_close(self):
        for client_type, fixture in [(KeepAwakeClient, LeaseFixture()),
                                     (KeepAwakeTransportClient, TransportFixture())]:
            fixture.drip = 'body'
            connections, watchdog = [], Mock()
            with self.subTest(client=client_type.__name__), server_for(fixture) as server:
                config = {'host': '127.0.0.1', 'port': 17866, 'token': TOKEN}
                client = client_type(lambda: dict(config), port=server.server_port, timeout=0.16)
                started = time.monotonic()
                with patch('http.client.HTTPConnection', slow_connections(connections, delay=0.04)), \
                        patch('threading.Timer', return_value=watchdog), self.assertRaises(TimeoutError):
                    client.status()
                self.assertLess(time.monotonic() - started, 0.30)
                watchdog.start.assert_called_once()
                watchdog.cancel.assert_called_once()
                self.assertEqual(connections[0].original_socket.fileno(), -1)
                self.assertEqual(connections[0].original_socket._io_refs, 0)

    def test_accepted_post_timeout_stays_unknown_and_is_never_replayed(self):
        fixture = LeaseFixture()
        fixture.drip = 'body'
        connections, watchdog = [], Mock()
        with server_for(fixture) as server:
            config = {'host': '127.0.0.1', 'port': 17866, 'token': TOKEN}
            client = KeepAwakeClient(lambda: dict(config), port=server.server_port, timeout=0.16)
            started = time.monotonic()
            with patch('http.client.HTTPConnection', slow_connections(connections, delay=0.04)), \
                    patch('threading.Timer', return_value=watchdog), self.assertRaises(KeepAwakeUnknown) as raised:
                client.request('POST', pack(0, 30000, 60000, INSTANCE, LEASE, JOB))
            self.assertLess(time.monotonic() - started, 0.30)
            self.assertEqual(failure_diagnostic(raised.exception),
                             {'method': 'POST', 'phase': 'read_body', 'cause_type': 'TimeoutError'})
            self.assertEqual(len(fixture.packets), 1)
            self.assertEqual(fixture.revision, 1)
            self.assertEqual(connections[0].original_socket.fileno(), -1)
            self.assertEqual(connections[0].original_socket._io_refs, 0)
            watchdog.cancel.assert_called_once()


if __name__ == '__main__':
    unittest.main()
