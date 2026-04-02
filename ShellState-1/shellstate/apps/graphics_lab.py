"""Dedicated shell launch surface for graphics image creation/import/rendering."""

from __future__ import annotations

import json
import os
from typing import List, Tuple

from shellstate.apps.notes import _fullscreen_editor_size, _notes_render_canvas_row
from shellstate.core.runtime_model import PROJECT_ROOT, _record_activity, _system_store, graphics
from shellstate.graphics.display import launch_image_surface

GRAPHICS_PREVIEW_WIDTH = 48
GRAPHICS_PREVIEW_HEIGHT = 27
GRAPHICS_PREVIEW_SPP = 1
GRAPHICS_EDITOR_WIDTH = 60
GRAPHICS_EDITOR_HEIGHT = 12
GRAPHICS_IMPORT_WIDTH = 60
GRAPHICS_IMPORT_HEIGHT = 4
GRAPHICS_SCENE_PRESETS = graphics.scene_preset_options()
THUMBNAIL_WIDTH = 32
THUMBNAIL_HEIGHT = 12
ASCII_RAMP = " .,:;irsXA253hMHGS#9B&@"


SEXTANT_CHARS = {
    0: ' ',
    1: '🬀', 2: '🬁', 3: '🬂', 4: '🬃',
    5: '🬄', 6: '🬅', 7: '🬆', 8: '🬇',
    9: '🬈', 10: '🬉', 11: '🬊', 12: '🬋',
    13: '🬌', 14: '🬍', 15: '🬎', 16: '🬏',
    17: '🬐', 18: '🬑', 19: '🬒', 20: '🬓',
    21: '▌', 22: '🬔', 23: '🬕', 24: '🬖',
    25: '🬗', 26: '🬘', 27: '🬙', 28: '🬚',
    29: '🬛', 30: '🬜', 31: '🬝', 32: '🬞',
    33: '🬟', 34: '🬠', 35: '🬡', 36: '🬢',
    37: '🬣', 38: '🬤', 39: '🬥', 40: '🬦',
    41: '🬧', 42: '▐', 43: '🬨', 44: '🬩',
    45: '🬪', 46: '🬫', 47: '🬬', 48: '🬭',
    49: '🬮', 50: '🬯', 51: '🬰', 52: '🬱',
    53: '🬲', 54: '🬳', 55: '🬴', 56: '🬵',
    57: '🬶', 58: '🬷', 59: '🬸', 60: '🬹',
    61: '🬺', 62: '🬻', 63: '█',
}


def _avg_rgb(cells):
    if not cells:
        return (0, 0, 0)
    r = sum(c[0] for c in cells) // len(cells)
    g = sum(c[1] for c in cells) // len(cells)
    b = sum(c[2] for c in cells) // len(cells)
    return (r, g, b)


def _color_distance_sq(a, b):
    dr = a[0] - b[0]
    dg = a[1] - b[1]
    db = a[2] - b[2]
    return (dr * dr) + (dg * dg) + (db * db)


