"""Read-only, administrator-only inspection of the keep-awake transport ring.

These GETs never submit, renew, reconcile or replay a lease. Diagnostics omit
request headers, bodies, authorization and arbitrary remote error text.
"""
from __future__ import annotations

import http.client
import ipaddress
import re
import socket
import threading
import time

from resident.keep_awake_client import PORT
from resident.http_deadline import DeadlineSocket
from resident.launch_client import configuration
from resident.lifecycle_client import hex_pin
from workbench.native_package import json_object

APP = 'Vita Resident Keep Awake Transport'
MAX_REPLY_BYTES = 1399
STATUS_PATH = '/keep-awake/transport-status'
RECORD_PREFIX = '/keep-awake/transport-record/'
U32, U64 = 0xffffffff, 0xffffffffffffffff
COMMON = {'app', 'protocol', 'resident_build_id', 'instance_id', 'status'}
STATUS_FIELDS = COMMON | {'capacity', 'record_bytes', 'count', 'oldest_seq', 'newest_seq',
                         'overwritten', 'diagnostic_reads', 'accepted', 'listen_attempts', 'listen_failures',
                         'accept_would_block', 'accept_failures', 'listener_generation', 'listener', 'network',
                         'sequence_exhausted', 'resource_sampling'}
RECORD_FIELDS = COMMON | {'seq', 'listener_generation', 'accepted_ms', 'method', 'operation',
                         'phase_ms', 'bytes', 'would_block', 'revision', 'apply_result', 'http_status',
                         'outcome', 'io_stage', 'io_result', 'io_errno', 'accept_result', 'accept_errno',
                         'close_result', 'close_errno', 'tick_count', 'max_gap_ms', 'flags'}


class TransportUnsupported(RuntimeError):
    """The installed listener does not implement the diagnostic routes."""
    status = 404
    classification = 'unsupported'


