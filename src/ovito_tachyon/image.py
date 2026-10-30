"""Minimal image I/O: read Tachyon's binary PPM output, write PNG (stdlib only)."""

from __future__ import annotations

import struct
import zlib

import numpy as np


def read_ppm(path) -> np.ndarray:
    """Read a binary (P6) PPM file into an ``(height, width, 3)`` uint8/uint16 array."""
    with open(path, "rb") as f:
        data = f.read()
    tokens: list[bytes] = []
    pos = 0
    while len(tokens) < 4:
        while data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b"#":
            pos = data.index(b"\n", pos) + 1
            continue
        end = pos
        while not data[end:end + 1].isspace():
            end += 1
        tokens.append(data[pos:end])
        pos = end
    pos += 1  # single whitespace byte after maxval
    magic, w, h, maxval = tokens[0], int(tokens[1]), int(tokens[2]), int(tokens[3])
    if magic != b"P6":
        raise ValueError(f"unsupported PPM variant {magic!r}")
    dtype = np.dtype(">u2") if maxval > 255 else np.uint8
    img = np.frombuffer(data, dtype=dtype, count=w * h * 3, offset=pos)
    return img.reshape(h, w, 3).astype(np.uint16 if maxval > 255 else np.uint8)


def write_png(path, image: np.ndarray) -> None:
    """Write an ``(h, w, 3)`` or ``(h, w, 4)`` uint8 array as PNG."""
    img = np.ascontiguousarray(image)
    if img.dtype != np.uint8:
        raise TypeError("write_png expects uint8 data")
    h, w, ch = img.shape
    color_type = {3: 2, 4: 6}[ch]
    raw = np.empty((h, 1 + w * ch), dtype=np.uint8)
    raw[:, 0] = 0  # filter type: None
    raw[:, 1:] = img.reshape(h, w * ch)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(raw.tobytes(), 6)))
        f.write(chunk(b"IEND", b""))
