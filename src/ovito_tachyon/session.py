"""Read particle type names, colors and radii from OVITO session files (.ovito).

OVITO's Python module refuses to load session states saved by OVITO Basic, so this decodes the object stream
directly. It understands the layout of OVITO 3.x up to 3.10 (positional field chunks) and that of 3.15 and later
(tagged fields), and decodes only ParticleType objects and the type edits of "Edit types" modifiers.
"""

from __future__ import annotations

import struct
from pathlib import Path

_END = 0x0FFFFFFF


class SessionFormatError(ValueError):
    pass


class _Reader:
    def __init__(self, data: bytes, pos: int = 0):
        self.data, self.pos = data, pos

    def u32(self) -> int:
        (value,) = struct.unpack_from(">I", self.data, self.pos)
        self.pos += 4
        return value

    def i64(self) -> int:
        (value,) = struct.unpack_from(">q", self.data, self.pos)
        self.pos += 8
        return value

    def u8(self) -> int:
        value = self.data[self.pos]
        self.pos += 1
        return value

    def raw(self, n: int) -> bytes:
        value = self.data[self.pos:self.pos + n]
        self.pos += n
        return value

    def qstring(self) -> str | None:
        n = self.u32()
        return None if n == 0xFFFFFFFF else self.raw(n).decode("utf-16-be")

    def qbytes(self) -> bytes:
        n = self.u32()
        return b"" if n == 0xFFFFFFFF else self.raw(n)

    def end(self) -> None:
        if self.u32() != _END:
            raise SessionFormatError(f"missing chunk end marker before offset {self.pos}")

    def rtti(self) -> str:
        """Class reference of the 3.0-3.10 layout: chunk with plugin and class name."""
        if self.u32() != 0x10000000:
            raise SessionFormatError("unexpected class reference")
        self.u32()
        self.qstring()
        name = self.qstring()
        self.end()
        return name


def _tagged_objects(data: bytes):
    """OVITO 3.15+: field table, class table and object table; objects store (field id, size, value) records."""
    ft, nf, ct, nc, ot, no = struct.unpack_from(">qIqIqI", data, len(data) - 36)
    r = _Reader(data, ct + 8)
    classes = []
    for _ in range(nc):
        r.u32()
        size = r.u32()
        start = r.pos
        classes.append(r.qbytes().decode())
        r.pos = start + size
    r.pos = ft + 8
    fields = []
    for _ in range(nf):
        r.u32()
        fields.append(r.qbytes().decode())
        r.u32()
        if r.u8():
            r.u32()
    r.pos = ot + 8
    table = [(r.u32(), r.u32(), r.i64()) for _ in range(no)]
    bounds = sorted({offset for _, _, offset in table} | {ft})
    for oid, cls, offset in table:
        limit = bounds[bounds.index(offset) + 1]
        r.pos, values = offset, {}
        while r.pos + 8 <= limit:
            fid, size = r.u32(), r.u32()
            if fid == 0 or fid > nf:
                break
            values[fields[fid - 1]] = r.raw(size)
        yield oid, classes[cls - 1], values


def _chunked_objects(data: bytes):
    """OVITO 3.0-3.10: class table lists each class's fields; objects store one chunk per field, in that order."""
    ct, nc, ot, no = struct.unpack_from(">qIqI", data, len(data) - 24)
    r = _Reader(data, ct + 8)
    classes = []
    for _ in range(nc):
        r.u32()
        r.u32()
        name = r.rtti()
        r.end()
        r.u32()
        r.u32()
        fields = []
        while True:
            chunk = r.u32()
            r.u32()
            if chunk == 0:
                r.end()
                break
            fields.append(r.qbytes().decode())
            r.rtti()
            r.u32()
            if r.u8():
                r.rtti()
            r.end()
        r.end()
        classes.append((name, fields))
    r.pos = ot + 8
    table = [(r.u32(), r.i64()) for _ in range(no)]
    for index, (cls, offset) in enumerate(table):
        name, fields = classes[cls]
        values = {}
        if name == "ParticleType":
            r.pos = offset
            for field in fields:
                r.u32()
                values[field] = r.raw(r.u32())
                r.end()
        yield index + 1, name, values


def _objects(data: bytes):
    if len(data) < 64 or data[:8] != bytes.fromhex("0facc5ab0afcca5a"):
        raise SessionFormatError("not an OVITO session file")
    ft, _, ct, _, ot, _ = struct.unpack_from(">qIqIqI", data, len(data) - 36)
    if all(0 < p < len(data) - 8 for p in (ft, ct, ot)) and \
            [data[p:p + 4] for p in (ft, ct, ot)] == [b"\0\0\x01\x01", b"\0\0\x02\0", b"\0\0\x03\0"]:
        return _tagged_objects(data)
    return _chunked_objects(data)


def _double_triple(raw: bytes):
    if len(raw) == 24:
        return struct.unpack(">3d", raw)
    if len(raw) == 12:
        return struct.unpack(">3f", raw)
    return None


def _number(raw: bytes):
    if len(raw) == 8:
        return struct.unpack(">d", raw)[0]
    if len(raw) == 4:
        return struct.unpack(">f", raw)[0]
    return None


def read_particle_types(path) -> dict[int, tuple[str | None, tuple[float, float, float], float | None]]:
    """Particle types in an .ovito file: ``{id: (name or None, (r, g, b), radius or None)}``.

    Where OVITO keeps user edits apart from the loaded types (the editable copies of 3.10 and earlier, or an
    "Edit types" modifier in later versions), the edited values win. A radius of None means OVITO's default.
    """
    data = Path(path).read_bytes()
    try:
        objects = list(_objects(data))
    except (struct.error, IndexError, UnicodeDecodeError) as exc:
        raise SessionFormatError(f"unsupported .ovito file: {exc}") from exc

    edited = set()
    for _, cls, values in objects:
        if cls == "EditTypesModifier" and values.get("isEnabled", b"\x01") != b"\x00":
            raw = values.get("editedTypes", b"")
            if len(raw) >= 4:
                count = struct.unpack_from(">I", raw)[0]
                edited.update(struct.unpack_from(f">{count}I", raw, 4))
        elif cls == "ParticleType" and len(values.get("editableProxy", b"")) == 4:
            edited.add(struct.unpack(">I", values["editableProxy"])[0])

    types: dict[int, tuple] = {}
    for oid, cls, values in objects:
        if cls != "ParticleType" or "numericId" not in values:
            continue
        color = _double_triple(values.get("color", b""))
        if color is None:
            continue
        tid = struct.unpack(">i", values["numericId"])[0]
        if tid in types and oid not in edited:
            continue
        name = _Reader(values["name"]).qstring() if len(values.get("name", b"")) >= 4 else None
        radius = _number(values.get("radius", b""))
        types[tid] = (name or None, tuple(min(max(c, 0.0), 1.0) for c in color), radius if radius else None)
    if not types:
        raise SessionFormatError("no particle types found in the .ovito file")
    return dict(sorted(types.items()))
