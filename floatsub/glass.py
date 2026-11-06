"""给无边框窗口加一点背后的磨砂。Windows 10 用系统的背景模糊。"""

import ctypes
from ctypes import byref, sizeof
from ctypes.wintypes import DWORD, HWND

_ACCENT_BLUR = 3
_ACCENT_ACRYLIC = 4
_WCA_ACCENT_POLICY = 19


class _AccentPolicy(ctypes.Structure):
    _fields_ = [
        ("AccentState", DWORD),
        ("AccentFlags", DWORD),
        ("GradientColor", DWORD),
        ("AnimationId", DWORD),
    ]


class _CompositionData(ctypes.Structure):
    _fields_ = [
        ("Attribute", DWORD),
        ("Data", ctypes.c_void_p),
        ("SizeOfData", ctypes.c_size_t),
    ]


def window_handle(widget) -> int:
    """控件所在的那一层窗口。不用 GetParent，否则会拿到拥有者，把磨砂加错地方。"""
    widget.update_idletasks()
    hwnd = int(widget.winfo_id())
    root = ctypes.windll.user32.GetAncestor(hwnd, 2)  # GA_ROOT，不穿过 owner
    return int(root or hwnd)


def clear_blur(hwnd: int) -> None:
    """拖动时先关掉磨砂。开着磨砂时，窗口会跟着鼠标慢慢蹭。"""
    policy = _AccentPolicy()
    data = _CompositionData()
    data.Attribute = _WCA_ACCENT_POLICY
    data.SizeOfData = sizeof(policy)
    data.Data = ctypes.addressof(policy)
    ctypes.windll.user32.SetWindowCompositionAttribute(HWND(hwnd), byref(data))


def move_window(hwnd: int, x: int, y: int) -> None:
    ctypes.windll.user32.SetWindowPos(HWND(hwnd), HWND(0), int(x), int(y), 0, 0, 0x0015)


def place_window(hwnd: int, x: int, y: int, width: int, height: int) -> None:
    ctypes.windll.user32.SetWindowPos(
        HWND(hwnd), HWND(0), int(x), int(y), int(width), int(height), 0x0014
    )


def apply_blur(hwnd: int, *, acrylic: bool = True, opacity: int = 28) -> None:
    """opacity 是 0 到 255，越小越透。颜色是很淡的冷灰。"""
    tint = max(0, min(255, opacity)) << 24 | 0x00141A28
    policy = _AccentPolicy()
    policy.AccentState = _ACCENT_ACRYLIC if acrylic else _ACCENT_BLUR
    policy.AccentFlags = 2
    policy.GradientColor = tint
    data = _CompositionData()
    data.Attribute = _WCA_ACCENT_POLICY
    data.SizeOfData = sizeof(policy)
    data.Data = ctypes.addressof(policy)
    ctypes.windll.user32.SetWindowCompositionAttribute(HWND(hwnd), byref(data))


def set_round(hwnd: int, size: int) -> None:
    region = ctypes.windll.gdi32.CreateEllipticRgn(0, 0, size, size)
    ctypes.windll.user32.SetWindowRgn(HWND(hwnd), region, True)


def clear_region(hwnd: int) -> None:
    ctypes.windll.user32.SetWindowRgn(HWND(hwnd), None, True)


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _Size(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class _Blend(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_byte),
        ("BlendFlags", ctypes.c_byte),
        ("SourceConstantAlpha", ctypes.c_byte),
        ("AlphaFormat", ctypes.c_byte),
    ]


class _BitmapInfo(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_int32),
        ("biHeight", ctypes.c_int32),
        ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


class _LogFont(ctypes.Structure):
    _fields_ = [
        ("lfHeight", ctypes.c_long),
        ("lfWidth", ctypes.c_long),
        ("lfEscapement", ctypes.c_long),
        ("lfOrientation", ctypes.c_long),
        ("lfWeight", ctypes.c_long),
        ("lfItalic", ctypes.c_byte),
        ("lfUnderline", ctypes.c_byte),
        ("lfStrikeOut", ctypes.c_byte),
        ("lfCharSet", ctypes.c_byte),
        ("lfOutPrecision", ctypes.c_byte),
        ("lfClipPrecision", ctypes.c_byte),
        ("lfQuality", ctypes.c_byte),
        ("lfPitchAndFamily", ctypes.c_byte),
        ("lfFaceName", ctypes.c_wchar * 32),
    ]


