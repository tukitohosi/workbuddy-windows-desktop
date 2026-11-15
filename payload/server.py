"""Local MCP server for explicitly selected desktop windows. No third-party runtime dependencies."""
import json
from collections import OrderedDict
import hashlib
import os
from pathlib import Path
import queue
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parent
VERSION = "1.4.3"
sys.path.insert(0, str(ROOT))
from execution import Operation
POWERSHELL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
bindings = {}


OPTIONS = {"click_count": {"type":"integer","enum":[1,2]},
           "delay_before_ms":{"type":"integer","minimum":0,"maximum":20000,"description":"Optional cancellable wait before touching the desktop. New session input during the wait stops the click."},
           "target":{"type":"string","enum":["focused"]},
           "key":{"type":"string","enum":["Ctrl+L","Enter"]},
           "action":{"type":"string","enum":["query","minimize","restore","maximize"]},
           "operation_id":{"type":"string","maxLength":96,"description":"Optional unique ID to retrieve a receipt and prevent repeated effects on this connection."}}
def describe(name, description, fields, optional=()):
    props = {f: OPTIONS.get(f, {"type":"integer","minimum":0} if f in ("x","y") else {"type":"string"}) for f in (*fields,*optional)}
    return {"name":name, "description":description, "inputSchema":{
        "type":"object","properties":props,"required":list(fields),"additionalProperties":False}}


TOOLS = [
    describe("desktop_open_notepad", "Open a new visible empty Notepad document. Returns window_id.", (), ("operation_id",)),
    describe("desktop_select_window", "Bind a window by exact process name and title. Explorer supports explicit aliases Windows 桌面 and Windows 主任务栏. Returns window_id.", ("process_name", "exact_title")),
    describe("desktop_inspect", "Inspect visible controls, element_id, roles and client pixel centers. If minimized, restore and inspect again.", ("window_id",)),
    describe("desktop_move_mouse", "Visibly move the real Windows pointer to (x, y) in the selected window's client area. Use coordinates from desktop_inspect.", ("window_id", "x", "y"), ("operation_id",)),
    describe("desktop_click", f"Windows desktop control {VERSION}. Click once or double-click in one call (click_count=2). When the selected Windows desktop is in the background, a double-click on an exposed icon can activate it with the first click. In that case the connector verifies the icon at the point before each click. Other windows must become foreground first. Verify the application outcome before repeating a click.", ("window_id","x","y"), ("click_count","delay_before_ms","operation_id")),
    describe("desktop_type_text", "Append to the specified element_id or sole editor. target=focused writes at the confirmed selection. Check status and entered; never blindly replay partial or unknown writes.", ("window_id","text"), ("element_id","target","operation_id")),
    describe("desktop_read_text", "Read the selected editor by element_id, target=focused, or the sole editor.", ("window_id",), ("element_id","target")),
    describe("desktop_invoke", "Invoke a unique visible button using either element_id or its exact button_name.", ("window_id",), ("element_id","button_name","operation_id")),
    describe("desktop_window_state", "Query, minimize, restore or maximize the selected window. Returns the observed native window state.", ("window_id","action"), ("operation_id",)),
    describe("desktop_press_key", "Send Ctrl+L in a bound Chromium window or Enter to its verified focused target. Enter may submit; use only when intended.", ("window_id","key"), ("operation_id",)),
    describe("desktop_last_result", "Look up the last mutating operation or a specific operation_id on this connection. Check after cancellation, timeout or a lost response.", (), ("operation_id",)),
]
BY_NAME = {t["name"]: t for t in TOOLS}
PHASE = {"desktop_open_notepad": "open", "desktop_select_window": "select",
         "desktop_inspect": "inspect", "desktop_move_mouse": "move", "desktop_click": "click",
         "desktop_type_text": "type", "desktop_read_text": "read", "desktop_invoke": "invoke",
         "desktop_window_state":"state","desktop_press_key":"key"}


