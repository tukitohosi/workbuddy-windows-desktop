"""Click-through pointer highlight. This module never replaces or hides a system cursor."""
import ctypes as c
from ctypes import wintypes as w
import math
from functools import lru_cache
from time import monotonic


CLASS = "WorkBuddyDesktopPointerEffect"
TITLE = "WorkBuddy 鼠标指针"
W, H, I, U, P = w.HWND, w.HANDLE, c.c_int, w.UINT, c.c_void_p
LRESULT = c.c_ssize_t
WNDPROC = c.WINFUNCTYPE(LRESULT, W, U, w.WPARAM, w.LPARAM)
user = c.WinDLL("user32", use_last_error=True)
gdi = c.WinDLL("gdi32", use_last_error=True)
kernel = c.WinDLL("kernel32", use_last_error=True)


class WindowClass(c.Structure):
    _fields_ = [("style", U), ("proc", WNDPROC), ("class_extra", I), ("window_extra", I),
                ("instance", H), ("icon", H), ("cursor", H), ("bg", H),
                ("menu", w.LPCWSTR), ("name", w.LPCWSTR)]


class BitmapHeader(c.Structure):
    _fields_ = [("size", w.DWORD), ("width", w.LONG), ("height", w.LONG),
                ("planes", w.WORD), ("bpp", w.WORD), ("compression", w.DWORD),
                ("image_size", w.DWORD), ("res_x", w.LONG), ("res_y", w.LONG),
                ("colors", w.DWORD), ("important", w.DWORD)]


class Blend(c.Structure):
    _fields_ = [("op", w.BYTE), ("flags", w.BYTE), ("alpha", w.BYTE), ("format", w.BYTE)]


def api(dll, name, result, *args):
    fn = getattr(dll, name)
    fn.restype, fn.argtypes = result, args
    return fn


module = api(kernel, "GetModuleHandleW", H, w.LPCWSTR)
register = api(user, "RegisterClassW", w.ATOM, c.POINTER(WindowClass))
create = api(user, "CreateWindowExW", W, w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
             I, I, I, I, W, H, H, P)
default_proc = api(user, "DefWindowProcW", LRESULT, W, U, w.WPARAM, w.LPARAM)
position = api(user, "SetWindowPos", w.BOOL, W, W, I, I, I, I, U)
show = api(user, "ShowWindow", w.BOOL, W, I)
destroy = api(user, "DestroyWindow", w.BOOL, W)
visible = api(user, "IsWindowVisible", w.BOOL, W)
cursor_pos = api(user, "GetPhysicalCursorPos", w.BOOL, c.POINTER(w.POINT))
remove = api(gdi, "DeleteObject", w.BOOL, H)
get_monitor = api(user, "MonitorFromPoint", H, w.POINT, w.DWORD)
monitor_dpi = api(c.WinDLL("shcore"), "GetDpiForMonitor", w.LONG, H, I, c.POINTER(U), c.POINTER(U))
make_dc = api(gdi, "CreateCompatibleDC", H, H)
drop_dc = api(gdi, "DeleteDC", w.BOOL, H)
select = api(gdi, "SelectObject", H, H, H)
make_dib = api(gdi, "CreateDIBSection", H, H, c.POINTER(BitmapHeader), U, c.POINTER(P), H, w.DWORD)
layer = api(user, "UpdateLayeredWindow", w.BOOL, W, H, c.POINTER(w.POINT), c.POINTER(w.SIZE),
            H, c.POINTER(w.POINT), w.DWORD, c.POINTER(Blend), w.DWORD)


@WNDPROC
def _proc(hwnd, msg, wp, lp):
    if msg == 0x84:  # WM_NCHITTEST
        return -1
    if msg == 0x21:  # WM_MOUSEACTIVATE
        return 3
    return default_proc(hwnd, msg, wp, lp)


# Small rounded pointer, in physical-pixel independent coordinates relative to
# the real hotspot. The inward curve on its lower side reads at 1x without the
# rectangular tail used by a standard Windows pointer.
def _arrow_path():
    path = [(0.0, 1.1)]
    def curve(control, end):
        start = path[-1]
        for i in range(1, 6):
            t = i / 5
            u = 1 - t
            path.append((u*u*start[0] + 2*u*t*control[0] + t*t*end[0],
                         u*u*start[1] + 2*u*t*control[1] + t*t*end[1]))
    curve((-.3, -.55), (1.35, .03))
    path.append((15.9, 6.6))
    curve((17.75, 7.55), (15.8, 8.45))
    path.append((10.65, 9.9))
    curve((9.85, 10.1), (9.45, 10.9))
    path.append((7.25, 16.0))
    curve((6.35, 17.8), (5.5, 15.85))
    path.append((0.0, 1.1))
    return path