def _ansi_dense_sextant_thumbnail_lines(
    path: str,
    thumb_w: int = THUMBNAIL_WIDTH,
    thumb_h: int = THUMBNAIL_HEIGHT,
    supersample: int = 2,
) -> List[str]:
    lines: List[str] = []
    thumb_w = max(1, int(thumb_w))
    thumb_h = max(1, int(thumb_h))
    supersample = max(1, int(supersample))
    cells = _thumbnail_cells(path, thumb_w * 2 * supersample, thumb_h * 3 * supersample)
    if not cells:
        return lines
    total_rows = len(cells)
    total_cols = len(cells[0]) if total_rows else 0

    def _cell_avg(row_start: int, col_start: int):
        group = []
        for sy in range(supersample):
            src_y = min(total_rows - 1, row_start + sy)
            row = cells[src_y]
            for sx in range(supersample):
                src_x = min(total_cols - 1, col_start + sx)
                group.append(row[src_x])
        return _avg_rgb(group)

    for out_row in range(thumb_h):
        row_index = out_row * 3 * supersample
        chars: List[str] = []
        for out_col in range(thumb_w):
            col_index = out_col * 2 * supersample
            block = [
                _cell_avg(row_index + (0 * supersample), col_index + (0 * supersample)),
                _cell_avg(row_index + (0 * supersample), col_index + (1 * supersample)),
                _cell_avg(row_index + (1 * supersample), col_index + (0 * supersample)),
                _cell_avg(row_index + (1 * supersample), col_index + (1 * supersample)),
                _cell_avg(row_index + (2 * supersample), col_index + (0 * supersample)),
                _cell_avg(row_index + (2 * supersample), col_index + (1 * supersample)),
            ]
            seed_a = 0
            seed_b = 0
            best_dist = -1
            for i in range(6):
                for j in range(i + 1, 6):
                    dist = _color_distance_sq(block[i], block[j])
                    if dist > best_dist:
                        best_dist = dist
                        seed_a = i
                        seed_b = j
            fg_group = []
            bg_group = []
            mask = 0
            color_a = block[seed_a]
            color_b = block[seed_b]
            for idx, color in enumerate(block):
                if _color_distance_sq(color, color_a) <= _color_distance_sq(color, color_b):
                    fg_group.append(color)
                    mask |= (1 << idx)
                else:
                    bg_group.append(color)
            if not fg_group:
                chars.append(' ')
                continue
            if not bg_group:
                fg = _avg_rgb(fg_group)
                chars.append(f"[38;2;{fg[0]};{fg[1]};{fg[2]}m█[0m")
                continue
            fg = _avg_rgb(fg_group)
            bg = _avg_rgb(bg_group)
            glyph = SEXTANT_CHARS.get(mask, '█' if len(fg_group) >= len(bg_group) else ' ')
            chars.append(f"[38;2;{fg[0]};{fg[1]};{fg[2]}m[48;2;{bg[0]};{bg[1]};{bg[2]}m{glyph}[0m")
        lines.append(''.join(chars))
    return lines


def _ppm_tokens(handle):
    while True:
        ch = handle.read(1)
        if not ch:
            return
        if ch.isspace():
            continue
        if ch == b'#':
            handle.readline()
            continue
        token = bytearray()
        while ch and not ch.isspace():
            token.extend(ch)
            ch = handle.read(1)
        yield bytes(token)


def _load_ppm_rgb(path: str) -> Tuple[int, int, bytes]:
    with open(path, 'rb') as handle:
        tokens = _ppm_tokens(handle)
        magic = next(tokens).decode('ascii')
        if magic != 'P6':
            raise ValueError('Preview thumbnail expects binary P6 PPM data.')
        width = int(next(tokens).decode('ascii'))
        height = int(next(tokens).decode('ascii'))
        max_value = int(next(tokens).decode('ascii'))
        if max_value != 255:
            raise ValueError('Preview thumbnail expects 8-bit PPM data.')
        data = handle.read(width * height * 3)
    expected = width * height * 3
    if len(data) != expected:
        raise ValueError('Preview thumbnail PPM data is truncated.')
    return width, height, data


