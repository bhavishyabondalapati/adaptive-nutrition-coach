"""Generate the PWA's PNG icons using only the Python standard library.

Draws a green rounded square with a white "trend line", matching favicon.svg.
Run from the project root:  python scripts/make_icons.py
"""

import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "frontend" / "public"
GREEN = (21, 128, 61)
WHITE = (255, 255, 255)
# Trend line in a 64x64 design grid (same as favicon.svg).
POINTS = [(14, 42), (26, 30), (34, 38), (50, 20)]


def dist_to_segment(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def pixel(x, y, size, rounded, inset):
    # Map to the 64-unit design grid; `inset` shrinks the drawing for maskable icons.
    u = (x + 0.5) / size * 64
    v = (y + 0.5) / size * 64
    if rounded:
        r, m = 14, 0
        cx = min(max(u, r + m), 64 - r - m)
        cy = min(max(v, r + m), 64 - r - m)
        if (u - cx) ** 2 + (v - cy) ** 2 > r * r:
            return (0, 0, 0, 0)
    # Scale the line around the centre.
    s = 1 - inset
    lu, lv = 32 + (u - 32) / s, 32 + (v - 32) / s
    d = min(dist_to_segment(lu, lv, *POINTS[i], *POINTS[i + 1]) for i in range(len(POINTS) - 1))
    return (*WHITE, 255) if d <= 3 else (*GREEN, 255)


def write_png(path, size, rounded=True, inset=0.0):
    rows = []
    for y in range(size):
        row = bytearray([0])  # filter type 0
        for x in range(size):
            row.extend(pixel(x, y, size, rounded, inset))
        rows.append(bytes(row))
    raw = zlib.compress(b"".join(rows), 9)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", raw) + chunk(b"IEND", b"")
    path.write_bytes(png)
    print("wrote", path)


if __name__ == "__main__":
    write_png(OUT / "icon-192.png", 192)
    write_png(OUT / "icon-512.png", 512)
    # Maskable icons get cropped to a circle by Android: full bleed + smaller art.
    write_png(OUT / "icon-maskable-512.png", 512, rounded=False, inset=0.3)
    write_png(OUT / "apple-touch-icon.png", 180, rounded=False)