class StatusWindow:
    """Wait for the local indicator to become visible before doing desktop work."""
    def __init__(self):
        self.process = None
        self.sequence = 0

    @staticmethod
    def collect(stream, messages):
        try:
            for line in stream:
                messages.put(json.loads(line))
        except (OSError, ValueError):
            pass
        finally:
            messages.put(None)

    def receive(self):
        try:
            message = self.messages.get(timeout=6)
        except queue.Empty:
            message = None
        if not isinstance(message, dict):
            raise RuntimeError("The WorkBuddy desktop indicator is unavailable. No further desktop action was issued.")
        return message

    def send(self, event, phase=None):
        self.sequence += 1
        msg = {"action": event, "seq": self.sequence}
        if phase:
            msg["phase"] = phase
        self.process.stdin.write(json.dumps(msg).encode("utf-8") + b"\n")
        self.process.stdin.flush()
        reply = self.receive()
        if reply.get("seq") != self.sequence or not reply.get("ok") or (event == "begin" and not reply.get("visible")):
            raise RuntimeError("Unable to confirm the state of the WorkBuddy desktop indicator.")

    def begin(self, phase):
        try:
            if self.process is None or self.process.poll() is not None:
                self.stop()
                self.messages = queue.Queue()
                self.process = subprocess.Popen(
                    [sys.executable, "-I", "-B", "-u", str(ROOT / "status_overlay.py")],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                threading.Thread(target=self.collect, args=(self.process.stdout, self.messages), daemon=True).start()
                if not self.receive().get("ready"):
                    raise RuntimeError("Could not start the WorkBuddy desktop indicator.")
            self.send("begin", phase)
        except (RuntimeError, OSError):
            self.stop()
            raise

    def stop(self):
        proc, self.process = self.process, None
        if proc is None:
            return
        try:
            proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        proc.stdout.close()

    def end(self, completed_phase=None):
        try:
            self.send("end", completed_phase)
        except (RuntimeError, OSError):
            # The action has already run. Avoid suggesting that the client repeat it.
            self.stop()


indicator = StatusWindow()


def check_args(name, args):
    if name not in BY_NAME or not isinstance(args, dict):
        raise ValueError("Unknown tool or invalid arguments.")
    schema = BY_NAME[name]["inputSchema"]
    if set(schema["required"]) - args.keys() or args.keys() - schema["properties"].keys():
        raise ValueError("Missing or unrecognized tool arguments.")
    for field, value in args.items():
        spec = schema["properties"][field]
        if spec["type"] == "integer":
            if type(value) is not int or not 0 <= value <= spec.get("maximum",2**31-1):
                raise ValueError(f"Expected an integer between 0 and {spec.get('maximum',2**31-1)} for {field}.")
        elif not isinstance(value,str) or not value or len(value)>spec.get("maxLength",100000):
            raise ValueError("Invalid text argument: " + field)
        if "enum" in spec and value not in spec["enum"]:
            raise ValueError("Unsupported value for " + field)
    if len(args.get("text","").encode("utf-16-le")) > 20000:
        raise ValueError("Limit: 10,000 UTF-16 units per call.")
    if "element_id" in args and "target" in args:
        raise ValueError("Choose an element_id or the confirmed focus.")
    if name == "desktop_invoke" and ("button_name" in args) == ("element_id" in args):
        raise ValueError("Specify one button_name or element_id.")
    if "window_id" in args and args["window_id"] not in bindings:
        raise ValueError("Unknown window_id. Open or select the window again on this connection.")


def perform(name, args, operation):
    payload = dict(args)
    payload.pop("operation_id",None)
    payload.pop("delay_before_ms",None)
    if "window_id" in payload:
        payload["binding"] = bindings[payload.pop("window_id")]
    if name == "desktop_window_state":
        payload["state_action"] = payload.pop("action")
    phase = PHASE[name]
    if operation.cancelled.is_set():
        return operation.interrupted()
    indicator.begin(phase)
    completed = None
    try:
        command = [str(POWERSHELL),"-NoProfile","-NonInteractive","-STA","-ExecutionPolicy","Bypass",
                   "-File",str(ROOT/"desktop.ps1")]
        result = operation.run(command, dict(payload,action=name))
        if "binding" in result:
            token = secrets.token_hex(12)
            bindings[token] = result.pop("binding")
            result["window_id"] = token
        if result.get("status", "completed") == "completed":
            completed = phase
        return result
    finally:
        indicator.end(completed)


def tool_result(value, error=False):
    return {"isError": error, "content":[{"type":"text","text":json.dumps(value,ensure_ascii=False)}]}

class ProtocolObserver:
    """Opt-in, metadata-only observation of specifically identified local acceptance clicks."""
    pattern = re.compile(r"wb141-([0-9a-f]{8})-[a-zA-Z0-9-]{1,64}\Z")
    receipt_fields = ("status","reason","cancel_reason","phase","effect","retry_safe","requested_clicks",
                      "completed_clicks","cancel_requested","click_in_flight","activation_method")

    def __init__(self):
        self.requests = OrderedDict()
        self.filename = "protocol-%s-%s.jsonl" % (os.getpid(), secrets.token_hex(4))
        self.lock = threading.Lock()

    def register(self, req_id, name, token):
        match = self.pattern.fullmatch(token) if name == "desktop_click" and token else None
        if not match:
            return
        folder = Path(tempfile.gettempdir()) / ("wb-desktop-acceptance-" + match[1])
        if (folder / "armed").is_file():
            with self.lock:
                if len(self.requests) >= 256:
                    self.requests.popitem(last=False)
                self.requests[req_id] = (folder, token)

    def forget(self, req_id):
        with self.lock:
            self.requests.pop(req_id, None)

    def event(self, req_id, event, **fields):
        with self.lock:
            item = self.requests.get(req_id)
            if item:
                folder, token = item
                self._write(folder, event, operation_id=token, **fields)

    def closed(self, cause):
        with self.lock:
            for folder in {item[0] for item in self.requests.values()}:
                self._write(folder,"transport_closed",cause=cause)

    def _write(self, folder, event, **fields):
        try:
            if (folder / "armed").is_file():
                line = dict(time_ns=time.time_ns(), monotonic_ns=time.monotonic_ns(), pid=os.getpid(),
                            version=VERSION, event=event, **fields)
                with (folder / self.filename).open("a",encoding="utf-8") as stream:
                    stream.write(json.dumps(line,separators=(",",":"))+"\n")
        except OSError:
            pass  # Diagnostic recording must never hold up subsequent actions or cancellation.


class Server:
    def __init__(self):
        self.lock = threading.RLock()
        self.output_lock = threading.Lock()
        self.calls = {}
        self.history = OrderedDict()
        self.work = queue.Queue()
        self.closed = False
        self.observer = ProtocolObserver()

    def write(self, req_id, result=None, error=None):
        msg = dict(jsonrpc="2.0", id=req_id)
        if error:
            msg["error"] = error
        else:
            msg["result"] = result
        with self.output_lock:
            if not self.closed:
                sys.stdout.buffer.write(json.dumps(msg,ensure_ascii=False).encode()+b"\n")
                sys.stdout.buffer.flush()

    def read_receipt(self, key):
        with self.lock:
            if key is None:
                key = next(reversed(self.history),None)
            record = self.history.get(key)
            return record[1].copy() if record else {"status":"not_found","scope":"this_connection"}

    def enqueue(self, req_id, name, args):
        with self.lock:
            if req_id in self.calls:
                raise ValueError("Duplicate active request id.")
            if len(self.calls) >= 32:
                raise ValueError("Too many pending desktop actions.")
            operation = Operation()
            token = None
            mutating = name not in ("desktop_select_window","desktop_read_text","desktop_inspect") and not (
                name == "desktop_window_state" and args["action"] == "query")
            if mutating:
                token = args.get("operation_id") or secrets.token_hex(12)
                self.observer.register(req_id,name,token)
                digest = hashlib.sha256(json.dumps([name,args],sort_keys=True,ensure_ascii=True).encode()).digest()
                if token in self.history:
                    existing, receipt = self.history[token]
                    if digest != existing:
                        raise ValueError("This operation_id already belongs to a different action.")
                    self.observer.event(req_id,"replayed",status=receipt["status"])
                    self.write(req_id,tool_result(dict(receipt,replayed=True),
                               receipt["status"] not in ("completed","pending")))
                    return
                if len(self.history) >= 256:
                    oldest = next((k for k,(_,r) in self.history.items() if r["status"]!="pending"),None)
                    if oldest is not None:
                        del self.history[oldest]
                self.history[token] = (digest,dict(status="pending",tool=name,operation_id=token))
            self.calls[req_id] = operation
            self.observer.event(req_id,"queued")
            self.work.put((req_id,name,args,operation,token))

    def worker(self):
        while True:
            item = self.work.get()
            if item is None:
                return
            req_id,name,args,operation,token = item
            try:
                value = None
                delay = args.get("delay_before_ms",0)
                if delay:
                    value = operation.wait_before_click(delay,args.get("click_count",1),
                        lambda:self.observer.event(req_id,"waiting_before_click",delay_before_ms=delay))
                if value is None:
                    self.observer.event(req_id,"dispatched")
                    value = perform(name,args,operation)
                value.setdefault("status","completed")
                if name=="desktop_click" and value["status"]=="cancelled" and value.get("effect")=="none":
                    value.setdefault("requested_clicks",args.get("click_count",1))
                    value.setdefault("completed_clicks",0)
                    value.setdefault("click_in_flight",False)
            except Exception as exc:
                value = {"status":"failed","detail":str(exc)}
            with self.lock:
                if token:
                    value["operation_id"] = token
                    self.history[token] = (self.history[token][0],dict(value,tool=name))
                self.observer.event(req_id,"finished",**{k:value[k] for k in self.observer.receipt_fields if k in value})
                self.calls.pop(req_id,None)
            try:
                self.write(req_id,tool_result(value,value["status"] not in ("completed","ok")))
            except (OSError,ValueError):
                self.disconnect("stdout_broken")

    def disconnect(self, cause="stdin_eof"):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            for req_id,operation in self.calls.items():
                operation.cancel("client_disconnected")
                self.observer.event(req_id,"disconnect_during_request",cause=cause)
            self.observer.closed(cause)

    def dispatch(self, msg):
        if not isinstance(msg,dict):
            return
        method,params,req_id = msg.get("method"),msg.get("params",{}),msg.get("id")
        if not isinstance(params,dict) or (req_id is not None and type(req_id) not in (str,int)):
            return
        if req_id is None:
            if method == "notifications/cancelled" and type(params.get("requestId")) in (str,int):
                with self.lock:
                    op = self.calls.get(params["requestId"])
                    if op: op.cancel()
                    self.observer.event(params["requestId"], "cancel_notification", matched="active" if op else "finished")
            return
        with self.lock:
            if req_id not in self.calls:
                self.observer.forget(req_id)
        if method == "initialize":
            versions = ("2024-11-05","2025-03-26","2025-06-18","2025-11-25")
            version = params.get("protocolVersion")
            result = {"protocolVersion":version if version in versions else "2025-06-18",
                      "serverInfo":{"name":"workbuddy-windows-desktop","version":VERSION},"capabilities":{"tools":{}}}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools":TOOLS}
        elif method == "tools/call":
            name,args = params.get("name"),params.get("arguments",{})
            try:
                check_args(name,args)
                if name != "desktop_last_result":
                    self.enqueue(req_id,name,args)
                    return
                result = tool_result(self.read_receipt(args.get("operation_id")))
            except (ValueError,TypeError) as exc:
                result = tool_result({"status":"rejected","effect":"none","detail":str(exc)},True)
        else:
            self.write(req_id,error={"code":-32601,"message":"Method not found"})
            return
        self.write(req_id,result)

    def run(self):
        worker = threading.Thread(target=self.worker)
        worker.start()
        try:
            for line in sys.stdin.buffer:
                try:
                    self.dispatch(json.loads(line))
                except (UnicodeError,ValueError):
                    self.write(None,error={"code":-32700,"message":"Invalid JSON"})
        finally:
            self.disconnect()
            self.work.put(None)
            worker.join()
            indicator.stop()


if __name__ == "__main__":
    Server().run()


