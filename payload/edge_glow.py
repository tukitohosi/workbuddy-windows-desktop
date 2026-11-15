"""Four noninteractive, per-pixel-alpha strips around a Windows monitor."""
import ctypes as c
from ctypes import wintypes as w
from array import array
from functools import lru_cache
from math import cos, exp, hypot, pi
from time import monotonic


CLASS = "WorkBuddyDesktopEdgeGlow"
NAMES = ("top", "bottom", "left", "right")
EX_STYLE = 0x00080000 | 0x00000020 | 0x08000000 | 0x00000080 | 0x00000008
# WS_EX_LAYERED, TRANSPARENT, NOACTIVATE, TOOLWINDOW, TOPMOST


def api(library, name, result, *args):
    fn = getattr(library, name)
    fn.argtypes, fn.restype = args, result
    return fn


class WndClass(c.Structure):
    _fields_ = [("style", w.UINT), ("proc", c.c_void_p), ("classExtra", c.c_int),
                ("windowExtra", c.c_int), ("instance", w.HINSTANCE), ("icon", w.HANDLE),
                ("cursor", w.HANDLE), ("background", w.HANDLE), ("menu", w.LPCWSTR), ("name", w.LPCWSTR)]


class BitmapHeader(c.Structure):
    _fields_ = [("size", w.DWORD), ("width", w.LONG), ("height", w.LONG), ("planes", w.WORD),
                ("bits", w.WORD), ("compression", w.DWORD), ("imageBytes", w.DWORD),
                ("xPerMeter", w.LONG), ("yPerMeter", w.LONG), ("colors", w.DWORD), ("important", w.DWORD)]


class Blend(c.Structure):
    _fields_ = [("op", w.BYTE), ("flags", w.BYTE), ("constant", w.BYTE), ("format", w.BYTE)]


u = c.WinDLL("user32", use_last_error=True)
g = c.WinDLL("gdi32", use_last_error=True)
k = c.WinDLL("kernel32", use_last_error=True)
handle, integer, ptr, string = w.HANDLE, c.c_int, c.c_void_p, w.LPCWSTR
module = api(k, "GetModuleHandleW", handle, string)
register = api(u, "RegisterClassW", w.ATOM, c.POINTER(WndClass))
create = api(u, "CreateWindowExW", w.HWND, w.DWORD, string, string, w.DWORD,
             integer, integer, integer, integer, w.HWND, handle, handle, ptr)
destroy = api(u, "DestroyWindow", w.BOOL, w.HWND)
show = api(u, "ShowWindow", w.BOOL, w.HWND, integer)
visible = api(u, "IsWindowVisible", w.BOOL, w.HWND)
memory_dc = api(g, "CreateCompatibleDC", handle, handle)
delete_dc = api(g, "DeleteDC", w.BOOL, handle)
create_bitmap = api(g, "CreateDIBSection", handle, handle, c.POINTER(BitmapHeader), w.UINT,
                    c.POINTER(ptr), handle, w.DWORD)
select = api(g, "SelectObject", handle, handle, handle)
delete = api(g, "DeleteObject", w.BOOL, handle)
upload = api(u, "UpdateLayeredWindow", w.BOOL, w.HWND, handle, c.POINTER(w.POINT), c.POINTER(w.SIZE),
             handle, c.POINTER(w.POINT), w.DWORD, c.POINTER(Blend), w.DWORD)
system_parameters = api(u, "SystemParametersInfoW", w.BOOL, w.UINT, w.UINT, ptr, w.UINT)


def smooth(x):
    x = max(0.0, min(x, 1.0))
    return x*x*(3-2*x)


# Theme samples follow the perimeter clockwise from the top-left. The first
# color occurs at both ends. The fourth channel controls the local intensity.
STOPS = ((125,163,255,134), (152,184,255,116), (149,145,247,102), (121,164,251,123),
         (135,157,251,108), (165,151,247,117), (123,169,249,110), (145,178,253,123))


def shade(position):
    step = (position % 1.0) * len(STOPS)
    index = int(step)
    mix = smooth(step - index)
    a, b = STOPS[index], STOPS[(index+1) % len(STOPS)]
    return tuple(x+(y-x)*mix for x, y in zip(a, b))


def bgra(red, green, blue, alpha):
    a = max(0, min(255, round(alpha)))
    # Native-endian packed BGRA; Windows architectures are little-endian.
    return (a<<24) | (round(red*a/255)<<16) | (round(green*a/255)<<8) | round(blue*a/255)


