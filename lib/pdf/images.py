"""
Images for a PDF, from the file's bytes and with the standard library.

JPEG goes in as it is. PNG goes in as it is too, unless it has transparency: PDF wants that as a
separate mask, so such files are unpacked first. Other formats return None: list them by name.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from typing import List, Optional

_PNG = b"\x89PNG\r\n\x1a\n"
# Unpacking in Python takes a while: larger images with transparency are listed by name.
MAX_UNPACKED_PIXELS = 12_000_000
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


@dataclass(frozen=True, eq=False)
class Image:
    width: int
    height: int
    color_space: str
    bits: int
    # The rest of the image's dictionary: its compression and how to read it.
    extra: str
    data: bytes
    mask: Optional[bytes] = None


def load_image(data: bytes) -> Optional[Image]:
    """The image, or None if it is a format or a shape PDF files here cannot hold."""

    try:
        if data.startswith(_PNG):
            return _load_png(data)
        if data.startswith(b"\xff\xd8"):
            return _load_jpeg(data)
    except (ValueError, IndexError, struct.error, zlib.error):
        return None
    return None


def _load_jpeg(data: bytes) -> Optional[Image]:
    position = 2
    while position + 9 < len(data):
        if data[position] != 0xFF:
            return None
        marker = data[position + 1]
        if marker == 0xFF:  # padding before a marker
            position += 1
            continue
        length = struct.unpack(">H", data[position + 2 : position + 4])[0]
        # The frame headers; 0xC4, 0xC8 and 0xCC share the range but are not frames.
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            bits, height, width, components = struct.unpack(
                ">BHHB", data[position + 4 : position + 10]
            )
            spaces = {1: "/DeviceGray", 3: "/DeviceRGB", 4: "/DeviceCMYK"}
            if components not in spaces or not width or not height:
                return None
            # CMYK JPEGs are stored inverted.
            decode = " /Decode [1 0 1 0 1 0 1 0]" if components == 4 else ""
            return Image(
                width, height, spaces[components], bits, f" /Filter /DCTDecode{decode}", data
            )
        position += 2 + length
    return None


def _load_png(data: bytes) -> Optional[Image]:
    position = len(_PNG)
    header = None
    palette = b""
    packed: List[bytes] = []
    while position + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[position : position + 8])
        chunk = data[position + 8 : position + 8 + length]
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", chunk)
        elif kind == b"PLTE":
            palette = chunk
        elif kind == b"IDAT":
            packed.append(chunk)
        elif kind == b"IEND":
            break
        position += 12 + length
    if header is None or not packed:
        return None

    width, height, bits, color, _, _, interlace = header
    if interlace or color not in _CHANNELS or not width or not height:
        return None
    compressed = b"".join(packed)

    if color in (4, 6):
        return _with_mask(width, height, bits, color, compressed)
    channels = _CHANNELS[color]
    space = {0: "/DeviceGray", 2: "/DeviceRGB"}.get(color)
    if color == 3:
        if not palette:
            return None
        space = f"[/Indexed /DeviceRGB {len(palette) // 3 - 1} <{palette.hex()}>]"
    # PDF reads PNG's own compression directly, so nothing is unpacked.
    extra = (
        " /Filter /FlateDecode /DecodeParms << /Predictor 15"
        f" /Colors {channels} /BitsPerComponent {bits} /Columns {width} >>"
    )
    return Image(width, height, str(space), bits, extra, compressed)


def _with_mask(
    width: int, height: int, bits: int, color: int, compressed: bytes
) -> Optional[Image]:
    if bits != 8 or width * height > MAX_UNPACKED_PIXELS:
        return None
    channels = _CHANNELS[color]
    pixels = _unfilter(zlib.decompress(compressed), width, height, channels)
    mask = bytes(pixels[channels - 1 :: channels])
    del pixels[channels - 1 :: channels]
    space = "/DeviceRGB" if color == 6 else "/DeviceGray"
    return Image(
        width,
        height,
        space,
        8,
        " /Filter /FlateDecode",
        zlib.compress(bytes(pixels), 6),
        zlib.compress(mask, 6),
    )


def _unfilter(raw: bytes, width: int, height: int, step: int) -> bytearray:
    """PNG's per-row filters undone, for 8-bit pixels of `step` bytes."""

    stride = width * step
    if len(raw) < (stride + 1) * height:
        raise ValueError("The image data is too short.")
    output = bytearray(stride * height)
    previous = bytearray(stride)
    source = 0
    target = 0
    for _ in range(height):
        kind = raw[source]
        row = bytearray(raw[source + 1 : source + 1 + stride])
        source += stride + 1
        if kind == 1:
            for index in range(step, stride):
                row[index] = (row[index] + row[index - step]) & 0xFF
        elif kind == 2:
            row = bytearray((a + b) & 0xFF for a, b in zip(row, previous))
        elif kind == 3:
            for index in range(stride):
                left = row[index - step] if index >= step else 0
                row[index] = (row[index] + (left + previous[index]) // 2) & 0xFF
        elif kind == 4:
            for index in range(stride):
                left = row[index - step] if index >= step else 0
                above = previous[index]
                corner = previous[index - step] if index >= step else 0
                estimate = left + above - corner
                to_left, to_above, to_corner = (
                    abs(estimate - left),
                    abs(estimate - above),
                    abs(estimate - corner),
                )
                if to_left <= to_above and to_left <= to_corner:
                    best = left
                elif to_above <= to_corner:
                    best = above
                else:
                    best = corner
                row[index] = (row[index] + best) & 0xFF
        elif kind != 0:
            raise ValueError("Unknown PNG filter.")
        output[target : target + stride] = row
        target += stride
        previous = row
    return output
