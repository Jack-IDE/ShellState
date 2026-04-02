"""Home-screen shortcut wiring."""

import os

from shellstate.core.engine import A
from shellstate.core.runtime_model import (
    PROJECT_ROOT,
    _SPEED_DIAL_MAX_SLOTS,
    _speed_dial_label_from_target,
    _speed_dial_slot_count,
    _speed_dials,
    graphics,
)
from shellstate.graphics.display import launch_image_surface


def _make_speed_dial_option_label(slot_index: int):
    def label(app):
        dials = _speed_dials(app)
        target = dials[slot_index] if slot_index < len(dials) else ""
        return _speed_dial_label_from_target(target) if target else "Empty"
    return label



def _make_speed_dial_action(slot_index: int):
    def action(app):
        dials = _speed_dials(app)
        target = dials[slot_index] if slot_index < len(dials) else ""
        if target and target in app.screens:
            return target
        app.set_status("Speed dial is empty.")
        return None
    return action





def _open_home_image_surface(app):
    state = graphics.home_scene_state(app)
    abs_path = _home_canvas_abs_path(state.get('path', ''))
    if not abs_path or not os.path.isfile(abs_path):
        app.set_status('No home image is available to open.')
        return None
    ok = launch_image_surface(abs_path, title='ShellState Home Image', follow=True)
    app.set_status('Opened home image window.' if ok else 'Could not open a real image surface.')
    return None


def _configure_home_screen(app) -> None:
    _purge_persistent_home_panel_cache(app)
    main_screen = app.screens.get("main")
    if not main_screen:
        return
    slot_count = _speed_dial_slot_count(app)
    speed_labels = [_make_speed_dial_option_label(i) for i in range(slot_count)]
    speed_actions = [_make_speed_dial_action(i) for i in range(slot_count)]
    main_screen["options"] = ["Utilities", "Settings"]
    main_screen["actions"] = ["utilities", "settings"]
    main_screen["shortcut_options"] = speed_labels
    main_screen["shortcut_actions"] = speed_actions
    main_screen["shortcut_title"] = ""
    main_screen["main_panel"] = render_home_image_panel
    main_screen["main_title"] = ""
    main_screen["panel_mode"] = "auto"
    main_screen["main_panel_width"] = 30
    main_screen["main_panel_square"] = True
    main_screen["main_panel_borderless"] = True
    main_screen["main_panel_below_menu"] = True
    main_screen.setdefault("layout_overrides", {})["show_utility_bar"] = True
    main_screen["main_panel_min_height"] = 14
    main_screen["footer_text"] = "[Arrows] Move  [Enter] Open  [Esc] Back  [U] Utilities  [S] Settings  [1-5] Dials  [O] Open Real Image"
    main_screen.setdefault("hotkeys", {})
    main_screen["hotkeys"].update({
        "u": "utilities",
        "s": "settings",
        "o": _open_home_image_surface,
    })
    for idx in range(_SPEED_DIAL_MAX_SLOTS):
        key = str(idx + 1)
        if idx < len(speed_actions):
            main_screen["hotkeys"][key] = speed_actions[idx]
        else:
            main_screen["hotkeys"].pop(key, None)


HOME_CANVAS_WIDTH = 26
HOME_CANVAS_HEIGHT = 12
HOME_CANVAS_SCALE = 0.86
HOME_CANVAS_SUPERSAMPLE = 2


def _home_canvas_abs_path(path: str) -> str:
    shown = str(path or '').strip()
    if not shown:
        return ''
    if os.path.isabs(shown):
        return shown
    return os.path.abspath(os.path.join(PROJECT_ROOT, shown))


def _purge_persistent_home_panel_cache(app) -> None:
    try:
        system = app.app_data.get('system', {}) if isinstance(getattr(app, 'app_data', None), dict) else {}
    except Exception:
        return
    if isinstance(system, dict) and 'home_panel' in system:
        system.pop('home_panel', None)



