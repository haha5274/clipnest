"""全局热键。

热键线程不建窗口，靠线程消息队列收 WM_HOTKEY，然后回调给 UI 侧。
"""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

HOTKEY_ID = 0xB10C

_MODIFIERS = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN, "super": MOD_WIN, "meta": MOD_WIN,
}

_NAMED_KEYS = {
    "space": 0x20, "enter": 0x0D, "return": 0x0D, "tab": 0x09,
    "esc": 0x1B, "escape": 0x1B, "backspace": 0x08, "delete": 0x2E,
    "insert": 0x2D, "home": 0x24, "end": 0x23, "pageup": 0x21,
    "pagedown": 0x22, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
}


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int,
                                  wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(_MSG), wintypes.HWND,
                               wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT,
                                      wintypes.WPARAM, wintypes.LPARAM]
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


def parse_hotkey(spec: str) -> tuple[int, int]:
    """'ctrl+alt+v' -> (modifiers, vk)。"""
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if not parts:
        raise ValueError("热键不能为空")
    mods = 0
    key = None
    for part in parts:
        if part in _MODIFIERS:
            mods |= _MODIFIERS[part]
        else:
            key = part
    if key is None:
        raise ValueError(f"热键缺少主键: {spec}")
    if len(key) == 1 and key.isalpha():
        vk = ord(key.upper())
    elif len(key) == 1 and key.isdigit():
        vk = ord(key)
    elif key in _NAMED_KEYS:
        vk = _NAMED_KEYS[key]
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    else:
        raise ValueError(f"无法识别的按键: {key}")
    if not mods:
        raise ValueError("热键必须包含至少一个修饰键（ctrl / alt / shift / win）")
    return mods | MOD_NOREPEAT, vk


class HotkeyManager(threading.Thread):
    """注册一个全局热键；注册失败时把错误交给 on_error。"""

    def __init__(self, spec: str, on_press, on_error=None):
        super().__init__(daemon=True, name="clipnest-hotkey")
        self.spec = spec
        self.on_press = on_press
        self.on_error = on_error
        self._thread_id: int | None = None
        self._ready = threading.Event()
        self._registered = False

    def run(self) -> None:
        self._thread_id = int(kernel32.GetCurrentThreadId())
        try:
            mods, vk = parse_hotkey(self.spec)
            ok = user32.RegisterHotKey(None, HOTKEY_ID, mods, vk)
        except ValueError as exc:
            self._ready.set()
            self._report(str(exc))
            return
        if not ok:
            self._ready.set()
            self._report(f"热键 {self.spec} 注册失败，可能已被其他程序占用")
            return

        self._registered = True
        self._ready.set()
        msg = _MSG()
        while True:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret in (0, -1):
                break
            if msg.message == WM_HOTKEY:
                try:
                    self.on_press()
                except Exception:  # noqa: BLE001
                    pass
        if self._registered:
            user32.UnregisterHotKey(None, HOTKEY_ID)
            self._registered = False

    def _report(self, message: str) -> None:
        if self.on_error:
            try:
                self.on_error(message)
            except Exception:  # noqa: BLE001
                pass

    def wait_ready(self, timeout: float = 2.0) -> bool:
        self._ready.wait(timeout)
        return self._registered

    def stop(self) -> None:
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
