"""双击启动（无控制台窗口）。"""

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from clipnest.__main__ import main  # noqa: E402


def report(exc: BaseException) -> None:
    """打包成 exe 后没有控制台，出错要弹窗，否则用户只看到什么也没发生。"""
    detail = "".join(traceback.format_exception(exc))[-1500:]
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("ClipNest 启动失败", f"{exc}\n\n{detail}")
        root.destroy()
    except Exception:
        pass


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - 兜底弹窗
        report(exc)
        sys.exit(1)