def _home_panel_store(app) -> dict:
    _purge_persistent_home_panel_cache(app)
    state = getattr(app, '_home_panel_cache', None)
    if not isinstance(state, dict):
        state = {}
        setattr(app, '_home_panel_cache', state)
    state.setdefault('thumbnail_cache_path', '')
    state.setdefault('thumbnail_cache_mtime', 0.0)
    state.setdefault('thumbnail_cache_mode', '')
    state.setdefault('thumbnail_cache_width', 0)
    state.setdefault('thumbnail_cache_height', 0)
    state.setdefault('thumbnail_lines', [])
    return state


def _cached_home_thumbnail_lines(app, abs_path: str, thumb_w: int, thumb_h: int):
    try:
        from shellstate.apps.graphics_lab import _ansi_dense_sextant_thumbnail_lines
    except Exception as exc:
        if hasattr(app, 'set_status'):
            app.set_status(f"Home image renderer import failed: {exc}")
        return None

    cache_state = _home_panel_store(app)
    try:
        mtime = os.path.getmtime(abs_path)
    except OSError as exc:
        if hasattr(app, 'set_status'):
            app.set_status(f"Home image file unreadable: {exc}")
        return None

    shown = os.path.relpath(abs_path, PROJECT_ROOT) if abs_path.startswith(PROJECT_ROOT) else abs_path
    cache_mode = f"ansi_dense_x{HOME_CANVAS_SUPERSAMPLE}"
    if (
        cache_state.get('thumbnail_cache_path') == shown
        and cache_state.get('thumbnail_cache_mtime') == mtime
        and cache_state.get('thumbnail_cache_mode') == cache_mode
        and int(cache_state.get('thumbnail_cache_width') or 0) == int(thumb_w)
        and int(cache_state.get('thumbnail_cache_height') or 0) == int(thumb_h)
    ):
        cached = cache_state.get('thumbnail_lines')
        if isinstance(cached, list) and cached:
            return [str(line) for line in cached]

    try:
        lines = _ansi_dense_sextant_thumbnail_lines(
            abs_path,
            thumb_w=thumb_w,
            thumb_h=thumb_h,
            supersample=HOME_CANVAS_SUPERSAMPLE,
        )
    except Exception as exc:
        if hasattr(app, 'set_status'):
            app.set_status(f"Home image semigraphics render failed: {exc}")
        return None

    cache_state['thumbnail_cache_path'] = shown
    cache_state['thumbnail_cache_mtime'] = mtime
    cache_state['thumbnail_cache_mode'] = cache_mode
    cache_state['thumbnail_cache_width'] = int(thumb_w)
    cache_state['thumbnail_cache_height'] = int(thumb_h)
    cache_state['thumbnail_lines'] = list(lines)
    return lines


def render_home_image_panel(app):
    state = graphics.home_scene_state(app)
    abs_path = _home_canvas_abs_path(state.get('path', ''))
    if not abs_path or not os.path.isfile(abs_path):
        return

    panel_w = max(1, int(getattr(app, '_panel_render_inner_width', HOME_CANVAS_WIDTH) or HOME_CANVAS_WIDTH))
    panel_h = max(1, int(getattr(app, '_panel_render_inner_height', HOME_CANVAS_HEIGHT) or HOME_CANVAS_HEIGHT))
    thumb_w = max(1, min(panel_w, int(round(panel_w * HOME_CANVAS_SCALE))))
    thumb_h = max(1, min(panel_h, int(round(panel_h * HOME_CANVAS_SCALE))))
    lines = _cached_home_thumbnail_lines(app, abs_path, thumb_w, thumb_h)
    if not lines:
        return

    top_pad = max(0, (panel_h - len(lines)) // 2)
    left_pad = max(0, (panel_w - thumb_w) // 2)
    blank_line = ' ' * panel_w
    for _ in range(top_pad):
        print(blank_line)
    pad = ' ' * left_pad
    for line in lines:
        print(f"{pad}{line}")
    remaining = max(0, panel_h - top_pad - len(lines))
    for _ in range(remaining):
        print(blank_line)
