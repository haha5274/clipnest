"""系统托盘图标（Shell_NotifyIcon + 隐藏窗口消息循环）。"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

WM_DESTROY = 0x0002
WM_COMMAND = 0x0111
WM_APP = 0x8000
WM_TRAY = WM_APP + 2
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205

NIM_ADD, NIM_DELETE = 0, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x1, 0x2, 0x4
MF_STRING = 0x0000
MF_SEPARATOR = 0x0800
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100

ID_SHOW, ID_CLEAR, ID_QUIT = 1001, 1002, 1003

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD),
                ("yHotspot", wintypes.DWORD), ("hbmMask", wintypes.HBITMAP),
                ("hbmColor", wintypes.HBITMAP)]


user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                  wintypes.WPARAM, wintypes.LPARAM]
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wintypes.ATOM
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT,
                               ctypes.c_size_t, wintypes.LPCWSTR]
user32.AppendMenuW.restype = wintypes.BOOL
user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                  wintypes.LPVOID]
user32.TrackPopupMenu.restype = wintypes.BOOL
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.DestroyMenu.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
user32.LoadCursorW.restype = wintypes.HANDLE
user32.LoadIconW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
user32.LoadIconW.restype = wintypes.HICON
user32.DestroyIcon.argtypes = [wintypes.HICON]
user32.DestroyIcon.restype = wintypes.BOOL
user32.CreateIconIndirect.argtypes = [ctypes.POINTER(ICONINFO)]
user32.CreateIconIndirect.restype = wintypes.HICON
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                               wintypes.UINT, wintypes.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = LRESULT
gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD,
]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateBitmap.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.UINT,
                               wintypes.UINT, ctypes.c_void_p]
gdi32.CreateBitmap.restype = wintypes.HBITMAP
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL

# 16x16 剪贴板图案：b 蓝边、w 白纸、d 深色文字线、. 透明
_ART = [
    "................",
    "......bbbb......",
    ".....bbbbbb.....",
    "...bwwwwwwwwb...",
    "...bwwwwwwwwb...",
    "...bwwddddwwb...",
    "...bwwwwwwwwb...",
    "...bwwwwwwwwb...",
    "...bwwddddwwb...",
    "...bwwwwwwwwb...",
    "...bwwwwwwwwb...",
    "...bwwddddwwb...",
    "...bwwwwwwwwb...",
    "...bbbbbbbbbb...",
    "................",
    "................",
]
_COLORS = {
    "b": (0xED, 0x6F, 0x2F, 0xFF),  # BGRA of #2f6fed
    "w": (0xFF, 0xFF, 0xFF, 0xFF),
    "d": (0x29, 0x21, 0x1D, 0xFF),  # BGRA of #1d2129
}


def build_icon(art: list[str] = _ART) -> int:
    """按像素表画一个图标，返回 HICON（调用方负责 DestroyIcon）。"""
    size = len(art)
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = size
    bmi.bmiHeader.biHeight = -size  # 自上而下
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0  # BI_RGB

    hdc = user32.GetDC(None)
    bits = ctypes.c_void_p()
    try:
        color = gdi32.CreateDIBSection(hdc, ctypes.byref(bmi), 0,
                                       ctypes.byref(bits), None, 0)
        if not color:
            raise OSError(ctypes.get_last_error(), "CreateDIBSection failed")
        buf = bytearray(size * size * 4)
        for y, row in enumerate(art):
            for x, ch in enumerate(row):
                if ch == ".":
                    continue
                b, g, r, a = _COLORS[ch]
                off = (y * size + x) * 4
                buf[off:off + 4] = bytes((b, g, r, a))
        ctypes.memmove(bits, bytes(buf), len(buf))

        mask = gdi32.CreateBitmap(size, size, 1, 1, b"\x00" * (size * size // 8))
        info = ICONINFO(True, 0, 0, mask, color)
        icon = user32.CreateIconIndirect(ctypes.byref(info))
        gdi32.DeleteObject(color)
        if mask:
            gdi32.DeleteObject(mask)
        if not icon:
            raise OSError(ctypes.get_last_error(), "CreateIconIndirect failed")
        return int(icon)
    finally:
        user32.ReleaseDC(None, hdc)


class TrayIcon:
    """在独立线程里跑隐藏窗口消息循环，承载托盘图标与右键菜单。"""

    def __init__(self, tooltip: str = "ClipNest", on_show=None,
                 on_clear=None, on_quit=None):
        self.tooltip = tooltip[:127]
        self.on_show = on_show
        self.on_clear = on_clear
        self.on_quit = on_quit
        self.hwnd = None
        self.hicon = None
        self.added = False
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._wndproc = None
        self._class_name = f"ClipNestTray_{id(self)}"

    # ---------------------------------------------------------------- 生命周期
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="clipnest-tray")
        self._thread.start()

    def wait_ready(self, timeout: float = 3.0) -> bool:
        return self._ready.wait(timeout)

    def stop(self) -> None:
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_COMMAND, ID_QUIT, 0)
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self.added = False

    # ------------------------------------------------------------------ 内部
    def _run(self) -> None:
        hinst = kernel32.GetModuleHandleW(None)
        self._wndproc = WNDPROC(self._on_message)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = hinst
        wc.hCursor = user32.LoadCursorW(None, 32512)  # IDC_ARROW
        wc.lpszClassName = self._class_name
        if not user32.RegisterClassW(ctypes.byref(wc)):
            err = ctypes.get_last_error()
            if err != 1410:  # 类已注册
                self._ready.set()
                return

        self.hwnd = user32.CreateWindowExW(0, self._class_name, "ClipNest Tray",
                                           0, 0, 0, 0, 0, None, None, hinst, None)
        if not self.hwnd:
            self._ready.set()
            return

        try:
            self.hicon = build_icon()
            self._icon_owned = True
        except OSError:
            self.hicon = user32.LoadIconW(None, 32512)  # IDI_APPLICATION
            self._icon_owned = False

        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = self.hwnd
        data.uID = 1
        data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        data.uCallbackMessage = WM_TRAY
        data.hIcon = self.hicon
        data.szTip = self.tooltip
        ok = shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data))
        self.added = bool(ok)
        self._ready.set()
        if not ok:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None
            return

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(data))
        if self.hicon and getattr(self, "_icon_owned", False):
            user32.DestroyIcon(self.hicon)
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None
        self._ready.clear()

    def _on_message(self, hwnd, msg, wparam, lparam) -> int:
        if msg == WM_TRAY:
            event = lparam & 0xFFFF
            if event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                self._fire(self.on_show)
                return 0
            if event == WM_RBUTTONUP:
                self._popup(hwnd)
                return 0
        elif msg == WM_COMMAND:
            cmd = wparam & 0xFFFF
            if cmd == ID_SHOW:
                self._fire(self.on_show)
            elif cmd == ID_CLEAR:
                self._fire(self.on_clear)
            elif cmd == ID_QUIT:
                self._fire(self.on_quit)
                user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _popup(self, hwnd) -> None:
        menu = user32.CreatePopupMenu()
        if not menu:
            return
        user32.AppendMenuW(menu, MF_STRING, ID_SHOW, "显示窗口")
        user32.AppendMenuW(menu, MF_STRING, ID_CLEAR, "清空历史")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, ID_QUIT, "退出")
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(hwnd)
        cmd = user32.TrackPopupMenu(
            menu, TPM_RIGHTBUTTON | TPM_RETURNCMD, pt.x, pt.y, 0, hwnd, None)
        user32.PostMessageW(hwnd, 0x0000, 0, 0)  # 让菜单正常消失
        user32.DestroyMenu(menu)
        if cmd:
            user32.PostMessageW(hwnd, WM_COMMAND, cmd, 0)

    @staticmethod
    def _fire(callback) -> None:
        if not callback:
            return
        try:
            callback()
        except Exception:  # noqa: BLE001
            pass
