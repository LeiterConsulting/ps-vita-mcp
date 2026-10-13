"""Payload-free Windows per-socket TCP_INFO_v0 observation.

query(sock) never receives, sends, peeks, shuts down, closes, duplicates, or
changes settings on the supplied socket. All returned values are numeric.
elapsed_ns measures the IOCTL interval; first-use DLL loading is outside it.
Reason: 0 success, 1 platform, 2 ABI, 3 socket, 4 API unavailable,
5 IOCTL failure, 6 output-size mismatch, 7 unexpected local failure.
This is diagnostic evidence, never lease/effect authority.
"""
from __future__ import annotations

import ctypes
import sys
import time

SIO_TCP_INFO = 0xD8000027
EXPECTED_BYTES = 88
U32 = ctypes.c_uint32
U64 = ctypes.c_uint64
U8 = ctypes.c_uint8


class TCPInfoV0(ctypes.Structure):
    # Natural MS ABI alignment; BOOLEAN is one byte, not a four-byte BOOL.
    _fields_ = [
        ('State', U32), ('Mss', U32), ('ConnectionTimeMs', U64),
        ('TimestampsEnabled', U8), ('RttUs', U32), ('MinRttUs', U32),
        ('BytesInFlight', U32), ('Cwnd', U32), ('SndWnd', U32),
        ('RcvWnd', U32), ('RcvBuf', U32), ('BytesOut', U64),
        ('BytesIn', U64), ('BytesReordered', U32), ('BytesRetrans', U32),
        ('FastRetrans', U32), ('DupAcksIn', U32), ('TimeoutEpisodes', U32),
        ('SynRetrans', U8),
    ]


_FIELDS = (
    ('state', 'State'), ('mss', 'Mss'), ('connection_time_ms', 'ConnectionTimeMs'),
    ('timestamps_enabled', 'TimestampsEnabled'), ('rtt_us', 'RttUs'),
    ('min_rtt_us', 'MinRttUs'), ('bytes_in_flight', 'BytesInFlight'),
    ('cwnd', 'Cwnd'), ('snd_wnd', 'SndWnd'), ('rcv_wnd', 'RcvWnd'),
    ('rcv_buf', 'RcvBuf'), ('bytes_out', 'BytesOut'), ('bytes_in', 'BytesIn'),
    ('bytes_reordered', 'BytesReordered'), ('bytes_retrans', 'BytesRetrans'),
    ('fast_retrans', 'FastRetrans'), ('dup_acks_in', 'DupAcksIn'),
    ('timeout_episodes', 'TimeoutEpisodes'), ('syn_retrans', 'SynRetrans'),
)
_OFFSETS = (0, 4, 8, 16, 20, 24, 28, 32, 36, 40, 44, 48, 56, 64, 68, 72, 76, 80, 84)
_API = None


def _abi_valid():
    return (ctypes.sizeof(TCPInfoV0) == EXPECTED_BYTES
            and ctypes.alignment(TCPInfoV0) == 8
            and ctypes.sizeof(ctypes.c_size_t) in (4, 8)
            and tuple(getattr(TCPInfoV0, field).offset for field, _ in TCPInfoV0._fields_) == _OFFSETS)


class _WinsockAPI:
    def __init__(self):
        self.library = ctypes.WinDLL('Ws2_32.dll')
        self.ioctl = self.library.WSAIoctl
        self.ioctl.restype = ctypes.c_int
        self.ioctl.argtypes = [ctypes.c_size_t, U32, ctypes.c_void_p, U32,
                              ctypes.c_void_p, U32, ctypes.POINTER(U32),
                              ctypes.c_void_p, ctypes.c_void_p]
        self.last_error = self.library.WSAGetLastError
        self.last_error.restype = ctypes.c_int
        self.last_error.argtypes = []


def _query(sock, *, api=None, windows=None):
    """Internal injection seam for fake-DLL tests; public query uses real OS."""
    global _API
    result = {'available': 0, 'version': 0, 'struct_bytes': ctypes.sizeof(TCPInfoV0),
              'socket_bytes': ctypes.sizeof(ctypes.c_size_t), 'bytes_returned': 0,
              'result': -1, 'wsa_error': 0, 'elapsed_ns': 0, 'reason': 1}
    if not (sys.platform == 'win32' if windows is None else windows):
        return result
    if not _abi_valid():
        result['reason'] = 2
        return result
    try:
        handle = sock.fileno()
        if (type(handle) is not int or handle < 0
                or handle >= (1 << (ctypes.sizeof(ctypes.c_size_t) * 8)) - 1):
            result['reason'] = 3
            return result
    except Exception:
        result['reason'] = 3
        return result
    if api is None:
        try:
            if _API is None:
                _API = _WinsockAPI()
            api = _API
        except Exception:
            result['reason'] = 4
            return result
    version, returned, info = U32(0), U32(0), TCPInfoV0()
    started = time.perf_counter_ns()
    try:
        raw = int(api.ioctl(handle, SIO_TCP_INFO, ctypes.byref(version), 4,
                            ctypes.byref(info), EXPECTED_BYTES, ctypes.byref(returned), None, None))
        # This must precede timing, formatting, or any other Winsock call.
        error = int(api.last_error()) if raw != 0 else 0
        result.update(result=max(-0x80000000, min(0x7fffffff, raw)),
                      wsa_error=max(-0x80000000, min(0x7fffffff, error)),
                      bytes_returned=int(returned.value),
                      elapsed_ns=max(0, min((1 << 64) - 1, time.perf_counter_ns() - started)))
        if raw != 0:
            result['reason'] = 5
        elif returned.value != EXPECTED_BYTES:
            result['reason'] = 6
        else:
            result.update(available=1, reason=0,
                          tcp={name: int(getattr(info, field)) for name, field in _FIELDS})
    except Exception:
        result.update(reason=7, elapsed_ns=max(0, min((1 << 64) - 1, time.perf_counter_ns() - started)))
    return result


