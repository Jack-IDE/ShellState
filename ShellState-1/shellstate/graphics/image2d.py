"""Very small stdlib-only 2D image helpers for the graphics subsystem."""
from __future__ import annotations

import math
from typing import Iterable, List, Sequence, Tuple

ColorF = Tuple[float, float, float]
Color8 = Tuple[int, int, int]

def _clamp01(v: float) -> float:
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else float(v)

def rgb8(color: Sequence[float]) -> Color8:
    r, g, b = (float(color[0]), float(color[1]), float(color[2]))
    return (
        max(0, min(255, int(round(_clamp01(r) * 255.0)))),
        max(0, min(255, int(round(_clamp01(g) * 255.0)))),
        max(0, min(255, int(round(_clamp01(b) * 255.0)))),
    )

class Canvas2D:
    def __init__(self, width: int, height: int, bg: Sequence[float] = (0.0, 0.0, 0.0)):
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self._pixels: List[List[Color8]] = [[rgb8(bg) for _ in range(self.width)] for _ in range(self.height)]

    def fill(self, color: Sequence[float]) -> None:
        c = rgb8(color)
        for y in range(self.height):
            row = self._pixels[y]
            for x in range(self.width):
                row[x] = c

    def set_pixel(self, x: int, y: int, color: Sequence[float]) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self._pixels[y][x] = rgb8(color)

    def blend_pixel(self, x: int, y: int, color: Sequence[float], alpha: float) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        alpha = _clamp01(alpha)
        src = rgb8(color)
        dst = self._pixels[y][x]
        self._pixels[y][x] = (
            int(round(dst[0] * (1.0 - alpha) + src[0] * alpha)),
            int(round(dst[1] * (1.0 - alpha) + src[1] * alpha)),
            int(round(dst[2] * (1.0 - alpha) + src[2] * alpha)),
        )

    def gradient_vertical(self, top: Sequence[float], bottom: Sequence[float]) -> None:
        top8 = rgb8(top)
        bot8 = rgb8(bottom)
        denom = max(1, self.height - 1)
        for y in range(self.height):
            t = y / denom
            color = (
                int(round(top8[0] * (1.0 - t) + bot8[0] * t)),
                int(round(top8[1] * (1.0 - t) + bot8[1] * t)),
                int(round(top8[2] * (1.0 - t) + bot8[2] * t)),
            )
            self._pixels[y] = [color for _ in range(self.width)]

    def rect(self, x: int, y: int, w: int, h: int, color: Sequence[float], fill: bool = True) -> None:
        if w <= 0 or h <= 0:
            return
        c = rgb8(color)
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(self.width, int(x + w))
        y1 = min(self.height, int(y + h))
        if fill:
            for py in range(y0, y1):
                row = self._pixels[py]
                for px in range(x0, x1):
                    row[px] = c
        else:
            for px in range(x0, x1):
                self.set_pixel(px, y0, c)
                self.set_pixel(px, y1 - 1, c)
            for py in range(y0, y1):
                self.set_pixel(x0, py, c)
                self.set_pixel(x1 - 1, py, c)

    def line(self, x0: float, y0: float, x1: float, y1: float, color: Sequence[float], thickness: int = 1) -> None:
        thickness = max(1, int(thickness))
        steps = max(abs(int(x1 - x0)), abs(int(y1 - y0)), 1)
        for i in range(steps + 1):
            t = i / steps
            x = int(round(x0 * (1.0 - t) + x1 * t))
            y = int(round(y0 * (1.0 - t) + y1 * t))
            radius = max(0, thickness // 2)
            for oy in range(-radius, radius + 1):
                for ox in range(-radius, radius + 1):
                    self.set_pixel(x + ox, y + oy, color)

    def circle(self, cx: float, cy: float, radius: float, color: Sequence[float], fill: bool = True) -> None:
        if radius <= 0:
            return
        c = rgb8(color)
        r = float(radius)
        x0 = max(0, int(math.floor(cx - r - 1)))
        x1 = min(self.width - 1, int(math.ceil(cx + r + 1)))
        y0 = max(0, int(math.floor(cy - r - 1)))
        y1 = min(self.height - 1, int(math.ceil(cy + r + 1)))
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                dx = x - cx
                dy = y - cy
                d2 = dx * dx + dy * dy
                if fill:
                    if d2 <= r * r:
                        self._pixels[y][x] = c
                else:
                    if abs(math.sqrt(d2) - r) <= 1.25:
                        self._pixels[y][x] = c

    def rows(self) -> List[List[Color8]]:
        return [row[:] for row in self._pixels]

def render_demo_poster(width: int = 256, height: int = 144, title: str = 'ShellState Graphics') -> List[List[Color8]]:
    canvas = Canvas2D(width, height)
    canvas.gradient_vertical((0.04, 0.05, 0.08), (0.12, 0.15, 0.22))
    horizon = int(height * 0.62)
    canvas.rect(0, horizon, width, height - horizon, (0.10, 0.10, 0.14), fill=True)
    for i in range(7):
        t = i / 6.0
        x = int((0.12 + t * 0.76) * width)
        h = int((0.10 + 0.18 * (1.0 - abs(0.5 - t) * 2.0)) * height)
        canvas.rect(x, horizon - h, max(4, width // 28), h, (0.22 + 0.06 * t, 0.38 + 0.10 * t, 0.62 + 0.10 * t), fill=True)
    sun_r = max(8, min(width, height) // 10)
    canvas.circle(int(width * 0.80), int(height * 0.24), sun_r, (0.96, 0.84, 0.42), fill=True)
    canvas.circle(int(width * 0.80), int(height * 0.24), sun_r + 4, (0.96, 0.84, 0.42), fill=False)
    canvas.line(width * 0.10, height * 0.78, width * 0.90, height * 0.78, (0.90, 0.92, 0.96), thickness=1)
    canvas.line(width * 0.10, height * 0.84, width * 0.90, height * 0.84, (0.36, 0.40, 0.50), thickness=1)
    canvas.rect(int(width * 0.06), int(height * 0.08), int(width * 0.40), int(height * 0.16), (0.08, 0.10, 0.14), fill=True)
    canvas.rect(int(width * 0.06), int(height * 0.08), int(width * 0.40), int(height * 0.16), (0.52, 0.72, 0.98), fill=False)
    bars = max(4, min(12, len(str(title).split())))
    for i in range(bars):
        canvas.rect(int(width * 0.09), int(height * 0.11) + i * max(3, height // 48), int(width * (0.12 + (0.22 if i == 0 else 0.16 + (i % 3) * 0.05))), max(2, height // 80), (0.84, 0.90, 0.98), fill=True)
    return canvas.rows()