class TransportRejected(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__('Resident transport inspection rejected with HTTP ' + str(status))


class TransportLost(RuntimeError):
    pass


def _endpoint(provider):
    try:
        value = provider()
        if not isinstance(value, dict) or set(value) != {'host', 'port', 'token'}:
            raise ValueError()
        if not isinstance(value['host'], str):
            raise ValueError()
        host = ipaddress.IPv4Address(value['host'])
        if (not (host.is_private or host.is_loopback) or host.is_unspecified or host.is_multicast
                or type(value['port']) is not int or not 1 <= value['port'] <= 65535
                or not hex_pin(value['token'], 32)):
            raise ValueError()
        return {'host': str(host), 'port': value['port'], 'token': value['token']}
    except Exception:
        raise TransportLost('Resident administrator endpoint is not configured locally') from None


def _pins(resident_build_id, instance_id, *, required=False):
    if not required and resident_build_id is None and instance_id is None:
        return
    if not hex_pin(resident_build_id, 64) or not hex_pin(instance_id, 32):
        raise ValueError('Pin the exact Resident build and keep-awake instance')


def _integer(value, maximum=U64, minimum=0):
    return type(value) is int and minimum <= value <= maximum


def _signed(value):
    return _integer(value, 0x7fffffff, -0x80000000)


def _sequence(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{16}', value) is not None


def _common(value, code, resident_build_id=None, instance_id=None):
    if (not isinstance(value, dict) or value.get('app') != APP
            or type(value.get('protocol')) is not int or value['protocol'] != 1
            or type(value.get('status')) is not int or value['status'] != code
            or not hex_pin(value.get('resident_build_id'), 64) or not hex_pin(value.get('instance_id'), 32)
            or resident_build_id is not None and value['resident_build_id'] != resident_build_id
            or instance_id is not None and value['instance_id'] != instance_id):
        raise TransportLost('Invalid or changed Resident transport identity')


def validate_status(value, *, resident_build_id=None, instance_id=None):
    _common(value, 200, resident_build_id, instance_id)
    if (set(value) != STATUS_FIELDS or not _integer(value['capacity'], 16, 16)
            or not _integer(value['record_bytes'], 192, 1) or not _integer(value['count'], 16)
            or not _sequence(value['oldest_seq']) or not _sequence(value['newest_seq'])
            or not _integer(value['listener_generation'], U32)
            or any(not _integer(value[key]) for key in ('overwritten', 'diagnostic_reads', 'accepted',
                                                       'listen_attempts', 'listen_failures', 'accept_would_block',
                                                       'accept_failures'))
            or type(value['sequence_exhausted']) is not bool or value['resource_sampling'] is not False):
        raise TransportLost('Invalid Resident transport status counters')
    oldest, newest = int(value['oldest_seq'], 16), int(value['newest_seq'], 16)
    if (value['count'] == 0 and (oldest != 0 or newest != 0)
            or value['count'] > 0 and (oldest == 0 or newest < oldest or newest - oldest + 1 != value['count'])
            or value['sequence_exhausted'] and newest != U64):
        raise TransportLost('Invalid Resident transport ring bounds')
    listener, network = value['listener'], value['network']
    if (not isinstance(listener, dict)
            or set(listener) != {'clock_ms', 'stage', 'result', 'errno', 'close_result', 'close_errno'}
            or not _integer(listener['clock_ms']) or not _integer(listener['stage'], 10)
            or any(not _signed(listener[key]) for key in ('result', 'errno', 'close_result', 'close_errno'))
            or not isinstance(network, dict)
            or set(network) != {'result', 'state', 'changes', 'clock_ms', 'max_gap_ms',
                                'last_loss_result', 'last_loss_state', 'last_loss_ms'}
            or any(not _signed(network[key]) for key in ('result', 'state', 'last_loss_result', 'last_loss_state'))
            or any(not _integer(network[key]) for key in ('changes', 'clock_ms', 'last_loss_ms'))
            or not _integer(network['max_gap_ms'], U32)):
        raise TransportLost('Invalid Resident transport listener or network observation')
    return value


def validate_record(value, code, sequence, resident_build_id, instance_id):
    _common(value, code, resident_build_id, instance_id)
    if value.get('seq') != sequence or not _sequence(value.get('seq')):
        raise TransportLost('Resident transport record differs from the requested sequence')
    if code == 404:
        if (set(value) != COMMON | {'seq', 'error'} or type(value['error']) is not int
                or value['error'] not in (1, 2) or int(sequence, 16) == 0 and value['error'] != 1):
            raise TransportLost('Invalid Resident transport record absence')
        return value | {'record_status': 'not_found' if value['error'] == 1 else 'overwritten'}
    if (code != 200 or int(sequence, 16) == 0 or set(value) != RECORD_FIELDS
            or not _integer(value['listener_generation'], U32) or not _integer(value['accepted_ms'])
            or not _integer(value['method'], 2) or not _integer(value['operation'], 4)
            or not _integer(value['outcome'], 10) or not _integer(value['io_stage'], 10)
            or not _integer(value['max_gap_ms'], U32) or not _integer(value['flags'], 31)
            or not _integer(value['http_status'], 599)
            or value['http_status'] != 0 and value['http_status'] < 100
            or any(not _signed(value[key]) for key in ('apply_result', 'io_result', 'io_errno',
                                                       'accept_result', 'accept_errno', 'close_result', 'close_errno'))):
        raise TransportLost('Invalid Resident transport record counters or enums')
    for key, count, maximum in (('phase_ms', 8, U32), ('bytes', 3, U32), ('would_block', 2, U32),
                                ('revision', 2, U32), ('tick_count', 2, U64)):
        if (not isinstance(value[key], list) or len(value[key]) != count
                or any(not _integer(item, maximum) for item in value[key])):
            raise TransportLost('Invalid Resident transport record vector')
    return value | {'record_status': 'available'}


class KeepAwakeTransportClient:
    def __init__(self, provider=configuration, *, port=PORT, timeout=5):
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('Invalid transport listener port')
        if type(timeout) not in (int, float) or not 0 < timeout <= 5:
            raise ValueError('Transport HTTP timeout must be positive and at most five seconds')
        self.provider, self.port, self.timeout = provider, port, timeout
        self.endpoint = _endpoint(provider)

    def check_endpoint(self):
        if _endpoint(self.provider) != self.endpoint:
            raise TransportLost('Resident administrator endpoint configuration changed')

    def _get(self, path, validate):
        if path != STATUS_PATH and not (path.startswith(RECORD_PREFIX)
                and re.fullmatch('[0-9a-f]{16}', path[len(RECORD_PREFIX):])):
            raise ValueError('Choose a fixed transport inspection route')
        self.check_endpoint()
        try:
            connection = http.client.HTTPConnection(self.endpoint['host'], self.port, timeout=self.timeout)
        except Exception:
            raise TransportLost('Resident transport connection setup failed') from None
        deadline = time.monotonic() + self.timeout
        expired = threading.Event()
        connected_socket = [None]

        # Same bounded GET algorithm as KeepAwakeClient: retain the connected
        # socket before Connection: close detaches it, interrupt drip-fed I/O,
        # and check the absolute deadline again before accepting any reply.
        def interrupt():
            expired.set()
            if connected_socket[0] is not None:
                try:
                    connected_socket[0].shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        def remaining_timeout():
            remaining = deadline - time.monotonic()
            if expired.is_set() or remaining <= 0:
                raise TimeoutError('Resident transport absolute HTTP deadline expired')
            return remaining

        def check_deadline():
            remaining_timeout()

        watchdog = threading.Timer(self.timeout, interrupt)
        watchdog.daemon = True
        watchdog.start()
        response = None
        try:
            connection.timeout = remaining_timeout()
            connection.connect()
            connection.sock = DeadlineSocket(connection.sock, remaining_timeout)
            connected_socket[0] = connection.sock
            check_deadline()
            connection.request('GET', path, headers={'Authorization': 'Bearer ' + self.endpoint['token'],
                                                     'Connection': 'close'})
            check_deadline()
            response = connection.getresponse()
            check_deadline()
            raw = response.read(MAX_REPLY_BYTES + 1)
            check_deadline()
            if (len(raw) > MAX_REPLY_BYTES
                    or response.getheader('Content-Type', '').split(';')[0] != 'application/json'):
                raise TransportLost('Invalid Resident transport response bounds or content type')
            if response.status in (401, 403):
                raise TransportRejected(response.status)
            try:
                value = json_object(raw)
            except (ValueError, UnicodeError, TypeError):
                raise TransportLost('Invalid Resident transport JSON response') from None
            if response.status == 404 and value == {'error': 'route_not_found'}:
                raise TransportUnsupported('Installed Resident does not implement transport inspection')
            if response.status not in (200, 404):
                raise TransportRejected(response.status)
            result = validate(value, response.status)
            self.check_endpoint()
            check_deadline()
            return result
        except (TransportLost, TransportRejected, TransportUnsupported, TimeoutError):
            raise
        except Exception:
            if expired.is_set():
                raise TimeoutError('Resident transport absolute HTTP deadline expired') from None
            raise TransportLost('Resident transport inspection interrupted') from None
        finally:
            watchdog.cancel()
            try:
                if response is not None:
                    response.close()
            except Exception:
                pass
            try:
                connection.close()
            except Exception:
                pass

    def status(self, resident_build_id=None, instance_id=None):
        _pins(resident_build_id, instance_id)
        def validate(value, code):
            if code != 200:
                raise TransportLost('Invalid Resident transport status acknowledgement')
            return validate_status(value, resident_build_id=resident_build_id, instance_id=instance_id)
        return self._get(STATUS_PATH, validate)

    def record(self, sequence, resident_build_id, instance_id):
        if not _sequence(sequence):
            raise ValueError('Choose an exact 16-character lowercase hexadecimal transport sequence')
        _pins(resident_build_id, instance_id, required=True)
        return self._get(RECORD_PREFIX + sequence,
                         lambda value, code: validate_record(value, code, sequence, resident_build_id, instance_id))


def register(mcp, configuration, read_annotations):
    @mcp.tool(annotations=read_annotations)
    def vita_resident_keep_awake_transport_status(resident_build_id: str | None = None,
                                                 instance_id: str | None = None) -> dict:
        """Read Resident 0.1.7's bounded transport ring/listener counters; optional exact build and power-instance pins must be supplied together. Administrator-only GET; never renews, replays or changes a lease. Older listeners report unsupported."""
        return KeepAwakeTransportClient(configuration).status(resident_build_id, instance_id)

    @mcp.tool(annotations=read_annotations)
    def vita_resident_keep_awake_transport_record(sequence: str, resident_build_id: str, instance_id: str) -> dict:
        """Read one completed transport sequence (exact 16 lowercase hex) pinned to its Resident build and power-worker instance. Reports available, not_found or overwritten; numeric diagnostics exclude headers, bodies and credentials. GET only."""
        return KeepAwakeTransportClient(configuration).record(sequence, resident_build_id, instance_id)
