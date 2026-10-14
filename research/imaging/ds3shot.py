"""Capture the Dark Souls III window to a PNG (no external dependencies)."""

import argparse
import ctypes
import struct
import sys
import time
import zlib
from ctypes import wintypes as w

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)

SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
PW_RENDERFULLCONTENT = 0x00000002
DIB_RGB_COLORS = 0
BI_RGB = 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", w.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
        ("biPlanes", w.WORD), ("biBitCount", w.WORD), ("biCompression", w.DWORD),
        ("biSizeImage", w.DWORD), ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", w.DWORD), ("biClrImportant", w.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", w.DWORD * 3)]


def find_window(title="DARK SOULS III"):
    hwnd = user32.FindWindowW(None, title)
    if hwnd:
        return hwnd
    found = []

    @ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def cb(h, _):
        if user32.IsWindowVisible(h):
            n = user32.GetWindowTextLengthW(h)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(h, buf, n + 1)
                if "DARK SOULS" in buf.value.upper():
                    found.append((h, buf.value))
        return True

    user32.EnumWindows(cb, 0)
    return found[0][0] if found else None


def client_rect_screen(hwnd):
    r = w.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    pt = w.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x, pt.y, r.right - r.left, r.bottom - r.top


def grab(hwnd, x, y, cx, cy, use_printwindow=True):
    hdc_src = user32.GetDC(hwnd if use_printwindow else 0)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_src)
    bmp = gdi32.CreateCompatibleBitmap(hdc_src, cx, cy)
    gdi32.SelectObject(hdc_mem, bmp)
    try:
        if use_printwindow:
            ok = user32.PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)
            if not ok:
                gdi32.BitBlt(hdc_mem, 0, 0, cx, cy, user32.GetDC(0), x, y,
                             SRCCOPY | CAPTUREBLT)
        else:
            gdi32.BitBlt(hdc_mem, 0, 0, cx, cy, user32.GetDC(0), x, y, SRCCOPY | CAPTUREBLT)

        bi = BITMAPINFO()
        bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.bmiHeader.biWidth = cx
        bi.bmiHeader.biHeight = -cy  # top-down
        bi.bmiHeader.biPlanes = 1
        bi.bmiHeader.biBitCount = 32
        bi.bmiHeader.biCompression = BI_RGB
        buf = ctypes.create_string_buffer(cx * cy * 4)
        got = gdi32.GetDIBits(hdc_mem, bmp, 0, cy, buf, ctypes.byref(bi), DIB_RGB_COLORS)
        if got == 0:
            raise SystemExit("GetDIBits failed")
        return buf.raw
    finally:
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(hwnd if use_printwindow else 0, hdc_src)


def black_ratio(bgra):
    """Fraction of sampled pixels that are pure black.  A torn PrintWindow capture
    of a D3D window comes back with big black rectangles, a real frame does not."""
    total = 0
    black = 0
    for i in range(0, len(bgra) - 4, 4 * 37):
        total += 1
        if bgra[i] < 6 and bgra[i + 1] < 6 and bgra[i + 2] < 6:
            black += 1
    return black / total if total else 1.0


def write_png(path, cx, cy, bgra):
    n = cx * cy * 4
    out = bytearray(n)
    out[0::4] = bgra[2::4]   # R
    out[1::4] = bgra[1::4]   # G
    out[2::4] = bgra[0::4]   # B
    out[3::4] = b"\xff" * (n // 4)
    rows = b"".join(b"\x00" + bytes(out[i * cx * 4:(i + 1) * cx * 4]) for i in range(cy))

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", cx, cy, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(rows, 6))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--title", default="DARK SOULS III")
    ap.add_argument("--scale", type=float, default=1.0, help="downscale factor")
    ap.add_argument("--screen", action="store_true", help="force screen BitBlt")
    args = ap.parse_args()

    hwnd = find_window(args.title)
    if not hwnd:
        raise SystemExit("game window not found")
    x, y, cx, cy = client_rect_screen(hwnd)
    print(f"hwnd=0x{hwnd:X} client=({x},{y}) {cx}x{cy}")
    bgra = grab(hwnd, x, y, cx, cy, use_printwindow=not args.screen)

    # A PrintWindow capture of a D3D window is sometimes torn (large black
    # rectangles).  Detect that and retry, alternating with a screen BitBlt.
    for attempt in range(6):
        br = black_ratio(bgra)
        if br <= 0.02 and any(bgra[: cx * cy * 4: 997]):
            break
        print("capture looks torn (%.1f%% black), retry %d" % (br * 100, attempt + 1))
        time.sleep(0.15)
        bgra = grab(hwnd, x, y, cx, cy, use_printwindow=(attempt % 2 == 0))

    if args.scale != 1.0:
        step = max(1, round(1 / args.scale))
        ncx, ncy = cx // step, cy // step
        rows = []
        for j in range(ncy):
            row = bgra[(j * step) * cx * 4: ((j + 1) * step) * cx * 4]
            rows.append(b"".join(row[i * step * 4:i * step * 4 + 4] for i in range(ncx)))
        bgra = b"".join(rows)
        cx, cy = ncx, ncy

    write_png(args.out, cx, cy, bgra)
    print(f"wrote {args.out} ({cx}x{cy})")


if __name__ == "__main__":
    main()