def _thumbnail_cells(path: str, thumb_w: int, thumb_h: int) -> List[List[Tuple[int, int, int]]]:
    width, height, data = _load_ppm_rgb(path)
    thumb_w = max(1, int(thumb_w))
    thumb_h = max(1, int(thumb_h))
    cells: List[List[Tuple[int, int, int]]] = []
    for ty in range(thumb_h):
        row: List[Tuple[int, int, int]] = []
        y0 = (ty * height) // thumb_h
        y1 = max(y0 + 1, ((ty + 1) * height) // thumb_h)
        for tx in range(thumb_w):
            x0 = (tx * width) // thumb_w
            x1 = max(x0 + 1, ((tx + 1) * width) // thumb_w)
            r_sum = g_sum = b_sum = count = 0
            for y in range(y0, y1):
                base = (y * width) * 3
                for x in range(x0, x1):
                    idx = base + (x * 3)
                    r_sum += data[idx]
                    g_sum += data[idx + 1]
                    b_sum += data[idx + 2]
                    count += 1
            if count <= 0:
                row.append((0, 0, 0))
            else:
                row.append((r_sum // count, g_sum // count, b_sum // count))
        cells.append(row)
    return cells


def _ascii_thumbnail_lines(path: str, thumb_w: int = THUMBNAIL_WIDTH, thumb_h: int = THUMBNAIL_HEIGHT) -> List[str]:
    lines: List[str] = []
    for row in _thumbnail_cells(path, thumb_w, thumb_h):
        chars = []
        for r, g, b in row:
            lum = (54 * r + 183 * g + 19 * b) // 256
            index = min(len(ASCII_RAMP) - 1, max(0, int((lum / 255.0) * (len(ASCII_RAMP) - 1))))
            chars.append(ASCII_RAMP[index])
        lines.append(''.join(chars).rstrip() or ' ')
    return lines


def _ansi_thumbnail_lines(path: str, thumb_w: int = THUMBNAIL_WIDTH, thumb_h: int = THUMBNAIL_HEIGHT) -> List[str]:
    lines: List[str] = []
    for row in _thumbnail_cells(path, thumb_w, thumb_h):
        chars = []
        for r, g, b in row:
            chars.append(f"\x1b[38;2;{r};{g};{b}m█\x1b[0m")
        lines.append(''.join(chars))
    return lines


def _ansi_halfblock_thumbnail_lines(path: str, thumb_w: int = THUMBNAIL_WIDTH, thumb_h: int = THUMBNAIL_HEIGHT) -> List[str]:
    lines: List[str] = []
    cells = _thumbnail_cells(path, thumb_w, max(1, int(thumb_h)) * 2)
    for row_index in range(0, len(cells), 2):
        top = cells[row_index]
        bottom = cells[row_index + 1] if row_index + 1 < len(cells) else top
        chars = []
        for tx in range(min(len(top), len(bottom))):
            tr, tg, tb = top[tx]
            br, bg, bb = bottom[tx]
            chars.append(
                f"\x1b[38;2;{tr};{tg};{tb}m\x1b[48;2;{br};{bg};{bb}m▀\x1b[0m"
            )
        lines.append(''.join(chars))
    return lines


def _purge_persistent_graphics_thumbnail_cache(app) -> None:
    try:
        system = app.app_data.get('system', {}) if isinstance(getattr(app, 'app_data', None), dict) else {}
    except Exception:
        return
    if not isinstance(system, dict):
        return
    state = system.get('graphics_lab')
    if not isinstance(state, dict):
        return
    state.pop('thumbnail_cache_path', None)
    state.pop('thumbnail_cache_mtime', None)
    state.pop('thumbnail_cache_mode', None)
    state.pop('thumbnail_lines', None)



def _graphics_thumbnail_cache_store(app) -> dict:
    _purge_persistent_graphics_thumbnail_cache(app)
    state = getattr(app, '_graphics_lab_thumbnail_cache', None)
    if not isinstance(state, dict):
        state = {}
        setattr(app, '_graphics_lab_thumbnail_cache', state)
    state.setdefault('thumbnail_cache_path', '')
    state.setdefault('thumbnail_cache_mtime', 0.0)
    state.setdefault('thumbnail_cache_mode', '')
    state.setdefault('thumbnail_lines', [])
    return state



def _graphics_thumbnail_lines(app, path: str) -> List[str]:
    shown = _display_path(path)
    if not shown:
        return ['No preview yet. Press Render to build current_lab.ppm.']
    abs_path = path
    if not os.path.isabs(abs_path):
        abs_path = os.path.join(PROJECT_ROOT, shown)
    abs_path = os.path.abspath(abs_path)
    if not os.path.isfile(abs_path):
        return [f'Preview file missing: {shown}']
    try:
        mtime = os.path.getmtime(abs_path)
    except OSError:
        return [f'Preview file unreadable: {shown}']
    cache_state = _graphics_thumbnail_cache_store(app)
    cache_path = str(cache_state.get('thumbnail_cache_path') or '')
    cache_mtime = cache_state.get('thumbnail_cache_mtime')
    ansi_enabled = bool(getattr(app, '_ansi_enabled', False))
    cache_mode = f'dense_sextant_x2' if ansi_enabled else 'plain_notice'
    if cache_path == shown and cache_mtime == mtime and cache_state.get('thumbnail_cache_mode') == cache_mode:
        cached = cache_state.get('thumbnail_lines')
        if isinstance(cached, list) and cached:
            return [str(line) for line in cached]
    try:
        if ansi_enabled:
            lines = _ansi_dense_sextant_thumbnail_lines(abs_path, thumb_w=THUMBNAIL_WIDTH, thumb_h=THUMBNAIL_HEIGHT, supersample=2)
        else:
            lines = [
                'ANSI preview is unavailable in this terminal.',
                'Press V to open the real image surface.',
            ]
    except Exception as exc:
        return [f'Thumbnail error: {exc}']
    cache_state['thumbnail_cache_path'] = shown
    cache_state['thumbnail_cache_mtime'] = mtime
    cache_state['thumbnail_cache_mode'] = cache_mode
    cache_state['thumbnail_lines'] = list(lines)
    return lines






def open_graphics_preview_surface(app):
    state = _graphics_lab_store(app)
    shown = _display_path(state.get('last_render_path', ''))
    if not shown:
        app.set_status('No preview image is available yet.')
        return None
    abs_path = shown if os.path.isabs(shown) else os.path.abspath(os.path.join(PROJECT_ROOT, shown))
    if not os.path.isfile(abs_path):
        app.set_status('Preview image file is missing.')
        return None
    ok = launch_image_surface(abs_path, title='ShellState Graphics Preview', follow=True)
    app.set_status('Opened graphics preview window.' if ok else 'Could not open a real image surface.')
    return None


def _goto_screen(app, name: str) -> None:
    setter = getattr(app, 'set_screen', None)
    if callable(setter):
        setter(name)
        return
    goto = getattr(app, 'goto_screen', None)
    if callable(goto):
        goto(name)
        return
    app.set_status(f'Open {name} to continue.')



def _display_path(path: str) -> str:
    value = str(path or '').strip()
    if not value:
        return ''
    if os.path.isabs(value):
        try:
            return os.path.relpath(value, PROJECT_ROOT) if value.startswith(PROJECT_ROOT) else value
        except Exception:
            return value
    return value



def _graphics_lab_store(app) -> dict:
    system = _system_store(app)
    state = system.setdefault('graphics_lab', {})
    if not isinstance(state, dict):
        state = {}
        system['graphics_lab'] = state
    if not state.get('scene_text'):
        state['scene_text'] = graphics.scene_json_for_preset('demo')
        state['scene_label'] = 'Demo Blob'
        state['scene_source'] = 'preset:demo'
    state.setdefault('scene_label', 'Demo Blob')
    state.setdefault('scene_source', 'preset:demo')
    state.setdefault('scene_text', graphics.scene_json_for_preset('demo'))
    state.setdefault('editor_row', 0)
    state.setdefault('editor_col', 0)
    state.setdefault('last_render_kind', '')
    state.setdefault('last_render_path', '')
    state.setdefault('last_scene_json_path', '')
    state.setdefault('last_render_at', '')
    state.setdefault('last_width', 0)
    state.setdefault('last_height', 0)
    state.setdefault('last_error', '')
    state.setdefault('import_path', '')
    state.setdefault('import_cursor', 0)
    _purge_persistent_graphics_thumbnail_cache(app)
    return state



def _set_scene_text(app, text: str, *, row: int | None = None, col: int | None = None) -> None:
    state = _graphics_lab_store(app)
    value = str(text or '')
    state['scene_text'] = value
    lines = value.split('\n') if value else ['']
    row = len(lines) - 1 if row is None else max(0, min(int(row), len(lines) - 1))
    col_default = len(lines[row])
    col = col_default if col is None else max(0, min(int(col), len(lines[row])))
    state['editor_row'] = row
    state['editor_col'] = col



def _load_scene_preset(app, preset_key: str, preset_label: str, *, open_editor: bool = True) -> None:
    state = _graphics_lab_store(app)
    _set_scene_text(app, graphics.scene_json_for_preset(preset_key))
    state['scene_label'] = preset_label
    state['scene_source'] = f'preset:{preset_key}'
    state['last_error'] = ''
    _record_activity(app, f'Loaded graphics scene preset ({preset_label})')
    app.set_status(f'Scene preset: {preset_label}')
    if open_editor:
        open_scene_editor(app)



def _make_load_preset_action(label: str, key: str):
    def action(app):
        _load_scene_preset(app, key, label, open_editor=True)
    return action



def _graphics_recent_lines(app):
    items = graphics.latest_exports(app, limit=6)
    if not items:
        return ['No graphics exports yet.']
    out = []
    for item in items:
        detail = str(item.get('detail', '') or '').strip()
        suffix = f'  ({detail})' if detail else ''
        out.append(f"- {item.get('kind', 'item')}: {item.get('path', '')}{suffix}")
    return out



def _scene_summary_lines(scene_text: str) -> list[str]:
    try:
        payload = json.loads(str(scene_text or '{}'))
        if not isinstance(payload, dict):
            return ['Scene JSON must decode to an object.']
    except Exception as exc:
        return [f'JSON error: {exc}']
    camera = payload.get('camera', {}) if isinstance(payload.get('camera'), dict) else {}
    objects = payload.get('objects', []) if isinstance(payload.get('objects'), list) else []
    lights = payload.get('lights', []) if isinstance(payload.get('lights'), list) else []
    lines = [
        f"Camera origin: {camera.get('origin', '(missing)')}",
        f"Objects: {len(objects)}",
        f"Lights: {len(lights)}",
    ]
    if objects:
        kinds: list[str] = []
        for obj in objects[:3]:
            if isinstance(obj, dict):
                kinds.append(str(obj.get('kind', '?')))
        if kinds:
            lines.append(f"Kinds: {', '.join(kinds)}")
    return lines



def render_graphics_lab_panel(app):
    state = _graphics_lab_store(app)
    print('Graphics image workspace.')
    print('Use a preset or import a scene JSON, edit it, then press Render.')
    print('')
    print(f"Current scene: {state.get('scene_label', 'Scene')}")
    print(f"Source: {state.get('scene_source', 'local draft')}")
    print('')
    for line in _scene_summary_lines(state.get('scene_text', '')):
        print(line)
    print('')
    print('Thumbnail')
    for line in _graphics_thumbnail_lines(app, state.get('last_render_path', '')):
        print(line)
    print('')
    if state.get('last_render_path'):
        print(f"Preview: {state.get('last_render_path')}")
        kind = str(state.get('last_render_kind') or 'image')
        print(f"Last kind: {kind}")
        if state.get('last_width') and state.get('last_height'):
            print(f"Size: {state.get('last_width')}x{state.get('last_height')}")
    else:
        print('Preview: not rendered yet')
    if state.get('last_scene_json_path'):
        print(f"Scene JSON: {state.get('last_scene_json_path')}")
    if state.get('last_render_at'):
        print(f"Updated: {state.get('last_render_at')}")
    if state.get('last_error'):
        print('')
        print(f"Last error: {state.get('last_error')}")
    print('')
    print('Recent')
    for line in _graphics_recent_lines(app)[:3]:
        print(line)



def render_current_scene(app):
    state = _graphics_lab_store(app)
    try:
        result = graphics.render_lab_scene_text(
            app,
            state.get('scene_text', ''),
            width=GRAPHICS_PREVIEW_WIDTH,
            height=GRAPHICS_PREVIEW_HEIGHT,
            spp=GRAPHICS_PREVIEW_SPP,
        )
    except Exception as exc:
        state['last_error'] = str(exc)
        app.set_status(f'Render error: {exc}')
        return
    state['last_error'] = ''
    cache_state = getattr(app, '_graphics_lab_thumbnail_cache', None)
    if isinstance(cache_state, dict):
        cache_state.clear()
    state['last_render_kind'] = 'scene3d'
    state['last_render_path'] = result['current_path']
    state['last_scene_json_path'] = result['scene_json_path']
    state['last_render_at'] = graphics.latest_exports(app, limit=1)[0].get('created_at', '') if graphics.latest_exports(app, limit=1) else ''
    state['last_width'] = result['width']
    state['last_height'] = result['height']
    _record_activity(app, 'Rendered current graphics lab scene')
    app.set_status(f"Render: {result['current_path']}")



def render_image2d_poster(app):
    state = _graphics_lab_store(app)
    rel = graphics.render_image2d_sample(app, width=256, height=144)
    state['last_error'] = ''
    state['last_render_kind'] = 'image2d'
    state['last_render_path'] = rel
    state['last_scene_json_path'] = ''
    latest = graphics.latest_exports(app, limit=1)
    state['last_render_at'] = latest[0].get('created_at', '') if latest else ''
    state['last_width'] = 256
    state['last_height'] = 144
    _record_activity(app, 'Rendered 2D poster image')
    app.set_status(f'2D image: {rel}')



def open_scene_editor(app):
    state = _graphics_lab_store(app)
    try:
        app.screens['graphics_scene_editor']['main_title'] = f"Scene JSON — {state.get('scene_label', 'Current Scene')}"
    except Exception:
        pass
    _goto_screen(app, 'graphics_scene_editor')



def open_import_scene_screen(app):
    state = _graphics_lab_store(app)
    source = _display_path(str(state.get('scene_source') or ''))
    state['import_path'] = source if source and not source.startswith('preset:') else ''
    state['import_cursor'] = len(state['import_path'])
    _goto_screen(app, 'graphics_scene_import')



def _graphics_editor_size(app) -> tuple[int, int]:
    return _fullscreen_editor_size(
        app,
        'graphics_scene_editor',
        'graphics_scene_editor_width',
        'graphics_scene_editor_height',
        'graphics_scene_editor_width',
        'graphics_scene_editor_height',
        GRAPHICS_EDITOR_WIDTH,
        GRAPHICS_EDITOR_HEIGHT,
        min_height=6,
    )



def _graphics_scene_lines(app) -> list[str]:
    text = str(_graphics_lab_store(app).get('scene_text', '') or '')
    lines = text.split('\n')
    return lines if lines else ['']



def _graphics_scene_position(app) -> tuple[int, int]:
    state = _graphics_lab_store(app)
    lines = _graphics_scene_lines(app)
    row = max(0, min(int(state.get('editor_row', 0) or 0), len(lines) - 1))
    col = max(0, min(int(state.get('editor_col', 0) or 0), len(lines[row])))
    return row, col



def _set_graphics_scene_state(app, lines: list[str], row: int | None = None, col: int | None = None) -> None:
    clean_lines = [str(line) for line in (lines or [''])]
    if not clean_lines:
        clean_lines = ['']
    row = len(clean_lines) - 1 if row is None else max(0, min(int(row), len(clean_lines) - 1))
    col_default = len(clean_lines[row])
    col = col_default if col is None else max(0, min(int(col), len(clean_lines[row])))
    state = _graphics_lab_store(app)
    state['scene_text'] = '\n'.join(clean_lines)
    state['editor_row'] = row
    state['editor_col'] = col



def _graphics_scene_window(app, width: int, height: int) -> tuple[list[str], int, int, int, int]:
    width = max(8, int(width))
    height = max(4, int(height))
    lines = _graphics_scene_lines(app)
    row, col = _graphics_scene_position(app)
    max_vstart = max(0, len(lines) - height)
    pad_y = min(2, max(1, height // 4))
    vstart = max(0, min(row - pad_y, max_vstart))
    if row >= vstart + height:
        vstart = min(max_vstart, row - height + 1)
    elif row < vstart:
        vstart = max(0, row)
    max_hstart = max(0, max((len(line) for line in lines), default=0) - width)
    pad_x = min(6, max(2, width // 5))
    hstart = max(0, min(col - pad_x, max_hstart))
    if col >= hstart + width:
        hstart = min(max_hstart, col - width + 1)
    elif col < hstart:
        hstart = max(0, col)
    visible = []
    for idx in range(vstart, min(vstart + height, len(lines))):
        visible.append(lines[idx][hstart:hstart + width])
    while len(visible) < height:
        visible.append('')
    return visible, vstart, hstart, row, col



def _graphics_scene_canvas_lines(app, width: int, height: int) -> list[str]:
    visible, vstart, hstart, row, col = _graphics_scene_window(app, width, height)
    target_index = row - vstart
    target_col = col - hstart
    out: list[str] = []
    for idx, line in enumerate(visible):
        out.append(
            _notes_render_canvas_row(
                app,
                line,
                target_col if idx == target_index and 0 <= target_index < height else -1,
                width,
                insert_mode=True,
            )
        )
    return out



def render_graphics_scene_editor_panel(app):
    state = _graphics_lab_store(app)
    width, height = _graphics_editor_size(app)
    print('Edit the current scene JSON.')
    print('Esc saves and returns to Graphics Lab.')
    print('')
    print(f"Scene: {state.get('scene_label', 'Current Scene')}")
    print(f"Source: {state.get('scene_source', 'local draft')}")
    print('')
    for line in _graphics_scene_canvas_lines(app, width=width, height=height):
        print(line)



def handle_graphics_scene_editor_key(app, key: str):
    lines = _graphics_scene_lines(app)
    row, col = _graphics_scene_position(app)
    if key == 'ESC':
        app.go_back()
        return True
    if key == 'UP':
        row = max(0, row - 1)
        col = min(col, len(lines[row]))
        _set_graphics_scene_state(app, lines, row, col)
        return True
    if key == 'DOWN':
        row = min(len(lines) - 1, row + 1)
        col = min(col, len(lines[row]))
        _set_graphics_scene_state(app, lines, row, col)
        return True
    if key == 'LEFT':
        if col > 0:
            col -= 1
        elif row > 0:
            row -= 1
            col = len(lines[row])
        _set_graphics_scene_state(app, lines, row, col)
        return True
    if key == 'RIGHT':
        if col < len(lines[row]):
            col += 1
        elif row < len(lines) - 1:
            row += 1
            col = 0
        _set_graphics_scene_state(app, lines, row, col)
        return True
    if key == 'HOME':
        _set_graphics_scene_state(app, lines, row, 0)
        return True
    if key == 'END':
        _set_graphics_scene_state(app, lines, row, len(lines[row]))
        return True
    if key == 'ENTER':
        left = lines[row][:col]
        right = lines[row][col:]
        lines[row] = left
        lines.insert(row + 1, right)
        _set_graphics_scene_state(app, lines, row + 1, 0)
        return True
    if key == 'BACKSPACE':
        if col > 0:
            lines[row] = lines[row][:col - 1] + lines[row][col:]
            _set_graphics_scene_state(app, lines, row, col - 1)
            return True
        if row > 0:
            merged_col = len(lines[row - 1])
            lines[row - 1] += lines[row]
            lines.pop(row)
            _set_graphics_scene_state(app, lines, row - 1, merged_col)
            return True
        return True
    if key == 'DELETE':
        if col < len(lines[row]):
            lines[row] = lines[row][:col] + lines[row][col + 1:]
            _set_graphics_scene_state(app, lines, row, col)
            return True
        if row < len(lines) - 1:
            lines[row] += lines[row + 1]
            lines.pop(row + 1)
            _set_graphics_scene_state(app, lines, row, col)
            return True
        return True
    if len(key) == 1 and key not in {'\x00', '\x1b'}:
        lines[row] = lines[row][:col] + key + lines[row][col:]
        _set_graphics_scene_state(app, lines, row, col + 1)
        return True
    return True



def _graphics_import_size(app) -> tuple[int, int]:
    return _fullscreen_editor_size(
        app,
        'graphics_scene_import',
        'graphics_import_width',
        'graphics_import_height',
        'graphics_import_width',
        'graphics_import_height',
        GRAPHICS_IMPORT_WIDTH,
        GRAPHICS_IMPORT_HEIGHT,
        min_height=4,
    )



def _resolve_import_path(raw_path: str) -> str:
    value = os.path.expanduser(str(raw_path or '').strip())
    if not value:
        raise ValueError('Enter a scene JSON path.')
    if os.path.isabs(value):
        return value
    project_candidate = os.path.abspath(os.path.join(PROJECT_ROOT, value))
    if os.path.exists(project_candidate):
        return project_candidate
    return os.path.abspath(value)



def _apply_import_scene_path(app) -> None:
    state = _graphics_lab_store(app)
    resolved = _resolve_import_path(state.get('import_path', ''))
    with open(resolved, 'r', encoding='utf-8') as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError('Imported JSON must decode to an object.')
    _set_scene_text(app, json.dumps(payload, indent=2, ensure_ascii=False) + '\n')
    shown = _display_path(resolved)
    state['scene_label'] = os.path.basename(resolved)
    state['scene_source'] = shown
    state['last_error'] = ''
    _record_activity(app, f'Imported graphics scene {shown}')
    app.set_status(f'Imported scene: {shown}')



def _import_scene_window(app, width: int) -> tuple[str, int]:
    state = _graphics_lab_store(app)
    value = str(state.get('import_path', '') or '')
    cursor = max(0, min(int(state.get('import_cursor', len(value)) or 0), len(value)))
    max_hstart = max(0, len(value) - width)
    pad = min(8, max(2, width // 5))
    hstart = max(0, min(cursor - pad, max_hstart))
    if cursor >= hstart + width:
        hstart = min(max_hstart, cursor - width + 1)
    elif cursor < hstart:
        hstart = max(0, cursor)
    return value[hstart:hstart + width], cursor - hstart



def render_graphics_import_panel(app):
    width, _ = _graphics_import_size(app)
    line, cursor = _import_scene_window(app, width)
    state = _graphics_lab_store(app)
    print('Import a scene JSON file into Graphics Lab.')
    print('Relative paths are resolved from the project root first.')
    print('')
    print(_notes_render_canvas_row(app, line, cursor, width, insert_mode=True))
    print('')
    current_source = str(state.get('scene_source') or '')
    if current_source:
        print(f'Current source: {current_source}')
    print('Example: runtime/exports/graphics/lab/current_lab.json')



def handle_graphics_import_key(app, key: str):
    state = _graphics_lab_store(app)
    value = str(state.get('import_path', '') or '')
    cursor = max(0, min(int(state.get('import_cursor', len(value)) or 0), len(value)))
    if key == 'ESC':
        app.go_back()
        return True
    if key == 'LEFT':
        state['import_cursor'] = max(0, cursor - 1)
        return True
    if key == 'RIGHT':
        state['import_cursor'] = min(len(value), cursor + 1)
        return True
    if key == 'HOME':
        state['import_cursor'] = 0
        return True
    if key == 'END':
        state['import_cursor'] = len(value)
        return True
    if key == 'BACKSPACE':
        if cursor > 0:
            state['import_path'] = value[:cursor - 1] + value[cursor:]
            state['import_cursor'] = cursor - 1
        return True
    if key == 'DELETE':
        if cursor < len(value):
            state['import_path'] = value[:cursor] + value[cursor + 1:]
            state['import_cursor'] = cursor
        return True
    if key == 'ENTER':
        try:
            _apply_import_scene_path(app)
        except Exception as exc:
            state['last_error'] = str(exc)
            app.set_status(f'Import error: {exc}')
            return True
        app.go_back()
        return True
    if len(key) == 1 and key not in {'\x00', '\x1b'}:
        state['import_path'] = value[:cursor] + key + value[cursor:]
        state['import_cursor'] = cursor + 1
        return True
    return True



def register_graphics_lab_screen(app) -> None:
    preset_actions = [_make_load_preset_action(label, key) for label, key in GRAPHICS_SCENE_PRESETS]
    preset_labels = [f'New {label}' for label, _ in GRAPHICS_SCENE_PRESETS]
    app.add_screen(
        name='graphics_lab',
        title='Graphics Lab',
        options=[*preset_labels, 'Edit Scene JSON', 'Import Scene JSON', 'Render'],
        actions=[*preset_actions, open_scene_editor, open_import_scene_screen, render_current_scene],
        main_panel=render_graphics_lab_panel,
        main_title='Preview Canvas',
        screen_type='workspace_split',
        hotkeys={
            'd': preset_actions[0],
            'c': preset_actions[1] if len(preset_actions) > 1 else open_scene_editor,
            't': preset_actions[2] if len(preset_actions) > 2 else open_scene_editor,
            'o': preset_actions[3] if len(preset_actions) > 3 else open_scene_editor,
            'k': preset_actions[4] if len(preset_actions) > 4 else open_scene_editor,
            'e': open_scene_editor,
            'i': open_import_scene_screen,
            'r': render_current_scene,
            'p': render_image2d_poster,
            'v': open_graphics_preview_surface,
            'b': 'back',
        },
    )
    app.screens['graphics_lab']['title_style'] = 'plain'
    app.screens['graphics_lab']['show_utility_bar'] = False
    app.screens['graphics_lab']['main_panel_width'] = 72
    app.screens['graphics_lab']['panel_mode'] = 'auto'
    app.screens['graphics_lab']['main_columns'] = 2
    app.screens['graphics_lab']['menu_box_gap'] = 2
    app.screens['graphics_lab']['menu_row_gap'] = 0
    app.screens['graphics_lab']['nav_options'] = []
    app.screens['graphics_lab']['nav_actions'] = []
    app.screens['graphics_lab']['footer_text'] = '[Enter] Open  [E] Edit  [I] Import JSON  [R] Render  [V] View Real Image  [P] 2D Poster  [Esc] Back'

    app.add_screen(
        name='graphics_scene_editor',
        title='Graphics Scene Editor',
        options=[],
        actions=[],
        main_panel=render_graphics_scene_editor_panel,
        main_title='Scene JSON',
        screen_type='workspace_full',
    )
    app.screens['graphics_scene_editor']['interaction_mode'] = 'typing'
    app.screens['graphics_scene_editor']['hide_menu'] = True
    app.screens['graphics_scene_editor']['on_key'] = handle_graphics_scene_editor_key
    app.screens['graphics_scene_editor']['graphics_scene_editor_width_fill'] = True
    app.screens['graphics_scene_editor']['graphics_scene_editor_height_fill'] = True
    app.screens['graphics_scene_editor']['footer_text'] = '[Arrows] Move  [Enter] New Line  [Backspace/Delete] Edit  [Esc] Save + Back'

    app.add_screen(
        name='graphics_scene_import',
        title='Import Scene JSON',
        options=[],
        actions=[],
        main_panel=render_graphics_import_panel,
        main_title='Import Scene JSON',
        screen_type='workspace_full',
    )
    app.screens['graphics_scene_import']['interaction_mode'] = 'typing'
    app.screens['graphics_scene_import']['hide_menu'] = True
    app.screens['graphics_scene_import']['on_key'] = handle_graphics_import_key
    app.screens['graphics_scene_import']['graphics_import_width_fill'] = True
    app.screens['graphics_scene_import']['graphics_import_height_fill'] = False
    app.screens['graphics_scene_import']['footer_text'] = '[Type Path]  [Enter] Import  [Esc] Back'
