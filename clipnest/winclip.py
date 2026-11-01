"""Win32 剪贴板读写。"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

CF_TEXT = 1
CF_DIB = 8
CF_UNICODETEXT = 13

GMEM_MOVEABLE = 0x0002
HANDLE = ctypes.c_void_p

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.restype = wintypes.BOOL

user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, HANDLE]
user32.SetClipboardData.restype = HANDLE
user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD

kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = HANDLE
kernel32.GlobalLock.argtypes = [HANDLE]
kernel32.GlobalLock.restype = HANDLE
kernel32.GlobalUnlock.argtypes = [HANDLE]
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalSize.argtypes = [HANDLE]
kernel32.GlobalSize.restype = ctypes.c_size_t
kernel32.GlobalFree.argtypes = [HANDLE]
kernel32.GlobalFree.restype = HANDLE


class ClipboardError(OSError):
    pass


def sequence_number() -> int:
    """剪贴板变更序号；发生变化说明内容被写入过。"""
    return int(user32.GetClipboardSequenceNumber())


def _open(retries: int = 10, delay: float = 0.02) -> None:
    for _ in range(retries):
        if user32.OpenClipboard(None):
            return
        time.sleep(delay)
    raise ClipboardError("无法打开剪贴板（可能被其他程序占用）")


def _read_bytes(fmt: int) -> bytes | None:
    handle = user32.GetClipboardData(fmt)
    if not handle:
        return None
    ptr = kernel32.GlobalLock(handle)
    if not ptr:
        return None
    try:
        size = int(kernel32.GlobalSize(handle))
        if size <= 0:
            return None
        return ctypes.string_at(ptr, size)
    finally:
        kernel32.GlobalUnlock(handle)


def read_text() -> str | None:
    """读取剪贴板中的文本，无文本返回 None。"""
    _open()
    try:
        if user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            raw = _read_bytes(CF_UNICODETEXT)
            if raw:
                text = raw.decode("utf-16-le", errors="ignore")
                return text.split("\x00", 1)[0]
        if user32.IsClipboardFormatAvailable(CF_TEXT):
            raw = _read_bytes(CF_TEXT)
            if raw:
                return raw.split(b"\x00", 1)[0].decode("mbcs", errors="ignore")
        return None
    finally:
        user32.CloseClipboard()


def read_dib() -> bytes | None:
    """读取剪贴板中的位图（CF_DIB 原始字节）。"""
    _open()
    try:
        if not user32.IsClipboardFormatAvailable(CF_DIB):
            return None
        return _read_bytes(CF_DIB)
    finally:
        user32.CloseClipboard()


def _write(fmt: int, data: bytes) -> None:
    _open()
    try:
        if not user32.EmptyClipboard():
            raise ClipboardError("清空剪贴板失败")
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            raise ClipboardError("内存分配失败")
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            kernel32.GlobalFree(handle)
            raise ClipboardError("锁定内存失败")
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(fmt, handle):
            kernel32.GlobalFree(handle)
            raise ClipboardError("写入剪贴板失败")
    finally:
        user32.CloseClipboard()


def write_text(text: str) -> None:
    _write(CF_UNICODETEXT, (text + "\x00").encode("utf-16-le"))


def write_dib(dib: bytes) -> None:
    _write(CF_DIB, dib)
