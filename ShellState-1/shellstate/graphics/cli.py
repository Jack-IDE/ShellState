"""CLI entry points for the ShellState graphics/media subsystem."""
from __future__ import annotations

import argparse
import os
from typing import Optional, Sequence

from .image2d import render_demo_poster
from .io_ppm import load_json, save_json, write_ppm
from .renderer import render_scene
from .samples import sample_assets
from .scene import sample_scene
from .video import decode_codec_to_directory, render_game_clip_to_directory, render_scene_clip_to_directory
from .game import render_world_frame, sample_world


DEFAULT_SELFTEST_OUT3D = 'selftest_preview_3d.ppm'
DEFAULT_SELFTEST_OUT2D = 'selftest_preview_2d.ppm'
DEFAULT_SELFTEST_OUTGAME = 'selftest_preview_game.ppm'


def _default_selftest_output_paths() -> tuple[str, str, str]:
    from shellstate.core.runtime_model import GRAPHICS_EXPORTS_DIR
    outdir = os.path.join(GRAPHICS_EXPORTS_DIR, 'selftest')
    os.makedirs(outdir, exist_ok=True)
    return (
        os.path.join(outdir, DEFAULT_SELFTEST_OUT3D),
        os.path.join(outdir, DEFAULT_SELFTEST_OUT2D),
        os.path.join(outdir, DEFAULT_SELFTEST_OUTGAME),
    )

def command_render(args: argparse.Namespace) -> None:
    scene = load_json(args.scene) if args.scene else sample_scene()
    write_ppm(args.out, render_scene(scene, args.width, args.height, spp=args.spp))
    print(f'Wrote 3D still frame: {args.out}')

def command_render_2d(args: argparse.Namespace) -> None:
    write_ppm(args.out, render_demo_poster(args.width, args.height, title=args.title))
    print(f'Wrote 2D sample image: {args.out}')

def command_render_game_frame(args: argparse.Namespace) -> None:
    write_ppm(args.out, render_world_frame(sample_world(), width=args.width, height=args.height))
    print(f'Wrote 2D game snapshot: {args.out}')

def command_export_sample_assets(args: argparse.Namespace) -> None:
    os.makedirs(args.outdir, exist_ok=True)
    assets = sample_assets(frames=args.frames, fps=args.fps, segment_frames=args.segment_frames, threshold=args.threshold)
    save_json(os.path.join(args.outdir, 'sample_scene.json'), assets['scene'])
    save_json(os.path.join(args.outdir, 'sample_clip.json'), assets['clip'])
    save_json(os.path.join(args.outdir, 'sample_codec.json'), assets['codec'])
    print(f'Exported sample assets to {args.outdir}')

def command_scene_clip(args: argparse.Namespace) -> None:
    result = render_scene_clip_to_directory(args.outdir, frames=args.frames, fps=args.fps, width=args.width, height=args.height, spp=args.spp)
    print(f"Wrote {result['frames']} 3D frames to {args.outdir}")

def command_game_clip(args: argparse.Namespace) -> None:
    result = render_game_clip_to_directory(args.outdir, frames=args.frames, fps=args.fps, width=args.width, height=args.height)
    print(f"Wrote {result['frames']} game frames to {args.outdir}")

def command_decode_render(args: argparse.Namespace) -> None:
    result = decode_codec_to_directory(args.codec, args.outdir, width=args.width, height=args.height, spp=args.spp)
    print(f"Decoded and rendered {result['frames']} frames to {args.outdir}")

