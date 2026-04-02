"""Stable ShellState-facing API for dedicated graphics and media operations."""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List

from .game import render_world_frame, sample_world, world_snapshot
from .image2d import render_demo_poster
from .io_ppm import save_json, write_ppm
from .renderer import render_scene, render_scene_progressive_with_overrides, render_scene_with_overrides
from .samples import sample_assets
from .scene import home_scene_by_name, home_scene_choices, sample_scene
from .video import render_game_clip_to_directory, render_scene_clip_to_directory

def _timestamp_slug() -> str:
    return datetime.now().strftime('%Y%m%d_%H%M%S_%f')


def _scale_framebuffer_nearest(framebuffer, out_w: int, out_h: int):
    src_h = len(framebuffer)
    src_w = len(framebuffer[0]) if src_h else 0
    out_w = max(1, int(out_w))
    out_h = max(1, int(out_h))
    if src_w <= 0 or src_h <= 0:
        return [[(0, 0, 0) for _ in range(out_w)] for _ in range(out_h)]
    if src_w == out_w and src_h == out_h:
        return framebuffer
    scaled = []
    for y in range(out_h):
        sy = min(src_h - 1, (y * src_h) // out_h)
        src_row = framebuffer[sy]
        row = []
        for x in range(out_w):
            sx = min(src_w - 1, (x * src_w) // out_w)
            row.append(src_row[sx])
        scaled.append(row)
    return scaled


def _lerp_u8(a: int, b: int, t: float) -> int:
    return max(0, min(255, int(a + (b - a) * t + 0.5)))


def _scale_framebuffer_bilinear(framebuffer, out_w: int, out_h: int):
    src_h = len(framebuffer)
    src_w = len(framebuffer[0]) if src_h else 0
    out_w = max(1, int(out_w))
    out_h = max(1, int(out_h))
    if src_w <= 0 or src_h <= 0:
        return [[(0, 0, 0) for _ in range(out_w)] for _ in range(out_h)]
    if src_w == out_w and src_h == out_h:
        return framebuffer
    if src_w == 1 or src_h == 1:
        return _scale_framebuffer_nearest(framebuffer, out_w, out_h)
    scaled = []
    for y in range(out_h):
        src_y = 0.0 if out_h <= 1 else (y * (src_h - 1)) / float(out_h - 1)
        y0 = int(src_y)
        y1 = min(src_h - 1, y0 + 1)
        ty = src_y - y0
        row = []
        for x in range(out_w):
            src_x = 0.0 if out_w <= 1 else (x * (src_w - 1)) / float(out_w - 1)
            x0 = int(src_x)
            x1 = min(src_w - 1, x0 + 1)
            tx = src_x - x0
            c00 = framebuffer[y0][x0]
            c10 = framebuffer[y0][x1]
            c01 = framebuffer[y1][x0]
            c11 = framebuffer[y1][x1]
            top = tuple(_lerp_u8(c00[i], c10[i], tx) for i in range(3))
            bottom = tuple(_lerp_u8(c01[i], c11[i], tx) for i in range(3))
            row.append(tuple(_lerp_u8(top[i], bottom[i], ty) for i in range(3)))
        scaled.append(row)
    return scaled


class GraphicsService:
    def __init__(self, runtime_dir: str, exports_dir: str):
        self.runtime_dir = runtime_dir
        self.exports_dir = exports_dir
        self.project_root = os.path.dirname(runtime_dir)
        self.graphics_dir = os.path.join(exports_dir, 'graphics')
        self.images2d_dir = os.path.join(self.graphics_dir, 'images2d')
        self.scenes3d_dir = os.path.join(self.graphics_dir, 'scenes3d')
        self.clips_dir = os.path.join(self.graphics_dir, 'clips')
        self.games_dir = os.path.join(self.graphics_dir, 'games')
        self.assets_dir = os.path.join(self.graphics_dir, 'assets')
        self.meta_dir = os.path.join(self.graphics_dir, 'meta')
        self.home_dir = os.path.join(self.graphics_dir, 'home')
        self.lab_dir = os.path.join(self.graphics_dir, 'lab')

    def ensure_dirs(self) -> None:
        for path in (self.graphics_dir, self.images2d_dir, self.scenes3d_dir, self.clips_dir, self.games_dir, self.assets_dir, self.meta_dir, self.home_dir, self.lab_dir):
            os.makedirs(path, exist_ok=True)

    def _graphics_store(self, app) -> Dict[str, Any]:
        system = app.app_data.setdefault('system', {})
        graphics = system.setdefault('graphics', {})
        if not isinstance(graphics, dict):
            graphics = {}
            system['graphics'] = graphics
        graphics.setdefault('exports', [])
        return graphics

    def _display_relpath(self, path: str) -> str:
        if path.startswith(self.project_root):
            return os.path.relpath(path, self.project_root)
        return path

    def _record_export(self, app, kind: str, path: str, detail: str = '') -> str:
        rel = self._display_relpath(path)
        store = self._graphics_store(app)
        item = {'kind': kind, 'path': rel, 'detail': detail, 'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        exports = [x for x in store.get('exports', []) if x.get('path') != rel]
        exports.insert(0, item)
        store['exports'] = exports[:24]
        store['latest_kind'] = kind
        store['latest_path'] = rel
        return rel

    def latest_exports(self, app, limit: int = 5) -> List[Dict[str, Any]]:
        return list(self._graphics_store(app).get('exports', []))[:max(1, int(limit))]


    def scene_preset_options(self) -> List[tuple[str, str]]:
        return [(label, key) for label, key in self.home_scene_options() if key != "off"]

    def scene_json_for_preset(self, preset: str = "demo") -> str:
        key = str(preset or "demo").strip().lower()
        if key in {"", "off"}:
            key = "demo"
        scene = home_scene_by_name(key)
        return json.dumps(scene, indent=2, ensure_ascii=False) + "\n"

    def render_lab_scene_text(self, app, scene_text: str, *, width: int = 48, height: int = 27, spp: int = 1) -> Dict[str, Any]:
        self.ensure_dirs()
        payload = json.loads(str(scene_text or "{}"))
        if not isinstance(payload, dict):
            raise ValueError("Scene JSON must decode to an object.")
        stamp = _timestamp_slug()
        archive_ppm = os.path.join(self.lab_dir, f"lab_scene_{stamp}.ppm")
        archive_json = os.path.join(self.lab_dir, f"lab_scene_{stamp}.json")
        current_ppm = os.path.join(self.lab_dir, "current_lab.ppm")
        current_json = os.path.join(self.lab_dir, "current_lab.json")
        framebuffer = render_scene(payload, int(width), int(height), spp=max(1, int(spp)))
        write_ppm(archive_ppm, framebuffer)
        write_ppm(current_ppm, framebuffer)
        save_json(archive_json, payload)
        save_json(current_json, payload)
        self._record_export(app, 'lab_scene', archive_ppm, detail=f"{int(width)}x{int(height)}")
        return {
            'archive_path': self._display_relpath(archive_ppm),
            'current_path': self._display_relpath(current_ppm),
            'scene_json_path': self._display_relpath(current_json),
            'width': int(width),
            'height': int(height),
            'spp': int(spp),
        }


    def home_scene_options(self) -> List[tuple[str, str]]:
        return list(home_scene_choices())

    def _home_store(self, app) -> Dict[str, Any]:
        store = self._graphics_store(app)
        home = store.setdefault('home_image', {})
        if not isinstance(home, dict):
            home = {}
            store['home_image'] = home
        return home

    def home_scene_state(self, app) -> Dict[str, Any]:
        home = self._home_store(app)
        preset = str(home.get('preset') or 'off')
        rel = str(home.get('path') or '')
        label = preset.title() or 'Off'
        for option_label, option_key in self.home_scene_options():
            if option_key == preset:
                label = option_label
                break
        return {
            'preset': preset,
            'label': label,
            'path': rel,
            'rendered_at': str(home.get('rendered_at') or ''),
            'width': int(home.get('width') or 0),
            'height': int(home.get('height') or 0),
        }

    def render_home_scene(self, app, preset: str, *, width: int = 48, height: int = 27, spp: int = 1) -> str:
        self.ensure_dirs()
        home = self._home_store(app)
        preset = str(preset or 'off').strip().lower()
        if preset == 'off':
            home.clear()
            home.update({'preset': 'off', 'path': '', 'rendered_at': '', 'width': 0, 'height': 0})
            return ''
        scene = home_scene_by_name(preset)
        path = os.path.join(self.home_dir, 'current_home.ppm')
        output_w = max(1, int(width))
        output_h = max(1, int(height))
        render_w = output_w
        render_h = output_h

        def _progress(index: int, total: int, pass_w: int, pass_h: int, framebuffer):
            preview = framebuffer
            if pass_w != output_w or pass_h != output_h:
                preview = _scale_framebuffer_bilinear(framebuffer, output_w, output_h)
            write_ppm(path, preview)
            if app is not None and hasattr(app, 'set_status'):
                app.set_status(f'Home image render {index}/{total}: {pass_w}x{pass_h}')
                can_repaint = bool(
                    hasattr(app, 'render')
                    and hasattr(app, 'screens')
                    and getattr(app, 'current_screen', None) in getattr(app, 'screens', {})
                )
                if can_repaint:
                    try:
                        app.render()
                    except Exception:
                        pass

        framebuffer = render_scene_progressive_with_overrides(
            scene,
            render_w,
            render_h,
            spp=max(1, int(spp)),
            max_steps=72,
            shadow_steps=0,
            ao_steps=1,
            reflection_bounces=0,
            progress_callback=_progress,
        )
        if render_w != output_w or render_h != output_h:
            framebuffer = _scale_framebuffer_bilinear(framebuffer, output_w, output_h)
            write_ppm(path, framebuffer)
        meta_path = os.path.join(self.home_dir, 'current_home.json')
        payload = {
            'kind': 'home_scene',
            'preset': preset,
            'width': int(width),
            'height': int(height),
            'spp': int(spp),
            'path': self._display_relpath(path),
            'progressive': True,
        }
        save_json(meta_path, payload)
        home.clear()
        home.update({
            'preset': preset,
            'path': self._display_relpath(path),
            'rendered_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'width': int(width),
            'height': int(height),
        })
        self._record_export(app, 'home_scene', path, detail=preset)
        return home['path']

    def render_image2d_sample(self, app, *, width: int = 256, height: int = 144) -> str:
        self.ensure_dirs()
        filename = f'image2d_{_timestamp_slug()}.ppm'
        path = os.path.join(self.images2d_dir, filename)
        write_ppm(path, render_demo_poster(width=width, height=height))
        meta_path = os.path.join(self.meta_dir, filename.replace('.ppm', '.json'))
        save_json(meta_path, {'kind': 'image2d', 'width': int(width), 'height': int(height), 'path': self._display_relpath(path)})
        return self._record_export(app, 'image2d', path, detail='2D poster sample')

    def render_scene3d_sample(self, app, *, width: int = 48, height: int = 27, spp: int = 1) -> str:
        self.ensure_dirs()
        filename = f'scene3d_{_timestamp_slug()}.ppm'
        path = os.path.join(self.scenes3d_dir, filename)
        write_ppm(path, render_scene(sample_scene(), width, height, spp=max(1, int(spp))))
        meta_path = os.path.join(self.meta_dir, filename.replace('.ppm', '.json'))
        save_json(meta_path, {'kind': 'scene3d', 'width': int(width), 'height': int(height), 'spp': int(spp), 'path': self._display_relpath(path)})
        return self._record_export(app, 'scene3d', path, detail='3D still sample')

    def export_scene3d_clip(self, app, *, frames: int = 4, fps: int = 4, width: int = 48, height: int = 27, spp: int = 1) -> str:
        self.ensure_dirs()
        stamp = _timestamp_slug()
        outdir = os.path.join(self.clips_dir, f'scene3d_clip_{stamp}')
        result = render_scene_clip_to_directory(outdir, frames=frames, fps=fps, width=width, height=height, spp=spp)
        save_json(os.path.join(outdir, 'meta.json'), result)
        return self._record_export(app, 'scene3d_clip', outdir, detail=f"{result['frames']} frames @ {result['fps']}fps")

    def render_game2d_snapshot(self, app, *, width: int = 256, height: int = 144) -> str:
        self.ensure_dirs()
        filename = f'game2d_snapshot_{_timestamp_slug()}.ppm'
        path = os.path.join(self.games_dir, filename)
        world = sample_world()
        write_ppm(path, render_world_frame(world, width=width, height=height))
        meta_path = os.path.join(self.meta_dir, filename.replace('.ppm', '.json'))
        save_json(meta_path, {'kind': 'game2d_snapshot', 'state': world_snapshot(world), 'path': self._display_relpath(path)})
        return self._record_export(app, 'game2d_snapshot', path, detail='2D game runtime snapshot')

    def export_game2d_clip(self, app, *, frames: int = 24, fps: int = 12, width: int = 160, height: int = 90) -> str:
        self.ensure_dirs()
        stamp = _timestamp_slug()
        outdir = os.path.join(self.games_dir, f'game2d_clip_{stamp}')
        result = render_game_clip_to_directory(outdir, frames=frames, fps=fps, width=width, height=height)
        save_json(os.path.join(outdir, 'meta.json'), result)
        return self._record_export(app, 'game2d_clip', outdir, detail=f"{result['frames']} frames @ {result['fps']}fps")

    def export_sample_assets(self, app, *, frames: int = 24, fps: int = 24, segment_frames: int = 24, threshold: float = 0.01) -> str:
        self.ensure_dirs()
        stamp = _timestamp_slug()
        outdir = os.path.join(self.assets_dir, f'graphics_assets_{stamp}')
        os.makedirs(outdir, exist_ok=True)
        assets = sample_assets(frames=frames, fps=fps, segment_frames=segment_frames, threshold=threshold)
        save_json(os.path.join(outdir, 'sample_scene.json'), assets['scene'])
        save_json(os.path.join(outdir, 'sample_clip.json'), assets['clip'])
        save_json(os.path.join(outdir, 'sample_codec.json'), assets['codec'])
        return self._record_export(app, 'graphics_assets', outdir, detail='sample scene/clip/codec assets')
