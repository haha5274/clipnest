"""SQLite 存储层。"""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import time
import zlib
from pathlib import Path

from .search import rank

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT    NOT NULL,           -- 'text' | 'image' | 'files' | 'rich'
    content    TEXT    NOT NULL,           -- 文本内容 / 图片占位描述 / 文件路径
    preview    TEXT    NOT NULL DEFAULT '',
    payload    BLOB,                       -- 图片 PNG；文件与富文本是 zlib 压缩的 JSON
    thumb      BLOB,                       -- 列表用极小缩略图
    dib        BLOB,                       -- 原始 CF_DIB，用于回写剪贴板
    width      INTEGER,
    height     INTEGER,
    hash       TEXT    NOT NULL UNIQUE,
    pinned     INTEGER NOT NULL DEFAULT 0,
    ts         REAL    NOT NULL,           -- 最近使用时间（epoch 秒）
    use_count  INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_items_ts ON items(pinned DESC, ts DESC);
"""


def pack(obj: object) -> bytes:
    return zlib.compress(json.dumps(obj, ensure_ascii=False).encode("utf-8"), 6)


def unpack(blob: bytes | None) -> dict:
    if not blob:
        return {}
    try:
        return json.loads(zlib.decompress(blob).decode("utf-8"))
    except (zlib.error, ValueError):
        return {}


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    # ---------------------------------------------------------------- 写入
    def _upsert(self, kind: str, content: str, preview: str, hash_: str,
                payload: bytes | None = None, thumb: bytes | None = None,
                dib: bytes | None = None, width: int | None = None,
                height: int | None = None) -> int:
        now = time.time()
        self.db.execute(
            """
            INSERT INTO items (kind, content, preview, payload, thumb, dib,
                               width, height, hash, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(hash) DO UPDATE SET
                ts = excluded.ts,
                use_count = items.use_count + 1
            """,
            (kind, content, preview, payload, thumb, dib, width, height, hash_, now),
        )
        self.db.commit()
        row = self.db.execute("SELECT id FROM items WHERE hash = ?", (hash_,)).fetchone()
        return int(row["id"])

    def add_text(self, text: str) -> int | None:
        if not text or not text.strip():
            return None
        hash_ = "t:" + hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()
        preview = " ".join(text.split())
        return self._upsert("text", text, preview, hash_)

    def add_image(self, dib: bytes, png: bytes, thumb: bytes,
                  width: int, height: int) -> int | None:
        if not png:
            return None
        hash_ = "i:" + hashlib.sha256(png).hexdigest()
        content = f"图片 {width}x{height}"
        return self._upsert("image", content, content, hash_,
                            payload=png, thumb=thumb, dib=dib,
                            width=width, height=height)

    def add_files(self, paths: list[str]) -> int | None:
        if not paths:
            return None
        blob = pack({"paths": paths})
        hash_ = "f:" + hashlib.sha256("\x00".join(paths).encode("utf-8", "ignore")).hexdigest()
        names = [Path(p).name or p for p in paths]
        preview = "、".join(names[:4]) + (f" 等 {len(names)} 个文件" if len(names) > 4
                                         else f"（{len(names)} 个文件）")
        return self._upsert("files", "\n".join(paths), preview, hash_, payload=blob)

    def add_rich(self, text: str | None, html: bytes | None, rtf: bytes | None,
                 preview: str) -> int | None:
        if not (text or html or rtf):
            return None
        blob = pack({
            "text": text,
            "html": base64.b64encode(html).decode("ascii") if html else None,
            "rtf": base64.b64encode(rtf).decode("ascii") if rtf else None,
        })
        hash_ = "r:" + hashlib.sha256(blob).hexdigest()
        preview = " ".join(preview.split())[:400]
        return self._upsert("rich", text or preview, preview, hash_, payload=blob)

    def touch(self, item_id: int) -> None:
        self.db.execute(
            "UPDATE items SET ts = ?, use_count = use_count + 1 WHERE id = ?",
            (time.time(), item_id),
        )
        self.db.commit()

    def set_pinned(self, item_id: int, pinned: bool) -> None:
        self.db.execute("UPDATE items SET pinned = ? WHERE id = ?",
                        (1 if pinned else 0, item_id))
        self.db.commit()

    def delete(self, item_id: int) -> None:
        self.db.execute("DELETE FROM items WHERE id = ?", (item_id,))
        self.db.commit()

    def clear(self, keep_pinned: bool = True) -> int:
        sql = "DELETE FROM items WHERE pinned = 0" if keep_pinned else "DELETE FROM items"
        cur = self.db.execute(sql)
        self.db.commit()
        return cur.rowcount

    def trim(self, max_items: int) -> int:
        """只保留最近 max_items 条非置顶记录。"""
        row = self.db.execute(
            "SELECT COUNT(*) AS n FROM items WHERE pinned = 0").fetchone()
        extra = int(row["n"]) - max_items
        if extra <= 0:
            return 0
        cur = self.db.execute(
            """DELETE FROM items WHERE id IN (
                   SELECT id FROM items WHERE pinned = 0 ORDER BY ts ASC LIMIT ?
               )""",
            (extra,),
        )
        self.db.commit()
        return cur.rowcount

    # ---------------------------------------------------------------- 读取
    def get(self, item_id: int) -> dict | None:
        row = self.db.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        return dict(row) if row else None

    def list(self, query: str = "", limit: int = 200) -> list[dict]:
        rows = self.db.execute(
            """SELECT * FROM items
               ORDER BY pinned DESC, ts DESC
               LIMIT ?""",
            (2000 if query else limit,),
        ).fetchall()
        items = [dict(r) for r in rows]
        if query:
            items = rank(items, query)[:limit]
        return items

    def counts(self) -> tuple[int, int]:
        row = self.db.execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(pinned), 0) AS pinned FROM items"
        ).fetchone()
        return int(row["total"]), int(row["pinned"])

    def close(self) -> None:
        try:
            self.db.close()
        except sqlite3.Error:
            pass
