"""给候选项打分。

按 前缀 > 子串 > 词边界 > 多词命中 > 子序列 逐级降级。中文靠连续子串匹配，
英文则允许空格分词。
"""

from __future__ import annotations


def _is_subsequence(needle: str, haystack: str) -> bool:
    it = iter(haystack)
    return all(ch in it for ch in needle)


def score(query: str, text: str) -> float | None:
    """返回 0~1 的匹配分；不匹配返回 None。空查询视为全匹配。"""
    q = query.strip().lower()
    if not q:
        return 1.0
    if not text:
        return None

    t = text.lower()
    if t.startswith(q):
        return 1.0

    idx = t.find(q)
    if idx >= 0:
        base = 0.82 if idx < 30 else 0.66
        prev = t[idx - 1]
        if not (prev.isalnum() or prev == "_"):
            base += 0.08  # 命中词边界
        return min(base, 0.98)

    tokens = q.split()
    if len(tokens) > 1 and all(tok in t for tok in tokens):
        return 0.5

    if _is_subsequence(q.replace(" ", ""), t):
        return 0.28

    return None


def rank(items: list[dict], query: str, limit: int = 200) -> list[dict]:
    """按匹配分降序 + 时间降序排序；置顶项保留轻微加成。"""
    scored = []
    for item in items:
        s = score(query, item.get("content", ""))
        if s is None:
            s = score(query, item.get("preview", ""))
        if s is None:
            continue
        if item.get("pinned"):
            s += 0.05
        scored.append((s, item.get("ts", 0), item))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [it for _, _, it in scored[:limit]]
