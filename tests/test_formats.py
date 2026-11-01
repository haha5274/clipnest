"""文件剪贴板、富文本、托盘图标、单实例的测试。"""

from __future__ import annotations

import base64
import ctypes
import struct
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

WINDOWS = sys.platform.startswith("win")

HTML = (
    b"Version:0.9\r\n"
    b"StartHTML:0000000105\r\nEndHTML:0000000200\r\n"
    b"StartFragment:0000000140\r\nEndFragment:0000000170\r\n"
    b"<html><body><!--StartFragment--><b>Hello</b> world"
    b"<!--EndFragment--></body></html>"
)
RTF = rb"{\rtf1\ansi\deff0 {\b Hello} world}"


@unittest.skipUnless(WINDOWS, "仅 Windows 支持")
class FileClipboardTests(unittest.TestCase):
    def test_payload_layout(self) -> None:
        from clipnest import winclip

        data = winclip.files_payload([r"C:\a.txt", r"C:\b.txt"])
        offset, _x, _y, _nc, wide = struct.unpack_from("<IiiII", data, 0)
        self.assertEqual(offset, 20)
        self.assertEqual(wide, 1)
        tail = data[offset:].decode("utf-16-le")
        self.assertEqual(tail, "C:\\a.txt\x00C:\\b.txt\x00\x00")

    def test_roundtrip_through_clipboard(self) -> None:
        from clipnest import winclip

        paths = [r"C:\Users\HAHA\报告 final.txt", r"C:\Users\HAHA\b.png"]
        winclip.write_files(paths)
        self.assertEqual(winclip.read_files(), paths)

    def test_no_files_returns_none(self) -> None:
        from clipnest import winclip

        winclip.write_text("只有文本")
        self.assertIsNone(winclip.read_files())

    def test_empty_file_list_is_ignored(self) -> None:
        from clipnest import winclip

        winclip.write_files([])
        self.assertIsNone(winclip.read_files())


@unittest.skipUnless(WINDOWS, "仅 Windows 支持")
class RichClipboardTests(unittest.TestCase):
    def test_bundle_roundtrip(self) -> None:
        from clipnest import winclip

        winclip.write_bundle("Hello world", HTML, RTF)
        bundle = winclip.read_rich()
        self.assertIsNotNone(bundle)
        self.assertEqual(bundle["html"].rstrip(b"\x00"), HTML)
        self.assertEqual(bundle["rtf"].rstrip(b"\x00"), RTF)
        self.assertEqual(winclip.read_text(), "Hello world")

    def test_plain_text_has_no_rich(self) -> None:
        from clipnest import winclip

        winclip.write_text("纯文本")
        self.assertIsNone(winclip.read_rich())

    def test_write_bundle_without_html(self) -> None:
        from clipnest import winclip

        winclip.write_bundle("只有 Unicode", None, None)
        self.assertEqual(winclip.read_text(), "只有 Unicode")
        self.assertIsNone(winclip.read_rich())

    def test_html_to_text_extracts_fragment(self) -> None:
        from clipnest import winclip

        text = winclip.html_to_text(HTML)
        self.assertIn("Hello", text)
        self.assertIn("world", text)
        self.assertNotIn("<b>", text)

    def test_html_to_text_strips_script(self) -> None:
        from clipnest import winclip

        raw = b"<html><script>alert(1)</script><p>visible</p></html>"
        self.assertEqual(winclip.html_to_text(raw), "visible")

    def test_rtf_to_text(self) -> None:
        from clipnest import winclip

        text = winclip.rtf_to_text(RTF)
        self.assertIn("Hello", text)
        self.assertNotIn("\\rtf1", text)


class StoreFormatTests(unittest.TestCase):
    def setUp(self) -> None:
        from clipnest.store import Store

        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "fmt.db")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_files_stored_and_deduped(self) -> None:
        from clipnest.store import unpack

        paths = [r"C:\x\a.txt", r"C:\x\b.txt"]
        first = self.store.add_files(paths)
        again = self.store.add_files(paths)
        self.assertEqual(first, again)
        self.assertEqual(self.store.counts()[0], 1)
        item = self.store.get(first)
        self.assertEqual(item["kind"], "files")
        self.assertEqual(unpack(item["payload"])["paths"], paths)
        self.assertEqual(item["content"].splitlines(), paths)
        self.assertIn("a.txt", item["preview"])

    def test_files_hash_ignores_duplicate_copies(self) -> None:
        self.store.add_files([r"C:\x\a.txt"])
        self.store.add_files([r"C:\x\a.txt"])
        self.assertEqual(self.store.get(self.store.add_files([r"C:\x\a.txt"]))["use_count"], 3)

    def test_rich_payload_roundtrip(self) -> None:
        from clipnest.store import unpack

        item_id = self.store.add_rich("Hello world", HTML, RTF, "Hello world")
        item = self.store.get(item_id)
        self.assertEqual(item["kind"], "rich")
        data = unpack(item["payload"])
        self.assertEqual(data["text"], "Hello world")
        self.assertEqual(base64.b64decode(data["html"]), HTML)
        self.assertEqual(base64.b64decode(data["rtf"]), RTF)
        self.assertEqual(item["content"], "Hello world")

    def test_rich_without_rtf(self) -> None:
        from clipnest.store import unpack

        item = self.store.get(self.store.add_rich("只 HTML", HTML, None, "只 HTML"))
        self.assertIsNone(unpack(item["payload"])["rtf"])

    def test_rich_requires_some_content(self) -> None:
        self.assertIsNone(self.store.add_rich(None, None, None, ""))

    def test_unpack_survives_garbage(self) -> None:
        from clipnest.store import unpack

        self.assertEqual(unpack(b"not zlib"), {})
        self.assertEqual(unpack(None), {})


@unittest.skipUnless(WINDOWS, "仅 Windows 支持")
class TrayTests(unittest.TestCase):
    def test_icon_bitmap_builds(self) -> None:
        from clipnest import tray

        icon = tray.build_icon()
        self.assertTrue(icon)
        tray.user32.DestroyIcon(icon)

    def test_art_is_square(self) -> None:
        from clipnest.tray import _ART

        self.assertEqual(len(_ART), 16)
        for row in _ART:
            self.assertEqual(len(row), 16)

    def test_notify_icon_data_size(self) -> None:
        from clipnest.tray import NOTIFYICONDATAW

        expected = 976 if ctypes.sizeof(ctypes.c_void_p) == 8 else 956
        self.assertEqual(ctypes.sizeof(NOTIFYICONDATAW), expected)


@unittest.skipUnless(WINDOWS, "仅 Windows 支持")
class SingleInstanceTests(unittest.TestCase):
    def test_second_instance_signals_first(self) -> None:
        from clipnest.instance import SingleInstance

        name = "ClipNestTest_" + uuid.uuid4().hex
        first = SingleInstance(name)
        self.assertTrue(first.acquire())

        second = SingleInstance(name)
        self.assertFalse(second.acquire())

        woke = []
        first.listen(lambda: woke.append(time.time()))
        self.assertTrue(second.signal_existing())

        deadline = time.time() + 3.0
        while time.time() < deadline and not woke:
            time.sleep(0.05)
        self.assertTrue(woke, "第一个实例没有被唤醒")
        first.release()

    def test_release_allows_reacquire(self) -> None:
        from clipnest.instance import SingleInstance

        name = "ClipNestTest_" + uuid.uuid4().hex
        first = SingleInstance(name)
        self.assertTrue(first.acquire())
        first.release()

        again = SingleInstance(name)
        self.assertTrue(again.acquire())
        again.release()


if __name__ == "__main__":
    unittest.main()
