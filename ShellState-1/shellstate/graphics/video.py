"""Video/clip helpers for the ShellState graphics subsystem."""
from __future__ import annotations

import os
from typing import Dict, List

from .codec import ParametricFieldCodec
from .game import simulate_world_frames
from .io_ppm import save_json, write_ppm
from .renderer import render_scene
from .scene import build_sample_clip

def render_scene_clip_to_directory(outdir: str, *, frames: int = 24, fps: int = 24, width: int = 320, height: int = 180, spp: int = 1) -> Dict[str, object]:
    os.makedirs(outdir, exist_ok=True)
    clip = build_sample_clip(max(1, int(frames)), max(1, int(fps)))
    for i, scene in enumerate(clip):
        write_ppm(os.path.join(outdir, f'frame_{i:04d}.ppm'), render_scene(scene, width, height, spp=max(1, int(spp))))
    codec = ParametricFieldCodec(fps=max(1, int(fps)), segment_frames=max(1, int(frames)), threshold=0.02)
    save_json(os.path.join(outdir, 'scene_clip.json'), clip)
    save_json(os.path.join(outdir, 'codec.json'), codec.encode(clip))
    return {'kind': 'scene3d_clip', 'frames': len(clip), 'fps': int(fps), 'outdir': outdir}

def decode_codec_to_directory(codec_path: str, outdir: str, *, width: int = 320, height: int = 180, spp: int = 1) -> Dict[str, object]:
    from .io_ppm import load_json
    codec = ParametricFieldCodec()
    encoded = load_json(codec_path)
    scenes = codec.decode(encoded)
    os.makedirs(outdir, exist_ok=True)
    for i, scene in enumerate(scenes):
        write_ppm(os.path.join(outdir, f'decoded_{i:04d}.ppm'), render_scene(scene, width, height, spp=max(1, int(spp))))
    return {'kind': 'decoded_clip', 'frames': len(scenes), 'outdir': outdir}

def render_game_clip_to_directory(outdir: str, *, frames: int = 24, fps: int = 24, width: int = 256, height: int = 144) -> Dict[str, object]:
    os.makedirs(outdir, exist_ok=True)
    frame_rows, states = simulate_world_frames(max(1, int(frames)), width=width, height=height, dt=1.0 / max(1, int(fps)))
    for i, frame in enumerate(frame_rows):
        write_ppm(os.path.join(outdir, f'frame_{i:04d}.ppm'), frame)
    save_json(os.path.join(outdir, 'game_states.json'), states)
    return {'kind': 'game2d_clip', 'frames': len(frame_rows), 'fps': int(fps), 'outdir': outdir}
