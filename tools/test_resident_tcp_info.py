"""Fake-DLL contract tests; no sockets or network calls."""
import ctypes
import unittest

from tools import resident_tcp_info as tcp


class Socket:
    def __init__(self, handle=17):
        self.handle = handle

    def fileno(self):
        return self.handle


class API:
    def __init__(self, result=0, error=0, size=88):
        self.result, self.error, self.size = result, error, size
        self.calls = []

    def ioctl(self, handle, code, incoming, incoming_size, outgoing, outgoing_size, returned, overlapped, completion):
        self.calls.append('ioctl')
        self.handle = handle
        assert code == 0xD8000027 and incoming_size == 4 and outgoing_size == 88
        assert ctypes.cast(incoming, ctypes.POINTER(tcp.U32))[0] == 0
        assert overlapped is None and completion is None
        ctypes.cast(returned, ctypes.POINTER(tcp.U32))[0] = self.size
        info = ctypes.cast(outgoing, ctypes.POINTER(tcp.TCPInfoV0)).contents
        info.State, info.BytesIn, info.BytesOut = 4, 596, 257
        return self.result

    def last_error(self):
        self.calls.append('error')
        return self.error


class Tests(unittest.TestCase):
    def numeric(self, value):
        for item in value.values():
            if isinstance(item, dict):
                self.numeric(item)
            else:
                self.assertIs(type(item), int)

    def test_abi_and_numeric_success(self):
        self.assertTrue(tcp._abi_valid())
        self.assertEqual(ctypes.sizeof(tcp.TCPInfoV0), 88)
        self.assertEqual(tcp.TCPInfoV0.BytesIn.offset, 56)
        api = API(error=12345)
        value = tcp._query(Socket(), api=api, windows=True)
        self.numeric(value)
        self.assertEqual((value['available'], value['bytes_returned'], value['wsa_error']), (1, 88, 0))
        self.assertEqual(value['tcp']['bytes_in'], 596)
        self.assertEqual(api.calls, ['ioctl'])

    def test_failure_captures_error_without_counters(self):
        api = API(result=-1, error=10022, size=0)
        value = tcp._query(Socket(), api=api, windows=True)
        self.assertEqual(api.calls, ['ioctl', 'error'])
        self.assertEqual((value['available'], value['reason'], value['wsa_error']), (0, 5, 10022))
        self.assertNotIn('tcp', value)
        self.numeric(value)

    def test_every_size_mismatch_is_unavailable(self):
        for size in (0, 1, 87, 89, 136, 0xffffffff):
            api = API(size=size)
            value = tcp._query(Socket(), api=api, windows=True)
            self.assertEqual((value['available'], value['reason']), (0, 6))
            self.assertNotIn('tcp', value)

    def test_pointer_width_and_bad_handle(self):
        maximum = (1 << (ctypes.sizeof(ctypes.c_size_t) * 8)) - 1
        api = API()
        tcp._query(Socket(maximum - 1), api=api, windows=True)
        self.assertEqual(api.handle, maximum - 1)
        for handle in (-1, maximum, maximum + 1, True, '17'):
            api = API()
            value = tcp._query(Socket(handle), api=api, windows=True)
            self.assertEqual(value['reason'], 3)
            self.assertEqual(api.calls, [])

    def test_non_windows_does_not_touch_api_or_socket(self):
        api = API()
        value = tcp._query(None, api=api, windows=False)
        self.assertEqual((value['available'], value['reason']), (0, 1))
        self.assertEqual(api.calls, [])

    def test_configured_socket_argument_is_pointer_sized(self):
        if tcp.sys.platform != 'win32':
            self.skipTest('Windows ABI declaration only')
        api = tcp._WinsockAPI()  # Loads DLL; executes no Winsock query.
        self.assertIs(api.ioctl.argtypes[0], ctypes.c_size_t)
        self.assertEqual(len(api.ioctl.argtypes), 9)


if __name__ == '__main__':
    unittest.main()
