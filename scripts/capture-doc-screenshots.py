from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
DEMO_STORE = ROOT / "build" / "demo-store"
OUTPUT = ROOT / "docs" / "screenshots"


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", ctypes.c_ushort),
        ("biBitCount", ctypes.c_ushort),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", _BITMAPINFOHEADER),
        ("bmiColors", ctypes.c_uint32 * 3),
    ]


def _root_window(widget) -> int:
    return int(
        ctypes.windll.user32.GetAncestor(
            widget.winfo_id(),
            2,  # GA_ROOT
        )
    )


def _capture_client(widget, path: Path) -> None:
    widget.update_idletasks()
    widget.update()
    time.sleep(0.35)
    hwnd = _root_window(widget)
    window_rect = _RECT()
    client_rect = _RECT()
    origin = (ctypes.c_long * 2)()
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    user32.GetWindowDC.restype = ctypes.c_void_p
    user32.PrintWindow.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint,
    ]
    user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
    gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
    gdi32.CreateCompatibleBitmap.restype = ctypes.c_void_p
    gdi32.CreateCompatibleBitmap.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
    ]
    gdi32.SelectObject.restype = ctypes.c_void_p
    gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
    gdi32.GetDIBits.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.POINTER(_BITMAPINFO),
        ctypes.c_uint,
    ]
    user32.GetWindowRect(hwnd, ctypes.byref(window_rect))
    user32.GetClientRect(hwnd, ctypes.byref(client_rect))
    user32.ClientToScreen(hwnd, ctypes.byref(origin))

    width = window_rect.right - window_rect.left
    height = window_rect.bottom - window_rect.top
    window_dc = user32.GetWindowDC(hwnd)
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    previous = gdi32.SelectObject(memory_dc, bitmap)
    try:
        if not user32.PrintWindow(hwnd, memory_dc, 2):
            raise RuntimeError("PrintWindow failed")
        info = _BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = 0
        buffer = ctypes.create_string_buffer(width * height * 4)
        lines = gdi32.GetDIBits(
            memory_dc,
            bitmap,
            0,
            height,
            buffer,
            ctypes.byref(info),
            0,
        )
        if lines != height:
            raise RuntimeError("GetDIBits failed")
        image = Image.frombuffer(
            "RGB",
            (width, height),
            buffer,
            "raw",
            "BGRX",
            0,
            1,
        )
        image.crop(
            (
                origin[0] - window_rect.left,
                origin[1] - window_rect.top,
                origin[0] - window_rect.left + client_rect.right,
                origin[1] - window_rect.top + client_rect.bottom,
            )
        ).save(path)
    finally:
        gdi32.SelectObject(memory_dc, previous)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(hwnd, window_dc)


def main() -> None:
    os.environ["AUTOBOYA_HOME"] = str(DEMO_STORE)
    os.environ["BOYA_KIT_DISABLE_AUTO_REFRESH"] = "1"
    os.chdir(ROOT)
    now = time.time()
    for name in ("courses.json", "statistics.json"):
        path = DEMO_STORE / "cache" / name
        if path.exists():
            os.utime(path, (now, now))

    from boya_kit.gui import BoyaApp

    OUTPUT.mkdir(parents=True, exist_ok=True)

    def capture_page(page: str) -> None:
        app = BoyaApp()
        app.attributes("-topmost", True)
        app.geometry("1600x950+20+20")
        app.update_idletasks()
        app._refresh_visuals(True)
        app._auth_prompted.update(
            str(user.get("username", ""))
            for user in app.snapshot.get("users", [])
            if user.get("auth_status") == "auth_required"
        )

        def capture() -> None:
            app._show_page(page)
            app.update()
            _capture_client(app, OUTPUT / f"{page}-en.png")
            app.after(100, app.destroy)

        app.after(500, capture)
        app.mainloop()

    single_page = os.environ.get("AUTOBOYA_CAPTURE_PAGE", "").strip()
    if not single_page:
        for page in ("dashboard", "accounts", "settings"):
            environment = os.environ.copy()
            environment["AUTOBOYA_CAPTURE_PAGE"] = page
            subprocess.run(
                [sys.executable, str(Path(__file__).resolve())],
                cwd=ROOT,
                env=environment,
                check=True,
            )
        return
    capture_page(single_page)


if __name__ == "__main__":
    main()
