"""生成 docs/clipnest.ico。

不引第三方库，按几何形状在 4 倍超采样网格上逐点判断覆盖，再缩回目标尺寸。
用法：python tools/make_icon.py
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clipnest.imageutil import encode_png  # noqa: E402

BLUE = (0x2F, 0x6F, 0xED)
WHITE = (0xFF, 0xFF, 0xFF)
SIZES = (16, 24, 32, 48, 64, 128, 256)
SS = 4


def _inside_round_rect(px: float, py: float, x0: float, y0: float,
                       x1: float, y1: float, r: float) -> bool:
    if px < x0 or px > x1 or py < y0 or py > y1:
        return False
    cx = min(max(px, x0 + r), x1 - r)
    cy = min(max(py, y0 + r), y1 - r)
    return (px - cx) ** 2 + (py - cy) ** 2 <= r * r


# 画布用 0~1 归一化坐标，方便按尺寸缩放
BACKDROP = (0.02, 0.02, 0.98, 0.98, 0.22)
BOARD = (0.21, 0.26, 0.79, 0.86, 0.07)
CLIP = (0.395, 0.175, 0.605, 0.315, 0.05)
LINES = (
    (0.32, 0.415, 0.68, 0.472, 0.028),
    (0.32, 0.535, 0.68, 0.592, 0.028),
    (0.32, 0.655, 0.565, 0.712, 0.028),
)

# 16/24 像素下三行细节会糊成一条，换成两行更大的线、板子也让出更多蓝边
BOARD_SMALL = (0.235, 0.285, 0.765, 0.845, 0.06)
CLIP_SMALL = (0.385, 0.17, 0.615, 0.315, 0.05)
LINES_SMALL = (
    (0.335, 0.455, 0.665, 0.545, 0.045),
    (0.335, 0.625, 0.585, 0.715, 0.045),
)


def layout(size: int):
    if size <= 24:
        return BOARD_SMALL, CLIP_SMALL, LINES_SMALL
    return BOARD, CLIP, LINES


def color_at(px: float, py: float, shapes) -> tuple[int, int, int] | None:
    board, clip, lines = shapes
    if _inside_round_rect(px, py, *clip):
        return BLUE
    if any(_inside_round_rect(px, py, *ln) for ln in lines):
        return BLUE
    if _inside_round_rect(px, py, *board):
        return WHITE
    if _inside_round_rect(px, py, *BACKDROP):
        return BLUE
    return None


def render(size: int) -> bytes:
    n = size * SS
    shapes = layout(size)
    out = bytearray(size * size * 4)
    step = 1.0 / n
    for y in range(size):
        for x in range(size):
            counts: dict[tuple[int, int, int], int] = {}
            base_y = y * SS
            base_x = x * SS
            for sy in range(SS):
                py = (base_y + sy + 0.5) * step
                for sx in range(SS):
                    px = (base_x + sx + 0.5) * step
                    c = color_at(px, py, shapes)
                    if c is not None:
                        counts[c] = counts.get(c, 0) + 1
            if not counts:
                continue
            hits = sum(counts.values())
            off = (y * size + x) * 4
            out[off] = sum(c[0] * k for c, k in counts.items()) // hits
            out[off + 1] = sum(c[1] * k for c, k in counts.items()) // hits
            out[off + 2] = sum(c[2] * k for c, k in counts.items()) // hits
            out[off + 3] = round(255 * hits / (SS * SS))
    return bytes(out)


def _bmp_entry(size: int, rgba: bytes) -> bytes:
    pixels = bytearray()
    for y in range(size - 1, -1, -1):
        row = rgba[y * size * 4:(y + 1) * size * 4]
        for x in range(size):
            r, g, b, a = row[x * 4:x * 4 + 4]
            pixels += bytes((b, g, r, a))

    mask_stride = ((size + 31) // 32) * 4
    mask = bytearray()
    for y in range(size - 1, -1, -1):
        bits = bytearray(mask_stride)
        for x in range(size):
            if rgba[(y * size + x) * 4 + 3] == 0:
                bits[x // 8] |= 0x80 >> (x % 8)
        mask += bits

    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0,
                         len(pixels) + len(mask), 0, 0, 0, 0)
    return header + bytes(pixels) + bytes(mask)


def build_ico(images: list[tuple[int, bytes]]) -> bytes:
    head = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    body = b""
    for size, rgba in images:
        if size >= 256:
            # 256 档按惯例存 PNG，否则单个条目就是 256KB 的裸位图
            entry = encode_png(size, size, rgba)
            dim = 0
        else:
            entry = _bmp_entry(size, rgba)
            dim = size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32,
                               len(entry), offset + len(body))
        body += entry
    return head + entries + body


def main() -> None:
    images = []
    for size in SIZES:
        rgba = render(size)
        images.append((size, rgba))
        print(f"  {size}x{size} ok")

    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    ico = build_ico(images)
    (docs / "clipnest.ico").write_bytes(ico)
    print(f"写出 docs/clipnest.ico  {len(ico)} 字节")

    preview = render(128)
    (docs / "icon-preview.png").write_bytes(encode_png(128, 128, preview))
    print("写出 docs/icon-preview.png")


if __name__ == "__main__":
    main()
