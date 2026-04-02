"""Simple file IO helpers for graphics assets."""
from __future__ import annotations

import json
from typing import Any, Sequence, Tuple

def write_ppm(path: str, framebuffer: Sequence[Sequence[Tuple[int, int, int]]]) -> None:
    height = len(framebuffer)
    width = len(framebuffer[0]) if height else 0
    with open(path, "wb") as f:
        f.write(f"P6\n{width} {height}\n255\n".encode("ascii"))
        for row in framebuffer:
            for r, g, b in row:
                f.write(bytes((r, g, b)))

def save_json(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")

def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
