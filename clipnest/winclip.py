"""Win32 剪贴板读写。"""

from __future__ import annotations

import ctypes
import re
import struct
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

CF_TEXT = 1
CF_DIB = 8
CF_UNICODETEXT = 13
CF_HDROP = 15

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
user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
user32.RegisterClipboardFormatW.restype = wintypes.UINT

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

_FORMATS: dict[str, int] = {}


def format_id(name: str) -> int:
    """注册表格式（HTML Format / Rich Text Format）的格式号，0 表示不可用。"""
    if name not in _FORMATS:
        _FORMATS[name] = int(user32.RegisterClipboardFormatW(name))
    return _FORMATS[name]


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


def read_files() -> list[str] | None:
    """读取 CF_HDROP 里的文件列表，没有文件返回 None。"""
    _open()
    try:
        if not user32.IsClipboardFormatAvailable(CF_HDROP):
            return None
        raw = _read_bytes(CF_HDROP)
    finally:
        user32.CloseClipboard()
    if not raw or len(raw) < 20:
        return None

    offset, _pt_x, _pt_y, _fnc, wide = struct.unpack_from("<IiiII", raw, 0)
    if offset >= len(raw):
        return None
    body = raw[offset:]
    if wide:
        text = body.decode("utf-16-le", errors="ignore")
    else:
        text = body.decode("mbcs", errors="ignore")
    parts = [p for p in text.split("\x00") if p]
    return parts or None


def read_rich() -> dict[str, bytes] | None:
    """读取富文本格式（HTML Format / RTF），没有则返回 None。"""
    bundle: dict[str, bytes] = {}
    html_id = format_id("HTML Format")
    rtf_id = format_id("Rich Text Format")
    _open()
    try:
        if html_id and user32.IsClipboardFormatAvailable(html_id):
            raw = _read_bytes(html_id)
            if raw:
                bundle["html"] = raw
        if rtf_id and user32.IsClipboardFormatAvailable(rtf_id):
            raw = _read_bytes(rtf_id)
            if raw:
                bundle["rtf"] = raw
    finally:
        user32.CloseClipboard()
    return bundle or None


def _alloc(data: bytes) -> HANDLE:
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data) or 1)
    if not handle:
        raise ClipboardError("内存分配失败")
    ptr = kernel32.GlobalLock(handle)
    if not ptr:
        kernel32.GlobalFree(handle)
        raise ClipboardError("锁定内存失败")
    if data:
        ctypes.memmove(ptr, data, len(data))
    kernel32.GlobalUnlock(handle)
    return handle


def _write_many(items: list[tuple[int, bytes]]) -> None:
    """把多种格式一次性写进剪贴板，保持原有的富文本/纯文本并存关系。"""
    _open()
    try:
        if not user32.EmptyClipboard():
            raise ClipboardError("清空剪贴板失败")
        for fmt, data in items:
            handle = _alloc(data)
            if not user32.SetClipboardData(fmt, handle):
                kernel32.GlobalFree(handle)
                raise ClipboardError("写入剪贴板失败")
    finally:
        user32.CloseClipboard()


def write_text(text: str) -> None:
    _write_many([(CF_UNICODETEXT, (text + "\x00").encode("utf-16-le"))])


def write_dib(dib: bytes) -> None:
    _write_many([(CF_DIB, dib)])


def files_payload(paths: list[str]) -> bytes:
    """构造 CF_HDROP 需要的 DROPFILES 结构。"""
    header = struct.pack("<IiiII", 20, 0, 0, 0, 1)
    names = "".join(p + "\x00" for p in paths) + "\x00"
    return header + names.encode("utf-16-le")


def write_files(paths: list[str]) -> None:
    _write_many([(CF_HDROP, files_payload(paths))])


def write_bundle(text: str | None = None, html: bytes | None = None,
                 rtf: bytes | None = None) -> None:
    """写回富文本：纯文本兜底，HTML / RTF 保留格式。"""
    items: list[tuple[int, bytes]] = []
    if text is not None:
        items.append((CF_UNICODETEXT, (text + "\x00").encode("utf-16-le")))
    if html:
        fmt = format_id("HTML Format")
        if fmt:
            items.append((fmt, html))
    if rtf:
        fmt = format_id("Rich Text Format")
        if fmt:
            items.append((fmt, rtf))
    if not items:
        raise ClipboardError("没有可写入的内容")
    _write_many(items)


_TAG = re.compile(r"<[^>]+>")
_BLOCK = re.compile(r"</(p|div|li|tr|h[1-6]|br)\s*>|<br\s*/?>", re.I)


def html_to_text(raw: bytes) -> str:
    """从 HTML Format 负载里取可读文字，用于列表预览。"""
    text = raw.decode("utf-8", errors="ignore")
    start = text.find("StartFragment:")
    if start >= 0:
        frag_at = text.find("\n", start)
        body = text[frag_at + 1:] if frag_at > 0 else text
    else:
        body = text
    end = body.find("<!--EndFragment-->")
    if end > 0:
        body = body[:end]
    body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", body)
    body = _BLOCK.sub("\n", body)
    body = _TAG.sub("", body)
    body = (body.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"'))
    lines = [" ".join(line.split()) for line in body.splitlines()]
    return "\n".join(line for line in lines if line).strip()


_RTF_TOKEN = re.compile(r"\\[a-z]+-?\d* ?|[{}]|\\.")


def rtf_to_text(raw: bytes) -> str:
    """粗暴地把 RTF 压成纯文本，只用于预览。"""
    text = raw.decode("latin-1", errors="ignore")
    text = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), text)
    text = _RTF_TOKEN.sub(" ", text)
    return " ".join(text.split()).strip()