def query(sock):
    return _query(sock)


def _qualify_localhost():
    """Known-length loopback only; never consults Vita configuration."""
    import socket
    samples = []

    def observe(label, sock):
        started = time.perf_counter_ns()
        value = query(sock)
        elapsed = time.perf_counter_ns() - started
        samples.append({'label': label, 'snapshot': value, 'observer_elapsed_ns': elapsed})
        if value['available'] != 1:
            raise RuntimeError('TCP_INFO unavailable during localhost qualification')
        return value['tcp']

    def wait_for(label, sock, key, wanted):
        deadline = time.monotonic() + 1
        for _ in range(100):
            value = observe(label, sock)
            if value[key] == wanted:
                return value
            if time.monotonic() >= deadline:
                break
            time.sleep(.01)
        raise RuntimeError('Localhost TCP counter did not reach its expected value')

    def receive(sock, expected):
        data = bytearray()
        while len(data) < len(expected):
            part = sock.recv(len(expected) - len(data))
            if not part:
                raise RuntimeError('Early localhost EOF')
            data.extend(part)
        if data != expected:
            raise RuntimeError('Localhost byte mismatch')
        return len(data)

    request, response = b'Q' * 257, b'R' * 596
    proof = {'result': 'failed', 'scope': 'localhost only; no Vita/configuration/packet capture',
             'request_bytes': len(request), 'response_bytes': len(response), 'samples': samples}
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.settimeout(2)
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.settimeout(2)
            started = time.perf_counter_ns()
            client.connect(listener.getsockname())
            proof['connect_elapsed_ns'] = time.perf_counter_ns() - started
            server, peer = listener.accept()
            with server:
                server.settimeout(2)
                if peer[0] != '127.0.0.1':
                    raise RuntimeError('Non-local peer refused')
                initial_client = observe('client_connected', client)
                initial_server = observe('server_accepted', server)
                client.sendall(request)
                server_before_read = wait_for('server_before_application_read', server, 'bytes_in', len(request))
                proof['server_application_bytes'] = receive(server, request)
                server_after_read = observe('server_after_application_read', server)
                server.sendall(response)
                client_before_read = wait_for('client_before_application_read', client, 'bytes_in', len(response))
                proof['client_application_bytes'] = receive(client, response)
                client_after_read = observe('client_after_application_read', client)
                if (initial_client['bytes_in'] != 0 or initial_client['bytes_out'] != 0
                        or initial_server['bytes_in'] != 0 or initial_server['bytes_out'] != 0
                        or server_before_read['bytes_in'] != server_after_read['bytes_in']
                        or client_before_read['bytes_in'] != client_after_read['bytes_in']
                        or client_after_read['bytes_out'] != len(request)
                        or server_after_read['bytes_out'] != 0):
                    raise RuntimeError('Localhost TCP byte-count basis differs')
                server_after_send = observe('server_after_send', server)
                if server_after_send['bytes_out'] != len(response):
                    raise RuntimeError('Localhost sent-byte basis differs')
            # Peer close is confined to this disposable loopback fixture.
            wait_for('client_after_peer_close', client, 'state', 7)
            if client.recv(1) != b'':
                raise RuntimeError('Expected localhost peer EOF')
            proof['peer_fin_close_wait_observed'] = 1
    proof.update(result='passed', tcp_bytes_count_payload_before_application_read=1,
                 query_count=len(samples), max_query_elapsed_ns=max(item['snapshot']['elapsed_ns'] for item in samples),
                 max_observer_elapsed_ns=max(item['observer_elapsed_ns'] for item in samples))
    return proof


if __name__ == '__main__':
    import argparse
    from datetime import datetime, timezone
    import hashlib
    import json
    from pathlib import Path
    import uuid

    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('qualify-localhost',))
    parser.parse_args()
    folder = Path(__file__).resolve().parents[1] / 'evidence' / 'resident' / ('tcp-info-localhost-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True, exist_ok=False)
    try:
        evidence = _qualify_localhost()
    except Exception as error:
        evidence = {'result': 'failed', 'scope': 'localhost only', 'error_type': type(error).__name__}
    evidence.update(python_version=list(sys.version_info[:3]), windows_build=sys.getwindowsversion().build if sys.platform == 'win32' else 0,
                    utility_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (folder / 'proof.json').write_text(json.dumps(evidence, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'result': evidence['result'], 'proof': str(folder / 'proof.json')}))
    raise SystemExit(0 if evidence['result'] == 'passed' else 1)
