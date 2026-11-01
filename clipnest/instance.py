"""单实例控制：命名互斥量判断是否已在运行，命名事件唤醒已有窗口。"""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

ERROR_ALREADY_EXISTS = 183
EVENT_MODIFY_STATE = 0x0002
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258

kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL,
                                  wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.OpenEventW.restype = wintypes.HANDLE
kernel32.SetEvent.argtypes = [wintypes.HANDLE]
kernel32.SetEvent.restype = wintypes.BOOL
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL


class SingleInstance:
    """第一个实例拿到互斥量，之后的实例通过命名事件把它叫出来。"""

    def __init__(self, name: str = "ClipNest.SingleInstance"):
        self._mutex_name = "Local\\" + name
        self._event_name = "Local\\" + name + ".Wake"
        self._mutex = None
        self._event = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def acquire(self) -> bool:
        self._mutex = kernel32.CreateMutexW(None, False, self._mutex_name)
        if not self._mutex:
            return True  # 创建失败时不阻止启动
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(self._mutex)
            self._mutex = None
            return False
        self._event = kernel32.CreateEventW(None, False, False, self._event_name)
        return True

    def signal_existing(self) -> bool:
        handle = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, self._event_name)
        if not handle:
            return False
        try:
            return bool(kernel32.SetEvent(handle))
        finally:
            kernel32.CloseHandle(handle)

    def listen(self, on_wake, interval_ms: int = 250) -> None:
        """在后台等唤醒信号；收到后交给回调（回调必须自己保证线程安全）。"""
        if not self._event:
            return

        def loop() -> None:
            while not self._stop.is_set():
                rc = kernel32.WaitForSingleObject(self._event, interval_ms)
                if rc == WAIT_OBJECT_0:
                    try:
                        on_wake()
                    except Exception:  # noqa: BLE001
                        pass

        self._thread = threading.Thread(target=loop, daemon=True,
                                        name="clipnest-wake")
        self._thread.start()

    def release(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        for handle in (self._event, self._mutex):
            if handle:
                kernel32.CloseHandle(handle)
        self._event = None
        self._mutex = None