def disc_bgra(size: int, listening: bool) -> bytes:
    """平滑深色圆和「译」。边上留透明，字用灰度做透明，不再硬切。"""
    scale = 2
    full = size * scale
    glyph = _glyph_alpha(full)
    fill = (44, 33, 28)
    rim = (232, 146, 64) if listening else (212, 164, 116)
    ink = (248, 241, 231)
    outer = full / 2 - 1.2
    center = (full - 1) / 2
    acc = [[0.0, 0.0, 0.0, 0.0] for _ in range(size * size)]
    for y in range(full):
        for x in range(full):
            dist = ((x - center) ** 2 + (y - center) ** 2) ** 0.5
            disc = _cover(outer - dist)
            edge = _cover(outer - dist) * (1.0 - _cover(outer - 2.4 - dist))
            color = _mix(fill, rim, edge)
            alpha = max(disc, edge)
            mark = glyph[y * full + x] * disc
            color = _mix(color, ink, mark)
            alpha = alpha + (1.0 - alpha) * mark
            slot = (y // scale) * size + (x // scale)
            acc[slot][0] += color[0] * alpha
            acc[slot][1] += color[1] * alpha
            acc[slot][2] += color[2] * alpha
            acc[slot][3] += alpha
    samples = float(scale * scale)
    out = bytearray(size * size * 4)
    for index, (red, green, blue, alpha) in enumerate(acc):
        alpha /= samples
        if alpha <= 0.004:
            continue
        a = min(255, int(round(alpha * 255)))
        offset = index * 4
        out[offset] = min(255, int(round(blue / samples)))
        out[offset + 1] = min(255, int(round(green / samples)))
        out[offset + 2] = min(255, int(round(red / samples)))
        out[offset + 3] = a
    return bytes(out)


def _prepare_dc() -> tuple:
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    user32.GetDC.restype = ctypes.c_void_p
    user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
    gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
    gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
    gdi32.CreateDIBSection.restype = ctypes.c_void_p
    gdi32.CreateDIBSection.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.c_uint,
    ]
    gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    user32.FillRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    user32.DrawTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint]
    gdi32.CreateSolidBrush.restype = ctypes.c_void_p
    gdi32.CreateFontIndirectW.restype = ctypes.c_void_p
    gdi32.SetTextColor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    gdi32.SetBkMode.argtypes = [ctypes.c_void_p, ctypes.c_int]
    return user32, gdi32


def show_layered(hwnd: int, x: int, y: int, bgra: bytes, size: int) -> None:
    """用带透明的位图显示圆球，圆边可以抗锯齿。"""
    user32, gdi32 = _prepare_dc()
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.GetWindowLongPtrW.argtypes = [HWND, ctypes.c_int]
    user32.SetWindowLongPtrW.argtypes = [HWND, ctypes.c_int, ctypes.c_ssize_t]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    style = user32.GetWindowLongPtrW(HWND(hwnd), -20)
    user32.SetWindowLongPtrW(HWND(hwnd), -20, style | 0x00080000 | 0x00000080)
    info = _BitmapInfo()
    info.biSize = ctypes.sizeof(_BitmapInfo)
    info.biWidth = size
    info.biHeight = -size
    info.biPlanes = 1
    info.biBitCount = 32
    bits = ctypes.c_void_p()
    screen = user32.GetDC(0)
    mem = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateDIBSection(mem, ctypes.byref(info), 0, ctypes.byref(bits), None, 0)
    gdi32.SelectObject(mem, bitmap)
    ctypes.memmove(bits, bgra, size * size * 4)
    origin = _Point(0, 0)
    place = _Point(int(x), int(y))
    extent = _Size(size, size)
    blend = _Blend(0, 0, 255, 1)
    user32.UpdateLayeredWindow.argtypes = [
        HWND,
        ctypes.c_void_p,
        ctypes.POINTER(_Point),
        ctypes.POINTER(_Size),
        ctypes.c_void_p,
        ctypes.POINTER(_Point),
        DWORD,
        ctypes.POINTER(_Blend),
        DWORD,
    ]
    user32.UpdateLayeredWindow.restype = ctypes.c_int
    user32.UpdateLayeredWindow(
        HWND(hwnd), None, ctypes.byref(place), ctypes.byref(extent), mem, ctypes.byref(origin), 0, ctypes.byref(blend), 2
    )
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(0, screen)


def _cover(distance: float) -> float:
    return max(0.0, min(1.0, (distance + 0.85) / 1.7))


def _mix(base: tuple[int, int, int], ink: tuple[int, int, int], amount: float) -> tuple[float, float, float]:
    return tuple(base[i] + (ink[i] - base[i]) * amount for i in range(3))


def _glyph_alpha(size: int) -> list[float]:
    user32, gdi32 = _prepare_dc()
    hdc = user32.GetDC(0)
    mem = gdi32.CreateCompatibleDC(hdc)
    info = _BitmapInfo()
    info.biSize = ctypes.sizeof(_BitmapInfo)
    info.biWidth = size
    info.biHeight = -size
    info.biPlanes = 1
    info.biBitCount = 32
    bits = ctypes.c_void_p()
    bitmap = gdi32.CreateDIBSection(mem, ctypes.byref(info), 0, ctypes.byref(bits), None, 0)
    gdi32.SelectObject(mem, bitmap)
    brush = gdi32.CreateSolidBrush(0)
    clear = ctypes.wintypes.RECT(0, 0, size, size)
    user32.FillRect(mem, ctypes.byref(clear), brush)
    rect = ctypes.wintypes.RECT(0, -2, size, size - 2)
    font_info = _LogFont()
    font_info.lfHeight = -int(size * 0.42)
    font_info.lfWeight = 500
    font_info.lfQuality = 4
    font_info.lfCharSet = 1
    font_info.lfFaceName = "Microsoft YaHei UI"
    font = gdi32.CreateFontIndirectW(ctypes.byref(font_info))
    gdi32.SelectObject(mem, font)
    gdi32.SetTextColor(mem, 0x00FFFFFF)
    gdi32.SetBkMode(mem, 1)
    user32.DrawTextW(mem, "译", -1, ctypes.byref(rect), 0x825)
    raw = ctypes.string_at(bits, size * size * 4)
    gdi32.DeleteObject(font)
    gdi32.DeleteObject(brush)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(0, hdc)
    return [max(raw[i], raw[i + 1], raw[i + 2]) / 255 for i in range(0, len(raw), 4)]
