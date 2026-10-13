"""Bounded GET-only transport timing probe. Live execution requires explicit pins.

No request/response bytes, headers, credentials, endpoint addresses or arbitrary
exception messages are retained. Eight observations and fifty seconds are hard
upper bounds; production leases and production source remain unchanged.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import http.client
import io
import json
from pathlib import Path
import socket
import sys
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from resident.keep_awake_client import KeepAwakeClient, PORT, validate
from resident.keep_awake_transport_client import KeepAwakeTransportClient
from resident.launch_client import configuration
from resident.lifecycle_client import hex_pin
from workbench.native_package import json_object

HTTPConnection = http.client.HTTPConnection
HTTPResponse = http.client.HTTPResponse
MAX_EVENTS, MAX_BODY, MAX_HEAD, MAX_OBSERVATIONS, MAX_SECONDS = 256, 8192, 2048, 8, 50
CAUSES = {'TimeoutError': 1, 'OSError': 2, 'ConnectionError': 3,
          'ConnectionResetError': 4, 'ConnectionAbortedError': 5,
          'RemoteDisconnected': 6, 'BadStatusLine': 7, 'IncompleteRead': 8,
          'KeepAwakeLost': 9, 'KeepAwakeRejected': 10, 'TransportLost': 11,
          'TransportRejected': 12, 'TransportUnsupported': 13, 'RuntimeError': 14,
          'ValueError': 15, 'ProbeRefused': 16}


class ProbeRefused(RuntimeError):
    pass


def numeric_error(error):
    number = getattr(error, 'errno', 0)
    return {'cause_code': CAUSES.get(type(error).__name__, 0),
            'errno': number if type(number) is int and -0x80000000 <= number <= 0x7fffffff else 0}


class Events:
    def __init__(self):
        self.utc_before = datetime.now(timezone.utc).isoformat()
        self.started_ns = time.monotonic_ns()
        self.utc_after = datetime.now(timezone.utc).isoformat()
        self.items = []
        self.dropped = 0
        self.raw_bytes = self.raw_chunks = 0
        self.lock = threading.Lock()

    def add(self, event, **fields):
        if any(type(value) not in (int, bool) for value in fields.values()):
            raise ProbeRefused('Non-numeric diagnostic field refused')
        item = {'event': event, 't_ns': time.monotonic_ns(), **fields}
        with self.lock:
            if len(self.items) < MAX_EVENTS:
                self.items.append(item)
            else:
                self.dropped += 1

    def received(self, count):
        with self.lock:
            self.raw_bytes += count
            self.raw_chunks += int(count > 0)
        self.add('raw_receive_end', bytes=count)

    def summary(self):
        with self.lock:
            return {'pc_utc_before': self.utc_before, 'pc_start_monotonic_ns': self.started_ns,
                    'pc_utc_after': self.utc_after, 'events': list(self.items),
                    'dropped_events': self.dropped, 'raw_receive_bytes': self.raw_bytes,
                    'raw_receive_chunks': self.raw_chunks}


class LoggedRaw(io.RawIOBase):
    """Observe actual SocketIO.readinto calls beneath BufferedReader, not lines."""
    def __init__(self, raw, events):
        super().__init__()
        self.raw, self.events = raw, events

    def readable(self):
        return True

    def fileno(self):
        return self.raw.fileno()

    def readinto(self, buffer):
        self.events.add('raw_receive_start', capacity=len(buffer))
        try:
            count = self.raw.readinto(buffer)
            self.events.received(count if count is not None else 0)
            return count
        except Exception as error:
            self.events.add('raw_receive_error', **numeric_error(error))
            raise

    def close(self):
        try:
            self.raw.close()
        finally:
            super().close()


class LoggedSocket:
    def __init__(self, transport, events):
        self.transport, self.events = transport, events

    def __getattr__(self, name):
        return getattr(self.transport, name)

    def sendall(self, data, *args, **kwargs):
        self.events.add('send_start', bytes=len(data))
        try:
            result = self.transport.sendall(data, *args, **kwargs)
            self.events.add('send_end', bytes=len(data))
            return result
        except Exception as error:
            self.events.add('send_error', **numeric_error(error))
            raise

    def recv(self, size):
        self.events.add('raw_receive_start', capacity=size)
        try:
            data = self.transport.recv(size)
            self.events.received(len(data))
            return data
        except Exception as error:
            self.events.add('raw_receive_error', **numeric_error(error))
            raise

    def shutdown(self, how):
        self.events.add('socket_shutdown_start', how=how)
        try:
            result = self.transport.shutdown(how)
            self.events.add('socket_shutdown_end', how=how)
            return result
        except Exception as error:
            self.events.add('socket_shutdown_error', **numeric_error(error))
            raise

    def close(self):
        self.events.add('socket_close_start')
        try:
            return self.transport.close()
        finally:
            self.events.add('socket_close_end')

    def makefile(self, mode='r', buffering=None, *args, **kwargs):
        if mode != 'rb' or args or kwargs or buffering not in (None, -1, 0):
            raise ProbeRefused('Unexpected response stream mode')
        self.events.add('response_stream_created')
        raw = self.transport.makefile('rb', buffering=0)
        logged = LoggedRaw(raw, self.events)
        return logged if buffering == 0 else io.BufferedReader(logged)


def connection_class(events):
    class Response(HTTPResponse):
        def begin(self):
            events.add('parse_headers_start')
            try:
                result = super().begin()
                events.add('parse_headers_end', http_status=self.status)
                return result
            except Exception as error:
                events.add('parse_headers_error', **numeric_error(error))
                raise

        def read(self, amount=None):
            events.add('read_body_start', maximum=-1 if amount is None else amount)
            try:
                data = super().read(amount)
                events.add('read_body_end', bytes=len(data))
                return data
            except Exception as error:
                events.add('read_body_error', **numeric_error(error))
                raise

    class Connection(HTTPConnection):
        response_class = Response

        def connect(self):
            events.add('connect_start')
            try:
                result = super().connect()
                self.sock = LoggedSocket(self.sock, events)
                events.add('connect_end', local_port=self.sock.getsockname()[1])
                return result
            except Exception as error:
                events.add('connect_error', **numeric_error(error))
                raise

        def request(self, *args, **kwargs):
            events.add('request_start')
            try:
                result = super().request(*args, **kwargs)
                events.add('request_end')
                return result
            except Exception as error:
                events.add('request_error', **numeric_error(error))
                raise

        def getresponse(self):
            events.add('getresponse_start')
            try:
                result = super().getresponse()
                events.add('getresponse_end', http_status=result.status)
                return result
            except Exception as error:
                events.add('getresponse_error', **numeric_error(error))
                raise

    return Connection


def request_bytes(endpoint, port):
    # Same HTTPConnection request shape and order, including its two automatic
    # headers. The returned bytes exist only in memory and are never serialized.
    host = endpoint['host'] + (':' + str(port) if port != 80 else '')
    return (f'GET /keep-awake/status HTTP/1.1\r\nHost: {host}\r\nAccept-Encoding: identity\r\n'
            f'Authorization: Bearer {endpoint["token"]}\r\nContent-Type: application/octet-stream\r\n'
            'Connection: close\r\n\r\n').encode('ascii')


def raw_status(client, events, timeout):
    client.check_endpoint()
    deadline = time.monotonic() + timeout
    transport = LoggedSocket(socket.socket(socket.AF_INET, socket.SOCK_STREAM), events)
    expired = threading.Event()

    def check():
        remaining = deadline - time.monotonic()
        if expired.is_set() or remaining <= 0:
            raise TimeoutError('Probe absolute deadline expired')
        return remaining

    def interrupt():
        expired.set()
        events.add('watchdog_fired')
        try:
            transport.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    watchdog = threading.Timer(timeout, interrupt)
    watchdog.daemon = True
    watchdog.start()
    try:
        transport.settimeout(check())
        transport.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        events.add('connect_start')
        transport.connect((client.endpoint['host'], client.port))
        events.add('connect_end', local_port=transport.getsockname()[1])
        check()
        events.add('request_start')
        transport.settimeout(check())
        transport.sendall(request_bytes(client.endpoint, client.port))
        events.add('request_end')
        check()
        events.add('parse_headers_start')
        buffer = bytearray()
        while b'\r\n\r\n' not in buffer:
            if len(buffer) >= MAX_HEAD:
                raise ProbeRefused('Probe response header exceeds bound')
            transport.settimeout(check())
            chunk = transport.recv(min(1024, MAX_HEAD - len(buffer)))
            check()
            if not chunk:
                raise ProbeRefused('Probe response header incomplete')
            buffer.extend(chunk)
        head, body = bytes(buffer).split(b'\r\n\r\n', 1)
        lines = head.split(b'\r\n')
        if lines[0] not in (b'HTTP/1.1 200 OK', b'HTTP/1.0 200 OK'):
            raise ProbeRefused('Probe response status refused')
        headers = {}
        for line in lines[1:]:
            key, separator, value = line.partition(b':')
            key, value = key.lower(), value.strip()
            if not separator or key in headers:
                raise ProbeRefused('Probe response framing refused')
            headers[key] = value
        if (set(headers) - {b'content-type', b'content-length', b'connection', b'cache-control'}
                or headers.get(b'content-type') != b'application/json'
                or headers.get(b'connection') != b'close'
                or not headers.get(b'content-length', b'').isdigit()):
            raise ProbeRefused('Probe response framing refused')
        size = int(headers[b'content-length'])
        if not 0 < size <= MAX_BODY or len(body) > size:
            raise ProbeRefused('Probe response body exceeds bound')
        events.add('parse_headers_end', http_status=200, bytes=len(head) + 4)
        events.add('read_body_start', maximum=size)
        while len(body) < size:
            transport.settimeout(check())
            chunk = transport.recv(min(1024, size - len(body)))
            check()
            if not chunk:
                raise ProbeRefused('Probe response body incomplete')
            body += chunk
        events.add('read_body_end', bytes=len(body))
        result = validate(json_object(body))
        client.check_endpoint()
        check()
        return result
    finally:
        watchdog.cancel()
        transport.close()


def observation(kind, provider, build, instance, *, port=PORT, timeout=5):
    if kind not in ('production', 'raw_socket') or not 0 < timeout <= 5:
        raise ProbeRefused('Invalid bounded observation')
    events = Events()
    result = {'kind': kind, 'deadline_ms': round(timeout * 1000), 'success': False}
    try:
        client = KeepAwakeClient(provider, port=port, timeout=timeout)
        events.add('observation_start')
        if kind == 'production':
            with patch('http.client.HTTPConnection', connection_class(events)):
                reply = client.status()
        else:
            reply = raw_status(client, events, timeout)
        if reply['resident_build_id'] != build or reply['instance_id'] != instance:
            raise ProbeRefused('Probe response identity changed')
        result['success'] = True
        # Retain only whitelisted numeric facts, not the parsed response body.
        result['reply'] = {key: reply[key] for key in ('clock_ms', 'revision', 'active', 'remaining_ms',
                                                     'session_remaining_ms', 'tick_count', 'tick_result')}
        events.add('observation_end')
    except Exception as error:
        result['failure'] = numeric_error(error)
        diagnostic = getattr(error, 'lease_diagnostic', None)
        if isinstance(diagnostic, dict) and diagnostic.get('phase') in (
                'configuration_check', 'connection_setup', 'send_request', 'read_headers', 'read_body', 'validate_reply'):
            result['failure_phase'] = diagnostic['phase']
        events.add('observation_error', **numeric_error(error))
    result.update(events.summary())
    return result


def ring_status(provider, build, instance, remaining):
    return KeepAwakeTransportClient(provider, timeout=min(5, remaining)).status(build, instance)


def run_live(build, instance, output):
    if not hex_pin(build, 64) or not hex_pin(instance, 32):
        raise ProbeRefused('Exact build and power-instance pins are required')
    output = output.resolve()
    if ROOT.resolve() not in output.parents or output.exists():
        raise ProbeRefused('Choose a new evidence file inside this workspace')
    endpoint = configuration()
    def provider():
        current = configuration()
        if current != endpoint:
            raise ProbeRefused('Probe administrator endpoint changed')
        return current
    started = time.monotonic()
    deadline = started + MAX_SECONDS
    report = {'started_utc': datetime.now(timezone.utc).isoformat(), 'resident_build_id': build,
              'instance_id': instance, 'max_seconds': MAX_SECONDS, 'max_observations': MAX_OBSERVATIONS,
              'device_mutations': 0, 'mutation_replays': 0, 'cause_codes': CAUSES,
              'observations': [], 'result': 'bounded observations complete'}
    def remaining():
        value = deadline - time.monotonic()
        if value <= 0:
            raise TimeoutError('Probe total budget exhausted')
        return value
    try:
        # AB / BA / AB / BA balances which client is first after an idle gap.
        kinds = ('production', 'raw_socket', 'raw_socket', 'production',
                 'production', 'raw_socket', 'raw_socket', 'production')
        for index, kind in enumerate(kinds):
            if index and index % 2 == 0:
                pause = min(8, remaining())
                time.sleep(pause)
            if remaining() < 5:
                report['result'] = 'total budget prevents another five-second observation'
                break
            before = ring_status(provider, build, instance, remaining())
            if remaining() < 5:
                report['result'] = 'total budget prevents another five-second observation'
                break
            trial = observation(kind, provider, build, instance)
            report['observations'].append(trial)
            trial['native_before'] = {'newest_seq': before['newest_seq'], 'count': before['count']}
            after = ring_status(provider, build, instance, remaining())
            trial['native_after'] = {'oldest_seq': after['oldest_seq'], 'newest_seq': after['newest_seq'],
                                     'count': after['count']}
            first, last = int(before['newest_seq'], 16) + 1, int(after['newest_seq'], 16)
            delta = last - first + 1
            trial['native_match'] = 'single_record' if delta == 1 else 'ambiguous_or_unrecorded'
            trial['native_candidates'] = []
            # A concurrently held external keeper can add its own GET/POST.
            # Do not assert a unique match or scan unbounded historical records.
            if 0 < delta <= 4:
                for sequence in range(first, last + 1):
                    record = KeepAwakeTransportClient(provider, timeout=min(5, remaining())).record(
                        f'{sequence:016x}', build, instance)
                    trial['native_candidates'].append(record)
                if delta == 1 and (record.get('record_status') != 'available'
                                   or record.get('method') != 1 or record.get('operation') != 1):
                    trial['native_match'] = 'unmatched_record'
            elif delta > 4:
                trial['native_match'] = 'ambiguous_more_than_four_records'
    except Exception as error:
        report['result'] = 'stopped on diagnostic failure or total budget'
        report['failure'] = numeric_error(error)
    report['elapsed_ms'] = round((time.monotonic() - started) * 1000)
    report['completed_utc'] = datetime.now(timezone.utc).isoformat()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps({'result': report['result'], 'observations': len(report['observations']),
                      'elapsed_ms': report['elapsed_ms'], 'evidence_file': str(output),
                      'device_mutations': 0, 'mutation_replays': 0}))
    return report


def smoke():
    """Offline localhost only: success, stalled headers, partial header bytes."""
    import socketserver
    build, instance, token = 'b' * 64, 'c' * 32, 'f' * 32
    mode, requests = ['success'], []
    reply = {'app': 'Vita Resident Keep Awake', 'protocol': 1, 'resident_build_id': build,
             'instance_id': instance, 'clock_ms': 100, 'revision': 0, 'port': PORT,
             'active': False, 'lease_id': None, 'job_id': None, 'remaining_ms': 0,
             'session_remaining_ms': 0, 'last_tick_ms': 0, 'tick_count': 0,
             'tick_result': 0, 'reason': 'boot', 'status': 200, 'error': None}
    body = json.dumps(reply, separators=(',', ':')).encode()
    head = (f'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n'
            'Connection: close\r\nCache-Control: no-store\r\n\r\n').encode()
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            data = b''
            self.request.settimeout(1)
            while b'\r\n\r\n' not in data and len(data) < 2048:
                chunk = self.request.recv(1024)
                if not chunk:
                    return
                data += chunk
            requests.append(data)  # In-memory comparison only; never serialized.
            current = mode[0]
            try:
                if current == 'success':
                    self.request.sendall(head + body)
                elif current == 'partial_headers':
                    self.request.sendall(head[:23])
                    time.sleep(0.35)
                else:
                    time.sleep(0.35)
            except OSError:
                pass
    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True
    trials = []
    with Server(('127.0.0.1', 0), Handler) as server:
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
        thread.start()
        endpoint = {'host': '127.0.0.1', 'port': 17866, 'token': token}
        try:
            for scenario in ('success', 'stall_headers', 'partial_headers'):
                mode[0] = scenario
                for kind in ('production', 'raw_socket'):
                    trial = observation(kind, lambda: endpoint.copy(), build, instance,
                                        port=server.server_address[1], timeout=0.15)
                    trial['scenario'] = scenario
                    trials.append(trial)
                    assert trial['success'] is (scenario == 'success')
                    assert all(event.get('bytes', 0) >= 0 for event in trial['events'])
                    if scenario == 'partial_headers':
                        assert trial['raw_receive_bytes'] == 23
                    elif scenario == 'stall_headers':
                        assert trial['raw_receive_bytes'] == 0
                    # Either the OS socket timeout or the watchdog can win.
                    assert scenario == 'success' or trial['failure']['cause_code'] == 1
            assert len(requests) == 6
            assert requests[0] == requests[1] == request_bytes(endpoint, server.server_address[1])
            assert all(request.startswith(b'GET /keep-awake/status HTTP/1.1\r\n') for request in requests)
            serialized = json.dumps(trials, allow_nan=False)
            assert token not in serialized and 'Bearer' not in serialized and 'Authorization' not in serialized
            assert 'Content-Type' not in serialized and body.decode() not in serialized
            assert HTTPConnection is http.client.HTTPConnection
        finally:
            server.shutdown()
            thread.join(timeout=1)
    print(json.dumps({'offline_localhost_only': True, 'passed': 6, 'request_shapes_identical': True,
                      'stalled_and_partial_headers_timed_out': True, 'raw_header_bytes_logged': False,
                      'credential_leaks': 0, 'device_mutations': 0}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--resident-build-id')
    parser.add_argument('--instance-id')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.smoke:
        if any(value is not None for value in (args.resident_build_id, args.instance_id, args.output)):
            parser.error('Smoke uses localhost only and accepts no live arguments')
        smoke()
    else:
        if args.output is None:
            parser.error('Provide a new --output path and exact build/instance pins')
        run_live(args.resident_build_id, args.instance_id, args.output)


if __name__ == '__main__':
    main()