def command_selftest(args: argparse.Namespace) -> None:
    from .codec import ParametricFieldCodec
    from .scene import build_sample_clip, flatten_numeric_paths
    default_out3d, default_out2d, default_outgame = _default_selftest_output_paths()
    if args.out3d == DEFAULT_SELFTEST_OUT3D:
        args.out3d = default_out3d
    if args.out2d == DEFAULT_SELFTEST_OUT2D:
        args.out2d = default_out2d
    if args.outgame == DEFAULT_SELFTEST_OUTGAME:
        args.outgame = default_outgame
    codec = ParametricFieldCodec(fps=12, segment_frames=6, threshold=0.02)
    clip = build_sample_clip(10, 12)
    enc = codec.encode(clip)
    dec = codec.decode(enc)
    max_err = 0.0
    for scene_a, scene_b in zip(clip, dec):
        fa = flatten_numeric_paths(scene_a)
        fb = flatten_numeric_paths(scene_b)
        for key in fa:
            max_err = max(max_err, abs(fa[key] - fb[key]))
    write_ppm(args.out3d, render_scene(sample_scene(), 16, 9, spp=max(1, args.spp)))
    write_ppm(args.out2d, render_demo_poster(64, 36))
    write_ppm(args.outgame, render_world_frame(sample_world(), width=64, height=36))
    print('Self-test passed')
    print(f'Max decode scalar error: {max_err:.6f}')
    print(f'3D preview frame: {args.out3d}')
    print(f'2D preview frame: {args.out2d}')
    print(f'Game preview frame: {args.outgame}')

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='ShellState graphics/media subsystem')
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('render', help='Render a 3D still scene to PPM')
    s.add_argument('--scene', default='')
    s.add_argument('--width', type=int, default=64)
    s.add_argument('--height', type=int, default=36)
    s.add_argument('--spp', type=int, default=1)
    s.add_argument('--out', default='still.ppm')
    s.set_defaults(func=command_render)
    s = sub.add_parser('render-2d', help='Render a built-in 2D sample image to PPM')
    s.add_argument('--width', type=int, default=256)
    s.add_argument('--height', type=int, default=144)
    s.add_argument('--title', default='ShellState Graphics')
    s.add_argument('--out', default='image2d.ppm')
    s.set_defaults(func=command_render_2d)
    s = sub.add_parser('render-game-frame', help='Render a 2D game snapshot to PPM')
    s.add_argument('--width', type=int, default=256)
    s.add_argument('--height', type=int, default=144)
    s.add_argument('--out', default='game2d.ppm')
    s.set_defaults(func=command_render_game_frame)
    s = sub.add_parser('scene-clip', help='Render a built-in 3D animated sample clip')
    s.add_argument('--frames', type=int, default=6)
    s.add_argument('--fps', type=int, default=6)
    s.add_argument('--width', type=int, default=48)
    s.add_argument('--height', type=int, default=27)
    s.add_argument('--spp', type=int, default=1)
    s.add_argument('--outdir', default='scene_clip_frames')
    s.set_defaults(func=command_scene_clip)
    s = sub.add_parser('game-clip', help='Render a built-in 2D game clip')
    s.add_argument('--frames', type=int, default=24)
    s.add_argument('--fps', type=int, default=24)
    s.add_argument('--width', type=int, default=256)
    s.add_argument('--height', type=int, default=144)
    s.add_argument('--outdir', default='game_clip_frames')
    s.set_defaults(func=command_game_clip)
    s = sub.add_parser('decode-render', help='Decode a codec JSON and render its 3D frames')
    s.add_argument('--codec', required=True)
    s.add_argument('--width', type=int, default=48)
    s.add_argument('--height', type=int, default=27)
    s.add_argument('--spp', type=int, default=1)
    s.add_argument('--outdir', default='decoded_frames')
    s.set_defaults(func=command_decode_render)
    s = sub.add_parser('export-sample-assets', help='Write sample scene, clip, and codec JSON files')
    s.add_argument('--frames', type=int, default=24)
    s.add_argument('--fps', type=int, default=24)
    s.add_argument('--segment-frames', type=int, default=24)
    s.add_argument('--threshold', type=float, default=0.01)
    s.add_argument('--outdir', default='sample_assets')
    s.set_defaults(func=command_export_sample_assets)
    s = sub.add_parser('selftest', help='Run subsystem sanity tests and write preview renders')
    s.add_argument('--spp', type=int, default=1)
    s.add_argument('--out3d', default=DEFAULT_SELFTEST_OUT3D)
    s.add_argument('--out2d', default=DEFAULT_SELFTEST_OUT2D)
    s.add_argument('--outgame', default=DEFAULT_SELFTEST_OUTGAME)
    s.set_defaults(func=command_selftest)
    return p

def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)

if __name__ == '__main__':
    main()
