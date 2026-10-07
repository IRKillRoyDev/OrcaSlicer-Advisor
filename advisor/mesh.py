"""Bounding box and triangle count for an STL file."""

from __future__ import annotations

import struct
from pathlib import Path


def _is_ascii_stl(data: bytes) -> bool:
    if data[:5].lower() != b"solid":
        return False
    if len(data) < 84:
        return True
    count = struct.unpack_from("<I", data, 80)[0]
    expected = 84 + count * 50
    if count > 0 and abs(len(data) - expected) < 8:
        return False
    head = data[:1000].lower()
    return b"facet" in head or b"vertex" in head


def mesh_stats(path: Path) -> dict:
    data = path.read_bytes()
    if not data:
        raise ValueError("STL file is empty")
    if _is_ascii_stl(data):
        verts = []
        for line in data.decode("utf-8", errors="ignore").splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0].lower() == "vertex":
                verts.append(tuple(float(part) for part in parts[1:4]))
        triangles = len(verts) // 3
    else:
        if len(data) < 84:
            raise ValueError("STL file is too small")
        triangles = struct.unpack_from("<I", data, 80)[0]
        expected = 84 + triangles * 50
        if triangles < 1 or len(data) < expected:
            raise ValueError("STL triangle count does not match the file size")
        verts = []
        offset = 84
        for _ in range(triangles):
            nums = struct.unpack_from("<12fH", data, offset)
            verts.extend((nums[3:6], nums[6:9], nums[9:12]))
            offset += 50
    if not verts:
        raise ValueError("STL has no vertices")
    xs = [vert[0] for vert in verts]
    ys = [vert[1] for vert in verts]
    zs = [vert[2] for vert in verts]
    return {
        "filename": path.name,
        "triangles": triangles,
        "size_mm": [
            round(max(xs) - min(xs), 2),
            round(max(ys) - min(ys), 2),
            round(max(zs) - min(zs), 2),
        ],
    }
