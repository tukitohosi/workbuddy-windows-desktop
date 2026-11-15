"""Nonactivating Windows activity indicator. Only accepts commands on inherited stdin."""
import ctypes as c
from ctypes import wintypes as w
import json
from pathlib import Path
from queue import Empty, Queue
import sys
from threading import Thread
from time import monotonic

# The connector uses python -I. Load only its adjacent installed effect modules.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from edge_glow import EdgeGlow
from pointer_effects import PointerEffect


TITLE = "WorkBuddy 正在使用电脑"
CLASS = "WorkBuddyDesktopControlStatus"
PHASES = {"open": "打开记事本", "select": "选择窗口", "inspect": "查看窗口",
          "type": "输入文字", "read": "读取文字", "invoke": "操作按钮",
          "move": "移动鼠标", "click": "点击鼠标", "key": "按下按键", "state": "窗口状态"}
DWELL_SECONDS = 1.8
HARD_LIMIT_SECONDS = 45
WM_DESTROY, WM_PAINT, WM_TIMER, WM_NCHITTEST, WM_MOUSEACTIVATE = 2, 15, 275, 132, 33
LRESULT = c.c_ssize_t
WNDPROC = c.WINFUNCTYPE(LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)


class WindowClass(c.Structure):
    _fields_ = [("style", w.UINT), ("proc", WNDPROC), ("classExtra", c.c_int), ("winExtra", c.c_int),
                ("instance", w.HINSTANCE), ("icon", w.HANDLE), ("cursor", w.HANDLE), ("bg", w.HBRUSH),
                ("menu", w.LPCWSTR), ("name", w.LPCWSTR)]


class MonitorInfo(c.Structure):
    _fields_ = [("size", w.DWORD), ("bounds", w.RECT), ("work", w.RECT), ("flags", w.DWORD)]


def bind(dll, name, result, *args):
    call = getattr(dll, name)
    call.restype, call.argtypes = result, args
    return call


user = c.WinDLL("user32", use_last_error=True)
kernel = c.WinDLL("kernel32", use_last_error=True)
gdi = c.WinDLL("gdi32", use_last_error=True)
W, I, U, H, P, S = w.HWND, c.c_int, w.UINT, w.HANDLE, c.c_void_p, w.LPCWSTR
module = bind(kernel, "GetModuleHandleW", H, S)
register = bind(user, "RegisterClassW", w.ATOM, c.POINTER(WindowClass))
create = bind(user, "CreateWindowExW", W, w.DWORD, S, S, w.DWORD, I, I, I, I, W, H, H, P)
position = bind(user, "SetWindowPos", w.BOOL, W, W, I, I, I, I, U)
show = bind(user, "ShowWindow", w.BOOL, W, I)
is_visible = bind(user, "IsWindowVisible", w.BOOL, W)
destroy = bind(user, "DestroyWindow", w.BOOL, W)
paint_now = bind(user, "UpdateWindow", w.BOOL, W)
set_text = bind(user, "SetWindowTextW", w.BOOL, W, S)
default_proc = bind(user, "DefWindowProcW", LRESULT, W, U, w.WPARAM, w.LPARAM)
post_quit = bind(user, "PostQuitMessage", None, I)
set_timer = bind(user, "SetTimer", c.c_size_t, W, c.c_size_t, U, P)
get_msg = bind(user, "GetMessageW", I, c.POINTER(w.MSG), W, U, U)
dispatch = bind(user, "DispatchMessageW", LRESULT, c.POINTER(w.MSG))
send = bind(user, "SendMessageW", LRESULT, W, U, w.WPARAM, w.LPARAM)
foreground = bind(user, "GetForegroundWindow", W)
monitor = bind(user, "MonitorFromWindow", H, W, w.DWORD)
monitor_at = bind(user, "MonitorFromPoint", H, w.POINT, w.DWORD)
cursor_at = bind(user, "GetCursorPos", w.BOOL, c.POINTER(w.POINT))
monitor_info = bind(user, "GetMonitorInfoW", w.BOOL, H, c.POINTER(MonitorInfo))
dpi_for_window = bind(user, "GetDpiForWindow", U, W) if hasattr(user, "GetDpiForWindow") else None
dpi_for_monitor = bind(c.WinDLL("shcore"), "GetDpiForMonitor", c.c_long, H, I, c.POINTER(U), c.POINTER(U))
create_font = bind(gdi, "CreateFontW", H, I, I, I, I, I, w.DWORD, w.DWORD, w.DWORD,
                   w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.DWORD, S)
delete_gdi = bind(gdi, "DeleteObject", w.BOOL, H)
create_brush = bind(gdi, "CreateSolidBrush", H, w.DWORD)
set_text_color = bind(gdi, "SetTextColor", w.DWORD, H, w.DWORD)
set_bg_color = bind(gdi, "SetBkColor", w.DWORD, H, w.DWORD)
round_region = bind(gdi, "CreateRoundRectRgn", H, I, I, I, I, I, I)
set_region = bind(user, "SetWindowRgn", I, W, H, w.BOOL)
acquire_dc = bind(user, "GetDC", H, W)
release_dc = bind(user, "ReleaseDC", I, W, H)
select_object = bind(gdi, "SelectObject", H, H, H)
extent = bind(gdi, "GetTextExtentPoint32W", w.BOOL, H, S, I, c.POINTER(w.SIZE))


