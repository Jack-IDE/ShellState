"""Parameter-track scene codec for the graphics subsystem."""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

from .math3d import solve_linear_system
from .scene import clone_scene, flatten_numeric_paths, replace_numeric_with_zero, set_by_path

def polyfit_track(values: Sequence[float], degree: int, dt: float) -> List[float]:
    xs = [i * dt for i in range(len(values))]
    order = degree + 1
    mat = [[0.0 for _ in range(order)] for _ in range(order)]
    rhs = [0.0 for _ in range(order)]
    for r in range(order):
        for c in range(order):
            mat[r][c] = sum((x ** (r + c)) for x in xs)
        rhs[r] = sum((x ** r) * y for x, y in zip(xs, values))
    return solve_linear_system(mat, rhs)

def eval_poly(coeffs: Sequence[float], t: float) -> float:
    total = 0.0
    power = 1.0
    for c in coeffs:
        total += c * power
        power *= t
    return total

def rms_error(values: Sequence[float], predicted: Sequence[float]) -> float:
    if not values:
        return 0.0
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(values, predicted)) / len(values))

class ParametricFieldCodec:
    def __init__(self, fps: int = 24, segment_frames: Optional[int] = None, threshold: float = 0.01):
        self.fps = fps
        self.dt = 1.0 / fps
        self.segment_frames = segment_frames or fps
        self.threshold = threshold

    def encode(self, scenes: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        if not scenes:
            raise ValueError("encode() requires at least one scene")
        template = replace_numeric_with_zero(clone_scene(scenes[0]))
        numeric_keys = sorted(flatten_numeric_paths(scenes[0]).keys())
        flattened = [flatten_numeric_paths(scene) for scene in scenes]
        tracks = {k: [frame[k] for frame in flattened] for k in numeric_keys}
        segments = []
        frame_count = len(scenes)
        start = 0
        while start < frame_count:
            seg_len = min(self.segment_frames, frame_count - start)
            segment = {"start_frame": start, "num_frames": seg_len, "tracks": {}}
            for key in numeric_keys:
                vals = tracks[key][start:start + seg_len]
                c1 = polyfit_track(vals, 1, self.dt) if len(vals) >= 2 else [vals[0], 0.0]
                p1 = [eval_poly(c1, i * self.dt) for i in range(seg_len)]
                e1 = rms_error(vals, p1)
                if len(vals) >= 3:
                    c2 = polyfit_track(vals, 2, self.dt)
                    p2 = [eval_poly(c2, i * self.dt) for i in range(seg_len)]
                    e2 = rms_error(vals, p2)
                else:
                    c2 = [vals[0], 0.0, 0.0]
                    p2 = [vals[0] for _ in range(seg_len)]
                    e2 = float("inf")
                if e1 <= self.threshold or e1 <= e2 * 1.25:
                    residuals = [vals[i] - p1[i] for i in range(seg_len)]
                    track_desc = {"model": "linear", "p0": c1[0], "v": c1[1]}
                    if max((abs(r) for r in residuals), default=0.0) > self.threshold * 0.5:
                        track_desc["residuals"] = residuals
                else:
                    residuals = [vals[i] - p2[i] for i in range(seg_len)]
                    track_desc = {"model": "quadratic", "p0": c2[0], "v": c2[1], "a": 2.0 * c2[2]}
                    if max((abs(r) for r in residuals), default=0.0) > self.threshold * 0.25:
                        track_desc["residuals"] = residuals
                segment["tracks"][key] = track_desc
            segments.append(segment)
            start += seg_len
        return {"format": "ParametricFieldStream/0.2", "fps": self.fps, "frame_count": frame_count, "template": template, "segments": segments}

    def decode(self, codec: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for segment in codec["segments"]:
            for frame_index in range(segment["num_frames"]):
                scene = clone_scene(codec["template"])
                t = frame_index * (1.0 / codec["fps"])
                for key, track in segment["tracks"].items():
                    if track["model"] == "linear":
                        value = track["p0"] + track["v"] * t
                    else:
                        value = track["p0"] + track["v"] * t + 0.5 * track["a"] * t * t
                    residuals = track.get("residuals")
                    if residuals is not None:
                        value += residuals[frame_index]
                    set_by_path(scene, key, value)
                out.append(scene)
        return out[: codec["frame_count"]]
