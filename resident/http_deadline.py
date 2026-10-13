"""Apply one HTTP deadline to each blocking socket operation.

The watchdog remains a fallback. Recomputing the socket timeout below the
response's BufferedReader also bounds repeated short reads and platforms where
shutdown does not promptly interrupt an already-blocked receive.
"""
from __future__ import annotations

import io


class _DeadlineReader(io.RawIOBase):
    def __init__(self, raw, transport, remaining):
        super().__init__()
        self.raw, self.transport, self.remaining = raw, transport, remaining

    def readable(self):
        return True

    def fileno(self):
        return self.raw.fileno()

    def readinto(self, buffer):
        if self.closed:
            raise ValueError('I/O operation on closed deadline stream')
        self.transport.settimeout(self.remaining())
        result = self.raw.readinto(buffer)
        self.remaining()
        return result

    def close(self):
        if self.closed:
            return
        try:
            self.raw.close()
        finally:
            super().close()


class DeadlineSocket:
    """HTTP-only adapter retaining the socket's original makefile ownership."""
    def __init__(self, transport, remaining):
        self.transport, self.remaining = transport, remaining

    def __getattr__(self, name):
        return getattr(self.transport, name)

    def sendall(self, data, *args, **kwargs):
        self.transport.settimeout(self.remaining())
        result = self.transport.sendall(data, *args, **kwargs)
        self.remaining()
        return result

    def makefile(self, mode='r', buffering=None, *args, **kwargs):
        if mode != 'rb' or args or kwargs or (buffering is not None and
                (type(buffering) is not int or buffering < -1)):
            raise ValueError('Deadline HTTP response requires a binary read stream')
        # The real SocketIO owns exactly one original socket I/O reference.
        # Closing HTTPConnection may detach/close its socket while this stream
        # still owns that reference; closing the response releases it normally.
        raw = self.transport.makefile('rb', buffering=0)
        wrapped = _DeadlineReader(raw, self.transport, self.remaining)
        if buffering == 0:
            return wrapped
        try:
            return io.BufferedReader(wrapped, io.DEFAULT_BUFFER_SIZE if buffering in (None, -1) else buffering)
        except Exception:
            wrapped.close()
            raise
