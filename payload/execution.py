"""Own the lifetime and cancellation record of one local desktop request."""
import ctypes as c
from ctypes import wintypes as w
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time


class BasicLimits(c.Structure):
    _fields_ = [("process_time", c.c_longlong), ("job_time", c.c_longlong),
                ("flags", w.DWORD), ("min_ws", c.c_size_t), ("max_ws", c.c_size_t),
                ("processes", w.DWORD), ("affinity", c.c_size_t),
                ("priority", w.DWORD), ("scheduling", w.DWORD)]


class JobLimits(c.Structure):
    _fields_ = [("basic", BasicLimits), ("io", c.c_ulonglong * 6),
                ("memory", c.c_size_t * 4)]


kernel = c.WinDLL("kernel32", use_last_error=True)
def bind(name, result, *args):
    method = getattr(kernel, name)
    method.argtypes, method.restype = args, result
    return method

create_job = bind("CreateJobObjectW", w.HANDLE, c.c_void_p, w.LPCWSTR)
set_job = bind("SetInformationJobObject", w.BOOL, w.HANDLE, c.c_int, c.c_void_p, w.DWORD)
attach = bind("AssignProcessToJobObject", w.BOOL, w.HANDLE, w.HANDLE)
close_handle = bind("CloseHandle", w.BOOL, w.HANDLE)

class LastInputInfo(c.Structure):
    _fields_ = [("size", w.UINT), ("tick", w.DWORD)]

get_last_input = c.WinDLL("user32", use_last_error=True).GetLastInputInfo
get_last_input.argtypes, get_last_input.restype = [c.POINTER(LastInputInfo)], w.BOOL

def session_input_tick():
    info = LastInputInfo(size=c.sizeof(LastInputInfo))
    return info.tick if get_last_input(c.byref(info)) else None


class Operation:
    def __init__(self):
        self.cancelled = threading.Event()
        self.reason = "client_cancelled"
        self._cancel_lock = threading.Lock()

    def cancel(self, reason="client_cancelled"):
        with self._cancel_lock:
            if not self.cancelled.is_set():
                self.reason = reason
                self.cancelled.set()

    def wait_before_click(self, milliseconds, requested, on_wait):
        """Return a receipt if the pending click must stop before any desktop effect."""
        first_input = session_input_tick()
        on_wait()
        if self.cancelled.wait(milliseconds / 1000):
            result = self.interrupted()
        else:
            last_input = session_input_tick()
            if first_input is not None and first_input == last_input:
                return None
            # Windows includes synthetic input in this marker. It does not identify
            # a particular person, button, or the reason the session input changed.
            reason = "session_input_unavailable" if None in (first_input, last_input) else "session_input_changed"
            result = dict(status="failed" if reason == "session_input_unavailable" else "cancelled",
                          reason=reason, effect="none", retry_safe=True)
        return dict(result, phase="waiting_before_click", requested_clicks=requested,
                    completed_clicks=0, click_in_flight=False)

    def interrupted(self, folder=None):
        result = {"status": "cancelled", "reason": self.reason, "effect": "none", "retry_safe": True}
        if folder and (folder / "started").exists():
            result.update(status="unknown", effect="possible", retry_safe=False)
            try:
                receipt = json.loads((folder / "receipt").read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                pass
            else:
                result.update(receipt, reason=self.reason, retry_safe=False)
        return result

    def run(self, command, request):
        if self.cancelled.is_set():
            return self.interrupted()
        with tempfile.TemporaryDirectory(prefix="wb-desktop-call-") as tmp:
            folder = Path(tmp)
            data = dict(request, cancel_path=str(folder / "cancel"), receipt_path=str(folder / "receipt"),
                        started_path=str(folder / "started"))
            job = create_job(None, None)
            if not job:
                raise c.WinError(c.get_last_error())
            proc = None
            try:
                limits = JobLimits()
                # Kill the helper on server exit. A user-opened Notepad and other
                # ordinary child applications must keep their own lifetime.
                limits.basic.flags = 0x2000 | 0x1000  # KILL_ON_JOB_CLOSE | SILENT_BREAKAWAY_OK
                if not set_job(job, 9, c.byref(limits), c.sizeof(limits)):
                    raise c.WinError(c.get_last_error())
                proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
                # The helper blocks on stdin until attachment succeeds.
                if not attach(job, int(proc._handle)):
                    raise c.WinError(c.get_last_error())
                if self.cancelled.is_set():
                    return self.interrupted()
                payload = json.dumps(data, ensure_ascii=False).encode()
                deadline = time.monotonic() + 30
                stopping = None
                while True:
                    if not self.cancelled.is_set() and time.monotonic() >= deadline:
                        self.cancel("timeout")
                    if self.cancelled.is_set() and stopping is None:
                        (folder / "cancel").touch()
                        stopping = time.monotonic()
                    if stopping is not None and time.monotonic() - stopping > .65:
                        proc.kill()
                        proc.communicate()
                        return self.interrupted(folder)
                    try:
                        stdout, _ = proc.communicate(payload, timeout=.045)
                        break
                    except subprocess.TimeoutExpired:
                        payload = None
                try:
                    reply = json.loads(stdout.decode("utf-8-sig"))
                except (UnicodeError, ValueError):
                    if self.cancelled.is_set() or (folder / "started").exists():
                        if not self.cancelled.is_set():
                            self.reason = "helper_disconnected"
                        return self.interrupted(folder)
                    raise RuntimeError("Desktop helper exited before returning a result.")
                if not reply.get("ok"):
                    if self.cancelled.is_set() or (folder / "started").exists():
                        if not self.cancelled.is_set():
                            self.reason = "action_interrupted"
                        return dict(self.interrupted(folder), detail=reply.get("error", "Action interrupted."))
                    raise ValueError(reply.get("error", "Desktop action was refused."))
                result = reply["result"]
                if self.cancelled.is_set():
                    result["cancel_requested"] = True
                    result["cancel_reason"] = self.reason
                return result
            finally:
                close_handle(job)
                if proc is not None:
                    if proc.poll() is None:
                        proc.kill()
                    proc.wait()
                    for stream in (proc.stdin, proc.stdout, proc.stderr):
                        stream.close()