def reply(**values):
    sys.stdout.buffer.write(json.dumps(values, ensure_ascii=True).encode("ascii") + b"\n")
    sys.stdout.buffer.flush()


def inbox(queue):
    try:
        # Do not hold Python's global buffered stdin lock at interpreter shutdown.
        # A shutdown request can arrive while the parent still owns its pipe writer.
        with open(sys.stdin.fileno(), "rb", buffering=0, closefd=False) as pipe:
            for raw in pipe:
                try:
                    msg = json.loads(raw)
                    queue.put(msg if isinstance(msg, dict) else {})
                except (ValueError, UnicodeError, RecursionError):
                    queue.put({})
    finally:
        queue.put(None)


class Overlay:
    def __init__(self):
        self.queue = Queue()
        self.deadline = 0
        self.scale = None
        self.layout_key = None
        self.phase = None
        self.cursor_deadline = 0
        self.cursor_running = False
        self.edge = EdgeGlow()
        self.cursor = PointerEffect()
        self.fonts = []
        self.bg = 0x282421
        self.brush = create_brush(self.bg)
        self.window_proc = WNDPROC(self.process)
        instance = module(None)
        wc = WindowClass(proc=self.window_proc, instance=instance, bg=self.brush, name=CLASS)
        if not register(c.byref(wc)):
            raise c.WinError(c.get_last_error())
        # Layered + transparent forwards mouse input across process boundaries.
        # TOOLWINDOW and NOACTIVATE keep the banner out of Alt+Tab and preserve focus.
        ex_style = 0x80000 | 0x20 | 0x80 | 0x08000000 | 0x8
        self.hwnd = create(ex_style, CLASS, TITLE, 0x88000000, 0, 0, 1, 1, None, None, instance, None)
        if not self.hwnd:
            raise c.WinError(c.get_last_error())
        alpha = bind(user, "SetLayeredWindowAttributes", w.BOOL, W, w.DWORD, w.BYTE, w.DWORD)
        if not alpha(self.hwnd, 0, 255, 2):
            raise c.WinError(c.get_last_error())
        self.labels = [create(0, "STATIC", text, 0x50000200, 0, 0, 1, 1,
                              self.hwnd, None, instance, None) for text in ("●", TITLE, "")]
        if not all(self.labels) or not set_timer(self.hwnd, 1, 32, None):
            raise c.WinError(c.get_last_error())

    def measure(self, texts):
        dc = acquire_dc(self.hwnd)
        if not dc:
            raise c.WinError(c.get_last_error())
        widths = []
        try:
            for text, font in zip(texts, self.fonts):
                prior = select_object(dc, font)
                try:
                    size = w.SIZE()
                    if not extent(dc, text, len(text), c.byref(size)):
                        raise c.WinError(c.get_last_error())
                    widths.append(size.cx + 1)
                finally:
                    select_object(dc, prior)
        finally:
            release_dc(self.hwnd, dc)
        return widths

    def layout(self, phase):
        fg = foreground()
        info = MonitorInfo(size=c.sizeof(MonitorInfo))
        point = w.POINT()
        if phase in ("move", "click") and cursor_at(c.byref(point)):
            target = monitor_at(point, 2)  # nearest physical display
        else:
            target = monitor(fg, 1)
        if not monitor_info(target, c.byref(info)):
            raise c.WinError(c.get_last_error())
        dx, dy = U(), U()
        if dpi_for_monitor(target, 0, c.byref(dx), c.byref(dy)) == 0 and dx.value:
            scale = dx.value / 96
        else:
            scale = ((dpi_for_window(fg) if dpi_for_window and fg else 96) or 96) / 96
        bounds = (info.bounds.left, info.bounds.top, info.bounds.right, info.bounds.bottom)
        work = (info.work.left, info.work.top, info.work.right, info.work.bottom)
        key = (bounds, work, scale, phase)
        if key == self.layout_key:
            return
        self.edge.display(bounds, scale)
        def px(n):
            return round(n * scale)
        if self.scale != scale:
            new_fonts = [create_font(-px(size), 0, 0, 0, weight, 0, 0, 0, 1, 0, 0, 5, 0,
                                     "Microsoft YaHei UI") for size, weight in ((12, 400), (15, 600), (13, 400))]
            if not all(new_fonts):
                raise c.WinError(c.get_last_error())
            for label, font in zip(self.labels, new_fonts):
                send(label, 0x30, font, 1)  # WM_SETFONT
            for old in self.fonts:
                delete_gdi(old)
            self.scale, self.fonts = scale, new_fonts
        if not set_text(self.labels[2], PHASES[phase]):
            raise c.WinError(c.get_last_error())
        widths = self.measure(("●", TITLE, PHASES[phase]))
        height = px(36)
        offset = px(15)
        for label, label_width, gap in zip(self.labels, widths, (8, 12, 15)):
            if not position(label, None, offset, 0, label_width, height, 0x14):
                raise c.WinError(c.get_last_error())
            offset += label_width + px(gap)
        width = min(offset, info.work.right - info.work.left)
        x = info.work.left + (info.work.right - info.work.left - width) // 2
        y = info.work.top + px(13)
        region = round_region(0, 0, width+1, height+1, height, height)
        if not region or not set_region(self.hwnd, region, True):
            if region:
                delete_gdi(region)
            raise c.WinError(c.get_last_error())
        if not position(self.hwnd, W(-1), x, y, width, height, 0x50):  # NOACTIVATE | SHOWWINDOW
            raise c.WinError(c.get_last_error())
        paint_now(self.hwnd)
        for label in self.labels:
            paint_now(label)
        if not is_visible(self.hwnd):
            raise RuntimeError("Status window could not be shown.")
        self.layout_key = key

    def display(self, phase):
        self.layout(phase)
        self.cursor.begin(phase)
        self.cursor_running = phase in ("move", "click")
        self.cursor_deadline = 0
        self.phase = phase
        self.deadline = monotonic() + HARD_LIMIT_SECONDS

    def hide(self):
        self.cursor.end()
        self.edge.hide()
        show(self.hwnd, 0)
        self.phase = self.layout_key = None
        self.cursor_running = False
        self.deadline = self.cursor_deadline = 0

    def tick(self, hwnd):
        try:
            while True:
                item = self.queue.get_nowait()
                if item is None:
                    destroy(hwnd)
                    return
                seq = item.get("seq")
                action = item.get("action")
                if type(seq) is not int:
                    reply(seq=None, ok=False, error="Integer seq required.")
                    continue
                if action in ("begin", "update") and item.get("phase") in PHASES:
                    self.display(item["phase"])
                elif action == "end":
                    if self.phase == "click" and item.get("phase") == "click":
                        self.cursor.pulse_click()
                    self.deadline = monotonic() + DWELL_SECONDS
                    self.cursor_deadline = monotonic() + 0.55
                elif action == "shutdown":
                    self.hide()
                    reply(seq=seq, ok=True, visible=False)
                    destroy(hwnd)
                    return
                else:
                    reply(seq=seq, ok=False, error="Unknown command or phase.")
                    continue
                reply(seq=seq, ok=True, visible=bool(is_visible(hwnd)))
        except Empty:
            pass
        except (OSError, RuntimeError, TypeError) as error:
            self.hide()
            if isinstance(error, (BrokenPipeError, OSError)) and getattr(error, "errno", None) in (22, 32):
                destroy(hwnd)
                return
            reply(seq=seq, ok=False, error="Status display failed.")
        if self.deadline and monotonic() >= self.deadline:
            self.hide()
        elif self.phase:
            try:
                self.layout(self.phase)
                self.edge.tick(monotonic(), self.deadline)
                if self.cursor_running:
                    if self.cursor_deadline and monotonic() >= self.cursor_deadline:
                        self.cursor.end()
                        self.cursor_running = False
                    else:
                        self.cursor.tick()
            except (OSError, RuntimeError):
                # The next command obtains geometry again after a display-change race.
                self.layout_key = None

    def process(self, hwnd, message, wp, lp):
        if message == WM_TIMER:
            self.tick(hwnd)
            return 0
        if message == 0x138:  # WM_CTLCOLORSTATIC
            labels = getattr(self, "labels", ())
            colors = (0xFFC091, 0xFAF8F7, 0xCCC4BF)
            set_text_color(wp, colors[labels.index(lp)] if lp in labels else 0xFAF8F7)
            set_bg_color(wp, self.bg)
            return self.brush
        if message == WM_NCHITTEST:
            return -1  # HTTRANSPARENT
        if message == WM_MOUSEACTIVATE:
            return 3  # MA_NOACTIVATE
        if message == WM_DESTROY:
            post_quit(0)
            return 0
        return default_proc(hwnd, message, wp, lp)

    def run(self):
        Thread(target=inbox, args=(self.queue,), daemon=True).start()
        reply(ready=True)
        msg = w.MSG()
        try:
            while (result := get_msg(c.byref(msg), None, 0, 0)) > 0:
                dispatch(c.byref(msg))
        finally:
            self.cursor.close()
            self.edge.close()
            for font in self.fonts:
                delete_gdi(font)
        if result < 0:
            raise c.WinError(c.get_last_error())


if __name__ == "__main__":
    if hasattr(user, "SetProcessDpiAwarenessContext"):
        bind(user, "SetProcessDpiAwarenessContext", w.BOOL, H)(H(-4))
    Overlay().run()
