"""Live sanitized records; bounded framing and diagnostics, stdlib on Windows/POSIX.

Known credentials are redacted on complete LF/CRLF records (including EOF).
Records over RECORD_LIMIT Unicode characters are wholly omitted, never emitted in fragments.
Unknown secret formats or secrets spanning logical records cannot be recognized.
"""
import os
import signal
import subprocess
import sys
import threading
import time
from scripts.command_errors import SUMMARY_LIMIT, redact, safe_command

RECORD_LIMIT = 16384  # Unicode characters, excluding LF/CRLF
BYTE_LIMIT = RECORD_LIMIT * 4  # largest valid UTF-8 payload; bounded before decoding
READ_SIZE = 4096
OMITTED = '[overlong output record omitted]\n'


class _WindowsJob:
    """Own descendants even if the initial process exits before pipe EOF."""
    def __init__(self):
        import ctypes
        from ctypes import wintypes as w
        class Limits(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
                        ('flags', w.DWORD), ('min_working', ctypes.c_size_t),
                        ('max_working', ctypes.c_size_t), ('active', w.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in
                        ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]
        class Extended(ctypes.Structure):
            _fields_ = [('basic', Limits), ('io', IO), ('process_memory', ctypes.c_size_t),
                        ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t),
                        ('peak_job', ctypes.c_size_t)]
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        self.api.CreateJobObjectW.restype = w.HANDLE
        self.api.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        self.api.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.api.CloseHandle.argtypes = [w.HANDLE]
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError('Could not create build process job')
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise OSError('Could not configure build process job')

    def assign(self, process):
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise OSError('Could not assign build process to job')

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def _available_reader(pipe):
    if os.name != 'nt':
        import select
        def read():
            return os.read(pipe.fileno(), READ_SIZE) if select.select([pipe], [], [], .05)[0] else None
        return read
    import ctypes
    import msvcrt
    from ctypes import wintypes as w
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.PeekNamedPipe.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD,
                                 ctypes.c_void_p, ctypes.POINTER(w.DWORD), ctypes.c_void_p]
    handle = msvcrt.get_osfhandle(pipe.fileno())
    def read():
        available = w.DWORD()
        if not api.PeekNamedPipe(handle, None, 0, None, ctypes.byref(available), None):
            if ctypes.get_last_error() in (109, 232):  # pipe closed / no data
                return b''
            raise OSError('Could not read build output pipe')
        return os.read(pipe.fileno(), min(available.value, READ_SIZE)) if available.value else None
    return read


def run_streamed(command, *, cwd=None, timeout=1800, stream=None):
    stream = sys.stdout if stream is None else stream
    deadline = time.monotonic() + timeout
    job = _WindowsJob() if os.name == 'nt' else None
    options = {'start_new_session': True} if os.name != 'nt' else {
        'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
    process = None
    reader = None
    stop = threading.Event()
    failed = threading.Event()
    tail = ''

    def terminate():
        if job is not None:
            job.close()  # Windows Job kills the entire owned tree, including orphans.
        elif process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if process is not None and process.poll() is None:
            process.kill()

    def emit(record):
        nonlocal tail
        text = record.decode('utf-8', 'replace').replace('\r\n', '\n')
        payload = text[:-1] if text.endswith('\n') else text
        safe = OMITTED if len(payload)>RECORD_LIMIT else redact(text)
        tail = (tail + safe)[-SUMMARY_LIMIT:]
        stream.write(safe)
        stream.flush()

    def read():
        pending = bytearray()
        dropping = False
        try:
            read_available = _available_reader(process.stdout)
            while not stop.is_set():
                chunk = read_available()
                if chunk is None:
                    stop.wait(.01)
                    continue
                if not chunk:
                    if pending and not dropping:
                        emit(OMITTED.encode() if len(pending)>BYTE_LIMIT else bytes(pending))
                    return
                # Framing never buffers more than BYTE_LIMIT + one fixed chunk.
                parts = chunk.split(b'\n')
                for index, part in enumerate(parts):
                    if not dropping:
                        size = len(pending) + len(part)
                        # Permit one pending CR solely to recognize a split CRLF.
                        trailing_cr = part.endswith(b'\r') or (not part and pending.endswith(b'\r'))
                        if size > BYTE_LIMIT and not (size == BYTE_LIMIT+1 and trailing_cr):
                            pending.clear()
                            dropping = True
                            emit(OMITTED.encode())
                        else:
                            pending.extend(part)
                    if index < len(parts) - 1:
                        if not dropping:
                            emit(bytes(pending) + b'\n')
                        pending.clear()
                        dropping = False
        except Exception:
            # Never store/propagate raw sink or pipe exception messages.
            failed.set()

    try:
        start_failure = None
        try:
            process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, bufsize=0, **options)
            process.args = safe_command(command)
            if job is not None:
                job.assign(process)
        except Exception as error:
            start_failure = (type(error).__name__, getattr(error, 'errno', None))
            terminate()
            if process is not None:
                process.wait(timeout=10)
        if start_failure is not None:
            raise RuntimeError(f'Could not start isolated build process; type={start_failure[0]}; errno={start_failure[1]}')
        reader = threading.Thread(target=read, name='life-journal-output-reader', daemon=True)
        reader.start()
        timed_out = False
        while process.poll() is None or reader.is_alive():
            if failed.is_set():
                terminate()
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                terminate()
                break
            failed.wait(min(.05, remaining))
        if timed_out or failed.is_set():
            process.wait(timeout=10)
            stop.set()
        reader.join(timeout=10)
        if reader.is_alive():
            raise RuntimeError('Build output reader did not stop')
        if failed.is_set():
            raise RuntimeError('Build output handling failed; process tree stopped')
        if timed_out:
            raise subprocess.TimeoutExpired(safe_command(command), timeout, stderr=tail)
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, safe_command(command), stderr=tail)
    finally:
        stop.set()
        if process is not None and process.poll() is None:
            terminate()
            process.wait(timeout=10)
        if job is not None:
            job.close()
        if reader is not None:
            reader.join(timeout=10)
        if process is not None and (reader is None or not reader.is_alive()):
            process.stdout.close()
