"""UI 集成测试：真实创建 tkinter 窗口，验证搜索、置顶、复制、删除。

非 Windows 或无图形环境时自动跳过。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

WINDOWS = sys.platform.startswith("win")


@unittest.skipUnless(WINDOWS, "仅 Windows 支持")
class AppSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import tkinter as tk

        try:
            cls.root = tk.Tk()
            cls.root.withdraw()
        except Exception as exc:  # noqa: BLE001 - 无显示环境
            raise unittest.SkipTest(f"无可用图形环境: {exc}")

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.root.destroy()
        except Exception:  # noqa: BLE001
            pass

    def setUp(self) -> None:
        import tkinter as tk

        from clipnest.app import ClipNestApp
        from clipnest.config import Config
        from clipnest.store import Store

        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "ui.db")
        self.cfg = Config(poll_interval_ms=10_000)
        self.win = tk.Toplevel(self.root)
        self.app = ClipNestApp(self.win, self.store, self.cfg, autostart=False)
        self.app._pump = lambda: None  # 停掉定时轮询

    def tearDown(self) -> None:
        try:
            self.win.destroy()
        finally:
            self.store.close()
            self.tmp.cleanup()

    def test_rows_follow_store(self) -> None:
        self.store.add_text("alpha")
        self.store.add_text("beta")
        self.app.refresh()
        self.assertEqual(len(self.app.items), 2)
        self.assertEqual(len(self.app.rows), 2)
        self.assertEqual(self.app.sel, 0)

    def test_search_filters_rows(self) -> None:
        self.store.add_text("docker compose up")
        self.store.add_text("npm run build")
        self.app.refresh()
        self.app.var.set("docker")
        self.app.root.update()
        self.assertEqual(len(self.app.items), 1)
        self.assertIn("docker", self.app.items[0]["content"])

    def test_pin_moves_item_to_top(self) -> None:
        first = self.store.add_text("first item")
        self.store.add_text("second item")
        self.app.refresh()
        index = [i["id"] for i in self.app.items].index(first)
        self.app._toggle_pin(index)
        self.app.refresh()
        self.assertEqual(self.app.items[0]["id"], first)
        self.assertEqual(self.store.get(first)["pinned"], 1)

    def test_delete_removes_item(self) -> None:
        self.store.add_text("to be deleted")
        self.app.refresh()
        self.app._delete_selected()
        self.assertEqual(len(self.app.items), 0)

    def test_copy_writes_clipboard(self) -> None:
        from clipnest import winclip

        self.store.add_text("clipboard round trip 中文")
        self.app.refresh()
        self.app._copy_selected()
        self.assertEqual(winclip.read_text(), "clipboard round trip 中文")

    def test_image_row_renders(self) -> None:
        from test_imageutil import make_dib

        from clipnest.imageutil import dib_to_png

        dib = make_dib(40, 24, 24)
        thumb, _, _ = dib_to_png(dib, max_side=32)
        self.store.add_image(dib, thumb, thumb, 40, 24)
        self.app.refresh()
        self.assertEqual(len(self.app.rows), 1)
        self.assertEqual(self.app.items[0]["kind"], "image")

    def test_files_row_renders_and_copies(self) -> None:
        from clipnest import winclip

        path = Path(self.tmp.name) / "note.txt"
        path.write_text("x", encoding="utf-8")
        self.store.add_files([str(path)])
        self.app.refresh()
        self.assertEqual(self.app.items[0]["kind"], "files")
        self.assertEqual(len(self.app.rows), 1)

        self.app._copy_selected()
        self.assertEqual(winclip.read_files(), [str(path)])

    def test_files_copy_skips_missing_paths(self) -> None:
        from clipnest import winclip

        alive = Path(self.tmp.name) / "alive.txt"
        alive.write_text("x", encoding="utf-8")
        gone = Path(self.tmp.name) / "gone.txt"
        self.store.add_files([str(alive), str(gone)])
        self.app.refresh()
        self.app._copy_selected()
        self.assertEqual(winclip.read_files(), [str(alive)])

    def test_rich_row_renders_and_copies(self) -> None:
        from clipnest import winclip

        self.store.add_rich("Hello world", b"<b>Hello</b> world", None, "Hello world")
        self.app.refresh()
        self.assertEqual(self.app.items[0]["kind"], "rich")
        self.assertEqual(len(self.app.rows), 1)

        self.app._copy_selected()
        self.assertEqual(winclip.read_text(), "Hello world")


if __name__ == "__main__":
    unittest.main()
