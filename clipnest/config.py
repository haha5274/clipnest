"""配置持久化：存放在 %APPDATA%\\ClipNest\\config.json。"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

APP_NAME = "ClipNest"


def data_dir() -> Path:
    """返回应用数据目录，不存在则创建。"""
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    d = root / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class Config:
    hotkey: str = "ctrl+alt+v"
    max_items: int = 500          # 非置顶条目的最大保留数量
    poll_interval_ms: int = 250   # 剪贴板轮询间隔
    max_text_kb: int = 512        # 超过该大小的文本不记录
    capture_images: bool = True
    dark: bool = False

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        path = path or (data_dir() / "config.json")
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self, path: Path | None = None) -> None:
        path = path or (data_dir() / "config.json")
        try:
            path.write_text(
                json.dumps(asdict(self), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass


def db_path() -> Path:
    return data_dir() / "clipnest.db"
