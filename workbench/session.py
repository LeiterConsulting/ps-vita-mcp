"""A fail-fast reentrant lock shared by all local Vita bridges and runners."""
from contextlib import contextmanager
from pathlib import Path
import os
import threading
from functools import wraps
ROOT=Path(__file__).resolve().parents[1]
_local=threading.RLock()
_depth=threading.local()
@contextmanager
def exclusive():
    if not _local.acquire(blocking=False): raise RuntimeError('Another Vita operation is in progress')
    handle=None
    try:
        depth=getattr(_depth,'value',0)
        if not depth:
            path=Path(os.environ.get('VITA_WORKBENCH_LOCK',str(ROOT/'.devloop-private/workbench.lock')))
            path.parent.mkdir(parents=True,exist_ok=True)
            handle=path.open('a+b')
            if path.stat().st_size==0: handle.write(b'0');handle.flush()
            handle.seek(0)
            try:
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError as error: raise RuntimeError('Another Vita bridge owns the device session') from error
        _depth.value=depth+1
        try: yield
        finally: _depth.value=depth
    finally:
        if handle is not None: handle.close()
        _local.release()
def serialized(function):
    @wraps(function)
    def wrapped(*args,**kwargs):
        with exclusive(): return function(*args,**kwargs)
    return wrapped