def ribbon_profiles(length, thickness, start, delta, stride):
    # Spatial changes span hundreds of pixels. Build only one vertical profile
    # per few pixels and repeat it, keeping antialiasing at full display DPI.
    result = []
    for pos in range(0, length, stride):
        t = start + (pos+min(stride,length-pos)*0.5)*delta
        r,g,b,power = shade(t)
        width = 0.46 + 0.085*cos(2*pi*(t-0.13))
        result.append(tuple(bgra(r,g,b,power*exp(-2.0*(d/(width*thickness))**2)
                                      *(1-smooth((d/thickness-0.63)/0.37))) for d in range(thickness)))
    return result


def rectangles(bounds, thickness):
    left, top, right, bottom = bounds
    width, height = right - left, bottom - top
    return ((left, top, width, thickness), (left, bottom-thickness, width, thickness),
            (left, top+thickness, thickness, height-2*thickness),
            (right-thickness, top+thickness, thickness, height-2*thickness))


def corner_color(x, y, color, thickness):
    # A rounded-rectangle distance field bends the light at the corner.
    # A second diffuse Gaussian adds a blue-ice light pool under the bend.
    r,g,b,power = color
    unit_x, unit_y = x/thickness, y/thickness
    radius = 0.74
    sx, sy = radius-unit_x, radius-unit_y
    signed = hypot(max(0,sx),max(0,sy)) + min(max(sx,sy),0) - radius
    depth = abs(signed)
    ribbon = power*exp(-2*(depth/0.53)**2)
    pool = 34*exp(-2*((unit_x-0.39)**2+(unit_y-0.39)**2)/0.83**2)
    strength = (ribbon+pool)*(1-smooth((min(unit_x,unit_y)-0.68)/0.32))
    shine = pool/max(ribbon+pool,1)
    return bgra(r+20*shine,g+21*shine,b,strength)


