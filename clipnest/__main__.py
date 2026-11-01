"""命令行入口：python -m clipnest [--hidden] [--db PATH]"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="clipnest",
        description="ClipNest：Windows 剪贴板历史管理器",
    )
    parser.add_argument("--hidden", action="store_true",
                        help="启动后不显示窗口，按全局热键呼出")
    parser.add_argument("--db", default=None, help="自定义数据库文件路径")
    args = parser.parse_args(argv)

    if not sys.platform.startswith("win"):
        print("ClipNest 目前仅支持 Windows（依赖 Win32 剪贴板 API）。")
        return 2
    try:
        from .app import run
    except ImportError as exc:  # tkinter 缺失
        print(f"启动失败：{exc}\n请安装带 tkinter 的 Python（python.org 官方安装包默认包含）。")
        return 3
    return run(hidden=args.hidden, db_file=args.db)


if __name__ == "__main__":
    raise SystemExit(main())
