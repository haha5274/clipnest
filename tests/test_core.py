"""搜索打分与存储层测试。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clipnest.search import rank, score  # noqa: E402
from clipnest.store import Store  # noqa: E402


class ScoreTests(unittest.TestCase):
    def test_empty_query_matches_everything(self) -> None:
        self.assertEqual(score("", "任意内容"), 1.0)
        self.assertEqual(score("   ", "任意内容"), 1.0)

    def test_prefix_beats_substring(self) -> None:
        prefix = score("git", "git config --global user")
        inner = score("git", "install git first")
        self.assertIsNotNone(prefix)
        self.assertIsNotNone(inner)
        self.assertGreater(prefix, inner)

    def test_chinese_substring(self) -> None:
        self.assertIsNotNone(score("剪贴板", "顺手记一下：剪贴板里刚复制的那段话"))

    def test_token_match(self) -> None:
        self.assertIsNotNone(score("pip install", "pip --quiet install requests"))

    def test_subsequence_fallback(self) -> None:
        self.assertIsNotNone(score("cfg", "config.json"))

    def test_no_match(self) -> None:
        self.assertIsNone(score("zzzz", "abcdefg"))

    def test_rank_prefers_pinned_on_tie(self) -> None:
        items = [
            {"content": "hello world", "preview": "", "ts": 1.0, "pinned": 0},
            {"content": "hello there", "preview": "", "ts": 0.5, "pinned": 1},
        ]
        ranked = rank(items, "hello")
        self.assertEqual(ranked[0]["pinned"], 1)


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "test.db")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_add_and_dedupe(self) -> None:
        first = self.store.add_text("hello")
        second = self.store.add_text("hello")
        self.assertEqual(first, second)          # 同内容只存一条
        self.assertEqual(self.store.counts()[0], 1)
        item = self.store.get(first)
        self.assertEqual(item["use_count"], 2)   # 但使用次数累加

    def test_blank_text_ignored(self) -> None:
        self.assertIsNone(self.store.add_text("   \n  "))

    def test_pin_sorts_first(self) -> None:
        a = self.store.add_text("aaa")
        self.store.add_text("bbb")
        self.store.set_pinned(a, True)
        items = self.store.list()
        self.assertEqual(items[0]["id"], a)

    def test_search_filters(self) -> None:
        self.store.add_text("docker compose up")
        self.store.add_text("npm run build")
        items = self.store.list("docker")
        self.assertEqual(len(items), 1)
        self.assertIn("docker", items[0]["content"])

    def test_clear_keeps_pinned(self) -> None:
        a = self.store.add_text("keep me")
        self.store.add_text("drop me")
        self.store.set_pinned(a, True)
        removed = self.store.clear(keep_pinned=True)
        self.assertEqual(removed, 1)
        self.assertEqual(self.store.counts()[0], 1)

    def test_trim_respects_pinned(self) -> None:
        ids = [self.store.add_text(f"item-{i}") for i in range(10)]
        self.store.set_pinned(ids[0], True)
        self.store.trim(3)
        remaining = {i["id"] for i in self.store.list()}
        self.assertIn(ids[0], remaining)
        self.assertEqual(len(remaining), 4)  # 1 置顶 + 3 最新

    def test_touch_moves_to_top(self) -> None:
        first = self.store.add_text("first")
        self.store.add_text("second")
        self.store.touch(first)
        self.assertEqual(self.store.list()[0]["id"], first)


if __name__ == "__main__":
    unittest.main()