PATH = _arrow_path()
FOG_RGB = (94, 142, 240)
INK_RGB = (27, 29, 34)
WHITE_RGB = (252, 253, 255)


@lru_cache(maxsize=7)
def _arrow_sprite(scale):
    # Scan-convert the small vector at 4x. The white contour is a dilation of
    # the same shape, and a separable box blur gives its shadow a soft edge.
    ss = 4
    lo, hi = -math.ceil(5*scale), math.ceil(22*scale)
    width = (hi-lo)*ss
    p = [((x*scale-lo)*ss, (y*scale-lo)*ss) for x, y in PATH]
    edges = list(zip(p, p[1:]))
    mask = bytearray(width*width)
    for y in range(width):
        scan = y+.5
        hits = sorted(x1+(scan-y1)*(x2-x1)/(y2-y1) for (x1,y1),(x2,y2) in edges
                      if min(y1,y2) <= scan < max(y1,y2))
        for a,b in zip(hits[::2],hits[1::2]):
            start, end = max(0,math.ceil(a-.5)), min(width,math.ceil(b-.5))
            mask[y*width+start:y*width+end] = bytes([1])*(end-start)
    # Smooth rounded outline generated from scanline intervals, not a second
    # independently drawn pointer. All mask computations stay inside the sprite.
    radius = max(1, round(1.15*scale*ss))
    outer = bytearray(len(mask))
    for y in range(width):
        row = mask[y*width:(y+1)*width]
        start = row.find(1)
        if start < 0:
            continue
        end = row.rfind(1)+1
        for dy in range(-radius,radius+1):
            yy=y+dy
            if not 0 <= yy < width:
                continue
            extent=math.isqrt(radius*radius-dy*dy)
            left,right=max(0,start-extent),min(width,end+extent)
            outer[yy*width+left:yy*width+right]=bytes([1])*(right-left)
    def coverage(bitmap):
        size = width//ss
        return [sum(sum(bitmap[(y*ss+dy)*width+x*ss:(y*ss+dy)*width+x*ss+ss]) for dy in range(ss))/(ss*ss)
                for y in range(size) for x in range(size)]
    inside,edge = coverage(mask),coverage(outer)
    size=width//ss
    # A short Gaussian kernel at native output resolution is enough at cursor size.
    sigma=.85*scale
    radius=math.ceil(sigma*2.7)
    weights=[math.exp(-i*i/(2*sigma*sigma)) for i in range(-radius,radius+1)]
    total=sum(weights)
    weights=[v/total for v in weights]
    def blur(values, vertical):
        blurred=[]
        for y in range(size):
            for x in range(size):
                if vertical:
                    val=sum(v*values[yy*size+x] for i,v in enumerate(weights) if 0 <= (yy:=y+i-radius) < size)
                else:
                    val=sum(v*values[y*size+xx] for i,v in enumerate(weights) if 0 <= (xx:=x+i-radius) < size)
                blurred.append(val)
        return blurred
    shadow=blur(blur(edge,False),True)
    offset=max(1,round(1.15*scale))
    points=[]
    for y in range(size):
        for x in range(size):
            i=y*size+x
            black,white=inside[i],max(0.,edge[i]-inside[i])
            shade=shadow[(y-offset)*size+x]*.22*(1-edge[i]) if y>=offset else 0.
            if black or white or shade > .002:
                # Premultiplied normalized coverage. Shadow is near-neutral ink.
                alpha=black+white+shade
                rgb=tuple(black*k+white*v+shade*d for k,v,d in zip(INK_RGB,WHITE_RGB,(18,26,45)))
                points.append((lo+x,lo+y,alpha,rgb))
    return points


