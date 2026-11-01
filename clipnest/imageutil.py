"""DIB 解码和 PNG 编码。

剪贴板里的位图是 CF_DIB（BITMAPINFOHEADER + 像素数据，没有文件头），
而 tkinter 的 PhotoImage 只认 PNG/GIF，中间得转一道。为此引 Pillow 不划算，
干脆自己拼 PNG 数据块。
"""

from __future__ import annotations

import struct
import zlib

BI_RGB = 0
BI_BITFIELDS = 3

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class DibError(ValueError):
    """DIB 数据无法解析。"""


def _chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def encode_png(width: int, height: int, rgba: bytes, step: int = 1) -> bytes:
    """把 RGBA 字节流编码为 PNG；step>1 时按最近邻降采样（用于缩略图）。"""
    if width <= 0 or height <= 0:
        raise ValueError("width/height must be positive")
    if len(rgba) < width * height * 4:
        raise ValueError("rgba buffer too small")

    step = max(1, int(step))
    out_w = max(1, width // step)
    out_h = max(1, height // step)
    stride = width * 4
    limit = out_w * 4 * step

    raw = bytearray()
    for y in range(out_h):
        src = y * step * stride
        line = rgba[src: src + stride]
        raw.append(0)  # filter type: None
        if step == 1:
            raw += line[:limit]
        else:
            n = out_w * 4
            row = bytearray(n)
            row[0::4] = line[0:limit:4 * step]
            row[1::4] = line[1:limit:4 * step]
            row[2::4] = line[2:limit:4 * step]
            row[3::4] = line[3:limit:4 * step]
            raw += row

    ihdr = struct.pack(">IIBBBBB", out_w, out_h, 8, 6, 0, 0, 0)  # 8bit RGBA
    return (
        PNG_SIGNATURE
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + _chunk(b"IEND", b"")
    )


def decode_dib(dib: bytes) -> tuple[int, int, bytes]:
    """解析 CF_DIB，返回 (width, height, rgba)。"""
    if not dib or len(dib) < 40:
        raise DibError("DIB 数据过短")

    bi_size, bi_width, bi_height, _planes, bit_count, compression = struct.unpack_from(
        "<IiiHHI", dib, 0
    )
    if bi_size < 40 or bi_size > len(dib):
        raise DibError("不支持的 BITMAPINFOHEADER")
    if bi_width <= 0 or bi_width > 20000:
        raise DibError("位图宽度非法")
    if bit_count not in (24, 32):
        raise DibError(f"暂不支持的位深: {bit_count}")
    if compression not in (BI_RGB, BI_BITFIELDS):
        raise DibError(f"暂不支持的压缩方式: {compression}")

    width = bi_width
    top_down = bi_height < 0
    height = abs(bi_height)
    if height > 20000:
        raise DibError("位图高度非法")

    bi_clr_used = struct.unpack_from("<I", dib, 32)[0]
    offset = bi_size
    if compression == BI_BITFIELDS and bi_size == 40:
        offset += 12  # 三个颜色掩码紧随头部
    offset += (bi_clr_used or (1 << bit_count if bit_count <= 8 else 0)) * 4

    stride = ((width * bit_count + 31) // 32) * 4
    if offset + stride * height > len(dib):
        raise DibError("DIB 像素数据不完整")

    rows = []
    has_alpha = False
    for y in range(height):
        src_y = y if top_down else height - 1 - y
        start = offset + src_y * stride
        if bit_count == 32:
            line = dib[start: start + width * 4]
            if not has_alpha and any(line[3::4]):
                has_alpha = True
            rows.append(line)
        else:  # 24bpp BGR -> RGBA
            line = dib[start: start + width * 3]
            row = bytearray(width * 4)
            row[0::4] = line[2::3]  # R
            row[1::4] = line[1::3]  # G
            row[2::4] = line[0::3]  # B
            row[3::4] = b"\xff" * width
            rows.append(bytes(row))

    rgba = bytearray().join(rows)
    if bit_count == 32 and not has_alpha:
        rgba[3::4] = b"\xff" * (width * height)
    return width, height, bytes(rgba)


def dib_to_png(dib: bytes, max_side: int | None = None) -> tuple[bytes, int, int]:
    """CF_DIB -> (png 字节, 输出宽, 输出高)。max_side 用于生成缩略图。"""
    width, height, rgba = decode_dib(dib)
    step = 1
    if max_side and max(width, height) > max_side:
        step = (max(width, height) + max_side - 1) // max_side
    png = encode_png(width, height, rgba, step=step)
    return png, max(1, width // step), max(1, height // step)
