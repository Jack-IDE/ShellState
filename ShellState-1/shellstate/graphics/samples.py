"""Sample asset helpers exposed by the graphics subsystem."""
from __future__ import annotations

from .codec import ParametricFieldCodec
from .scene import build_sample_clip, sample_scene

def sample_assets(frames: int = 12, fps: int = 12, segment_frames: int = 12, threshold: float = 0.01):
    clip = build_sample_clip(frames, fps)
    codec = ParametricFieldCodec(fps=fps, segment_frames=segment_frames, threshold=threshold)
    return {"scene": sample_scene(), "clip": clip, "codec": codec.encode(clip)}
