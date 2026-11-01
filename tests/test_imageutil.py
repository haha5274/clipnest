"""图片编解码测试：构造合成 DIB，验证解码与 PNG 编码。"""

from __future__ import annotations

import struct
import sys
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clipnest.imageutil import DibError, decode_dib, dib_to_png, encode_png  # noqa: E402
from clipnest.imageutil import PNG_SIGNATURE  # noqa: E402


def make_dib(width: int, height: int, bit_count: int = 24,
             top_down: bool = False) -> bytes:
    """构造一个从左到右颜色渐变的 DIB（BGR 顺序）。"""
    stride = ((width * bit_count + 31) // 32) * 4
    bi_height = -height if top_down else height
    header = struct.pack("<IiiHHIIiiII", 40, width, bi_height, 1, bit_count, 0,
                         stride * height, 2835, 2835, 0, 0)
    body = bytearray()
    for _ in range(height):
        row = bytearray()
        for x in range(width):
            b = x % 256
            row += bytes((b, 128, 255 - b))  # B, G, R
        row += b"\x00" * (stride - len(row))
        body += row
    return header + bytes(body)


class DecodeTests(unittest.TestCase):
    def test_24bit_bottom_up(self) -> None:
        dib = make_dib(4, 3, 24)
        w, h, rgba = decode_dib(dib)
        self.assertEqual((w, h), (4, 3))
        self.assertEqual(len(rgba), 4 * 3 * 4)
        # 第一行像素：DIB 自下而上存储，解码后应上下翻转
        self.assertEqual(tuple(rgba[0:4]), (255, 128, 0, 255))
        self.assertEqual(tuple(rgba[4:8]), (254, 128, 1, 255))

    def test_24bit_top_down_matches(self) -> None:
        bottom = decode_dib(make_dib(5, 2, 24))[2]
        top = decode_dib(make_dib(5, 2, 24, top_down=True))[2]
        self.assertEqual(bottom, top)

    def test_32bit_opaque_gets_alpha(self) -> None:
        width, height = 2, 2
        header = struct.pack("<IiiHHIIiiII", 40, width, -height, 1, 32, 0,
                             0, 2835, 2835, 0, 0)
        pixels = bytes([1, 2, 3, 0] * (width * height))
        w, h, rgba = decode_dib(header + pixels)
        self.assertEqual((w, h), (width, height))
        self.assertEqual(rgba[3::4], b"\xff" * (width * height))

    def test_rejects_garbage(self) -> None:
        with self.assertRaises(DibError):
            decode_dib(b"not a dib")
        with self.assertRaises(DibError):
            decode_dib(make_dib(2, 2, 24)[:40])


class PngTests(unittest.TestCase):
    def test_signature_and_size(self) -> None:
        png = encode_png(3, 2, bytes([255, 0, 0, 255]) * 6)
        self.assertTrue(png.startswith(PNG_SIGNATURE))
        iw, ih = struct.unpack(">II", png[16:24])
        self.assertEqual((iw, ih), (3, 2))

    def test_idat_decompresses_to_expected_rows(self) -> None:
        rgba = bytes([10, 20, 30, 40]) * 2
        png = encode_png(2, 1, rgba)
        start = png.index(b"IDAT") + 4
        length = struct.unpack(">I", png[start - 8:start - 4])[0]
        raw = zlib.decompress(png[start:start + length])
        self.assertEqual(raw[0], 0)          # filter type None
        self.assertEqual(raw[1:], rgba)      # 原始像素

    def test_downsample_halves_dimensions(self) -> None:
        rgba = bytes([7, 7, 7, 255]) * (8 * 6)
        png = encode_png(8, 6, rgba, step=2)
        iw, ih = struct.unpack(">II", png[16:24])
        self.assertEqual((iw, ih), (4, 3))

    def test_dib_to_png_thumb(self) -> None:
        dib = make_dib(64, 32, 24)
        png, w, h = dib_to_png(dib, max_side=16)
        self.assertTrue(png.startswith(PNG_SIGNATURE))
        self.assertLessEqual(max(w, h), 16)
        self.assertEqual((w, h), (16, 8))


if __name__ == "__main__":
    unittest.main()