@lru_cache(maxsize=18)
def _pixels(scale, strength=0):
    """Return a premultiplied BGRA dib. strength is a discrete click-highlight level (0..3)."""
    # Cornflower-blue mist around the point, Gaussian throughout with no rim.
    hot=math.ceil(55*scale)
    side=2*hot+1
    data=bytearray(side*side*4)
    sigma=(13.7+strength*.86)*scale
    peak=(.345+strength*.018)*255
    lut=[bytes(((FOG_RGB[2]*a+127)//255,(FOG_RGB[1]*a+127)//255,(FOG_RGB[0]*a+127)//255,a))
         for a in range(256)]
    gaussian=[math.exp(-((i-hot)/sigma)**2*.5) for i in range(side)]
    for y, g in enumerate(gaussian):
        gain=peak*g
        row=b"".join(lut[round(gain*v)] for v in gaussian)
        data[(y*side)*4:((y+1)*side)*4]=row
    for x,y,alpha,rgb in _arrow_sprite(scale):
        i=((y+hot)*side+x+hot)*4
        transparent=1-alpha
        for ch,color in enumerate(reversed(rgb)):
            data[i+ch]=max(0,min(255,round(color + data[i+ch]*transparent)))
        data[i+3]=max(0,min(255,round(255*alpha + data[i+3]*transparent)))
    return side,hot,bytes(data)


class PointerEffect:
    """Call from the overlay GUI thread. No HWND is created until the first pointer action."""
    def __init__(self):
        self.hwnd = None
        self.phase = None
        self._pulse_start = None
        self._monitor = None
        self._dpi = 96
        self._shape = self._location = None
        self._side = self._hot = 0

    def _window(self):
        if self.hwnd:
            return
        inst = module(None)
        wc = WindowClass(proc=_proc, instance=inst, name=CLASS)
        if not register(c.byref(wc)) and c.get_last_error() != 1410:  # class already registered
            raise c.WinError(c.get_last_error())
        # LAYERED | TRANSPARENT | TOPMOST | TOOLWINDOW | NOACTIVATE. WS_DISABLED
        # makes WindowFromPoint ignore this window, including across process boundaries.
        self.hwnd = create(0x080800A8, CLASS, TITLE, 0x88000000, 0, 0, 1, 1, None, None, inst, None)
        if not self.hwnd:
            raise c.WinError(c.get_last_error())

    def _paint(self, point, scale, strength):
        side, hot, pixels = _pixels(scale, strength)
        dc = make_dc(None)
        if not dc:
            raise c.WinError(c.get_last_error())
        bitmap = old = None
        try:
            header = BitmapHeader(size=c.sizeof(BitmapHeader), width=side, height=-side, planes=1, bpp=32)
            bits = P()
            bitmap = make_dib(dc, c.byref(header), 0, c.byref(bits), None, 0)
            if not bitmap or not bits:
                raise c.WinError(c.get_last_error())
            c.memmove(bits, pixels, len(pixels))
            old = select(dc, bitmap)
            if not old:
                raise c.WinError(c.get_last_error())
            dst, source = w.POINT(point.x - hot, point.y - hot), w.POINT()
            sz, blend = w.SIZE(side, side), Blend(0, 0, 255, 1)
            if not layer(self.hwnd, None, c.byref(dst), c.byref(sz), dc, c.byref(source), 0, c.byref(blend), 2):
                raise c.WinError(c.get_last_error())
            self._side, self._hot = side, hot
        finally:
            if old:
                select(dc, old)
            if bitmap:
                remove(bitmap)
            drop_dc(dc)

    def begin(self, phase):
        if phase not in ("move", "click"):
            self.end()
            return
        self._window()
        self.phase = phase
        self._pulse_start = None
        self._monitor = None   # recheck scale if monitor settings changed since last use
        try:
            self.tick()
        except Exception:
            self.end()
            raise

    def tick(self):
        if not self.phase:
            return
        point = w.POINT()
        if not cursor_pos(c.byref(point)):
            raise c.WinError(c.get_last_error())
        monitor = get_monitor(point, 2)
        if monitor != self._monitor:
            xdpi, ydpi = U(), U()
            self._dpi = xdpi.value if monitor and monitor_dpi(monitor, 0, c.byref(xdpi), c.byref(ydpi)) == 0 else 96
            self._monitor = monitor
        scale = max(1., min(6., self._dpi / 96))
        strength = 0
        if self.phase == "click" and self._pulse_start is not None:
            t = (monotonic() - self._pulse_start) / .24
            if t < 1:
                strength = min(3, max(0, round(3*(1-t))))
            else:
                self._pulse_start = None
        shape = (scale, strength)
        if shape != self._shape:
            self._paint(point, scale, strength)
            self._shape = shape
            self._location = None
        if self._location != (point.x, point.y) or not visible(self.hwnd):
            if not position(self.hwnd, W(-1), point.x-self._hot, point.y-self._hot,
                            self._side, self._side, 0x51):  # NOSIZE | NOACTIVATE | SHOWWINDOW
                raise c.WinError(c.get_last_error())
            self._location = (point.x, point.y)

    def pulse_click(self):
        """Call after a successful click, while phase is click, to flash at its actual location."""
        if self.phase == "click":
            self._pulse_start = monotonic()
            self.tick()

    def end(self):
        self.phase = None
        self._pulse_start = None
        self._location = None
        if self.hwnd:
            show(self.hwnd, 0)

    def close(self):
        self.end()
        if self.hwnd:
            destroy(self.hwnd)
            self.hwnd = None
        self._shape = None