@lru_cache(maxsize=8)
def strip_texture(side, monitor_w, monitor_h, thickness):
    horizontal = side in ("top","bottom")
    reverse_depth = side in ("bottom","right")
    full = monitor_w if horizontal else monitor_h
    length = full if horizontal else full-2*thickness
    start = {"top":0, "right":0.25, "bottom":0.75, "left":1.0}[side]
    delta = (0.25 if side in ("top","right") else -0.25) / full
    offset = 0 if horizontal else thickness
    stride = max(4, thickness//6)
    profiles = ribbon_profiles(length,thickness,start+offset*delta,delta,stride)
    if horizontal:
        rows = []
        for y in range(thickness):
            depth = thickness-1-y if reverse_depth else y
            runs = [array("I",[p[depth]]).tobytes()*stride for p in profiles]
            rows.append(bytearray(b"".join(runs)[:length*4]))
    else:
        rows = []
        for p in profiles:
            line = array("I",p[::-1] if reverse_depth else p).tobytes()
            rows.extend(bytearray(line) for _ in range(min(stride,length-len(rows))))
    # Smoothly blend a small two-dimensional light pool into each end of
    # the long one-dimensional profile. Its color is shared by both strips.
    # Cache corner samples across the adjoining horizontal and vertical strips.
    radius = min(2*thickness,full//2)
    for end in (0,1):
        color = shade(start+(delta*full if end else 0))
        patch = corner_patch(thickness,color)
        for d in range(thickness):
            for j in range(offset,radius):
                along = length-1-(j-offset) if end else j-offset
                inset = thickness-1-d if reverse_depth else d
                row, col = (inset,along) if horizontal else (along,inset)
                src = (d*2*thickness+j)*4
                target = col*4
                weight = 1-smooth((j/thickness-0.87)/1.1)
                old = rows[row][target:target+4]
                new = patch[src:src+4]
                rows[row][target:target+4] = bytes(round(x+(y-x)*weight) for x,y in zip(old,new))
    return b"".join(rows)


@lru_cache(maxsize=16)
def corner_patch(thickness,color):
    return array("I",(corner_color(x+0.5,y+0.5,color,thickness)
                     for y in range(thickness) for x in range(2*thickness))).tobytes()


class Layer:
    """Keep the selected DIB and DC so animation only changes global opacity."""
    def __init__(self, rect, pixels):
        x,y,width,height = rect
        self.destination, self.size = w.POINT(x,y), w.SIZE(width,height)
        self.dc = self.bitmap = self.previous = None
        self.dc = memory_dc(None)
        if not self.dc:
            raise c.WinError(c.get_last_error())
        try:
            header = BitmapHeader(size=c.sizeof(BitmapHeader), width=width, height=-height, planes=1, bits=32)
            address = ptr()
            self.bitmap = create_bitmap(self.dc,c.byref(header),0,c.byref(address),None,0)
            if not self.bitmap or not address.value:
                raise c.WinError(c.get_last_error())
            c.memmove(address,pixels,len(pixels))
            self.previous = select(self.dc,self.bitmap)
            if not self.previous:
                raise c.WinError(c.get_last_error())
        except Exception:
            self.close()
            raise

    def present(self, hwnd, opacity):
        if not upload(hwnd,None,c.byref(self.destination),c.byref(self.size),self.dc,
                      c.byref(w.POINT()),0,c.byref(Blend(0,0,opacity,1)),2):
            raise c.WinError(c.get_last_error())

    def close(self):
        if self.previous:
            select(self.dc,self.previous)
        if self.bitmap:
            delete(self.bitmap)
        if self.dc:
            delete_dc(self.dc)
        self.dc = self.bitmap = self.previous = None


def client_animation_enabled():
    value = w.BOOL()
    return bool(system_parameters(0x1042,0,c.byref(value),0) and value.value)


def opacity_at(age, remaining, animate):
    if not animate:
        return 255
    # Retain a visible initial halo while the rest rises. No recurring pulse.
    attack = 0.22 + 0.78*smooth(age/0.34)
    release = smooth(remaining/0.45)
    return round(255*min(attack,release))


class EdgeGlow:
    def __init__(self):
        self.hwnds = []
        self.geometry = None
        self.shown = False
        self.layers = []
        self.started = 0
        self.opacity = -1
        self.animated = False
        instance = module(None)
        cls = WndClass(proc=c.cast(u.DefWindowProcW, ptr), instance=instance, name=CLASS)
        if not register(c.byref(cls)) and c.get_last_error() != 1410:  # CLASS_ALREADY_EXISTS
            raise c.WinError(c.get_last_error())
        try:
            for side in NAMES:
                hwnd = create(EX_STYLE, CLASS, "WorkBuddy edge " + side, 0x88000000,  # WS_POPUP | WS_DISABLED
                              0, 0, 1, 1, None, None, instance, None)
                if not hwnd:
                    raise c.WinError(c.get_last_error())
                self.hwnds.append(hwnd)
        except Exception:
            self.close()
            raise

    def display(self, bounds, scale):
        left, top, right, bottom = bounds
        width,height = right-left,bottom-top
        thickness = min(max(5, round(34 * scale)), width//2, (height-1)//2)
        if thickness < 1:
            raise RuntimeError("Monitor geometry unavailable.")
        geometry = (bounds, thickness)
        if geometry != self.geometry:
            layers = []
            try:
                for side,rect in zip(NAMES, rectangles(bounds,thickness)):
                    layers.append(Layer(rect,strip_texture(side,width,height,thickness)))
            except Exception:
                for layer in layers:
                    layer.close()
                raise
            for old in self.layers:
                old.close()
            self.layers = layers
            self.geometry = geometry
            self.opacity = -1
        now = monotonic()
        if not self.shown:
            self.started = now
            self.animated = client_animation_enabled()
            self.opacity = -1
        self._present(opacity_at(now-self.started,1,self.animated))
        if not self.shown:
            for hwnd in self.hwnds:
                show(hwnd, 4)  # SW_SHOWNOACTIVATE
            self.shown = all(map(visible, self.hwnds))
            if not self.shown:
                self.hide()
                raise RuntimeError("Screen edge indicator could not be shown.")

    def _present(self, opacity):
        if self.opacity != opacity:
            for layer,hwnd in zip(self.layers,self.hwnds):
                layer.present(hwnd,opacity)
            self.opacity = opacity

    def tick(self, now, deadline=0):
        if self.shown:
            self._present(opacity_at(now-self.started,deadline-now if deadline else 1,self.animated))

    def hide(self):
        for hwnd in self.hwnds:
            show(hwnd, 0)
        self.shown = False

    def close(self):
        for layer in self.layers:
            layer.close()
        self.layers.clear()
        for hwnd in self.hwnds:
            destroy(hwnd)
        self.hwnds.clear()
