"""Home-screen image selection and rendering."""

import os

from shellstate.core.runtime_model import PROJECT_ROOT, _record_activity, _system_store, graphics
from shellstate.graphics.display import launch_image_surface

HOME_IMAGE_WIDTH = 256
HOME_IMAGE_HEIGHT = 256
HOME_IMAGE_SPP = 1
HOME_IMAGE_HIDDEN_PRESETS = {'demo', 'city', 'beach_ball'}
HOME_IMAGE_CHOICES = [
    (label, key)
    for label, key in graphics.home_scene_options()
    if key not in HOME_IMAGE_HIDDEN_PRESETS
]


def _choice_label(preset: str) -> str:
    for label, key in HOME_IMAGE_CHOICES:
        if key == preset:
            return label
    return str(preset or 'Off')




def _open_home_image_viewer(app) -> None:
    current = graphics.home_scene_state(app)
    path = str(current.get('path') or '').strip()
    if not path:
        app.set_status('No home image is selected.')
        return
    abs_path = path if os.path.isabs(path) else os.path.abspath(os.path.join(PROJECT_ROOT, path))
    if not os.path.isfile(abs_path):
        app.set_status('Home image file is missing.')
        return
    ok = launch_image_surface(abs_path, title='ShellState Home Image', follow=True)
    app.set_status('Opened home image window.' if ok else 'Could not open a real image surface.')


def _home_image_ui_state(app) -> dict:
    system = _system_store(app)
    state = system.setdefault('home_image_ui', {})
    if not isinstance(state, dict):
        state = {}
        system['home_image_ui'] = state
    raw_index = state.get('choice_index', 0)
    try:
        choice_index = int(raw_index)
    except (TypeError, ValueError):
        choice_index = 0
    choice_index = max(0, min(choice_index, len(HOME_IMAGE_CHOICES) - 1))
    state['choice_index'] = choice_index
    return state


def _sync_home_image_cursor(app) -> None:
    state = _home_image_ui_state(app)
    current = graphics.home_scene_state(app).get('preset', 'off')
    for idx, (_, key) in enumerate(HOME_IMAGE_CHOICES):
        if key == current:
            state['choice_index'] = idx
            return
    state['choice_index'] = 0


def _apply_home_image_choice(app) -> None:
    state = _home_image_ui_state(app)
    choice_index = int(state.get('choice_index', 0) or 0)
    label, preset = HOME_IMAGE_CHOICES[choice_index]
    rel = graphics.render_home_scene(app, preset, width=HOME_IMAGE_WIDTH, height=HOME_IMAGE_HEIGHT, spp=HOME_IMAGE_SPP)
    if preset == 'off':
        _record_activity(app, 'Turned off home image')
        app.set_status('Home image turned off.')
        return
    _record_activity(app, f'Set home image to {label}')
    app.set_status(f'Home image: {rel}')


def _rerender_home_image(app) -> None:
    current = graphics.home_scene_state(app).get('preset', 'off')
    if current == 'off':
        app.set_status('No home image is selected.')
        return
    rel = graphics.render_home_scene(app, current, width=HOME_IMAGE_WIDTH, height=HOME_IMAGE_HEIGHT, spp=HOME_IMAGE_SPP)
    _record_activity(app, f'Re-rendered home image ({_choice_label(current)})')
    app.set_status(f'Home image refreshed: {rel}')


def render_home_image_settings_panel(app):
    state = _home_image_ui_state(app)
    choice_index = int(state.get('choice_index', 0) or 0)
    current = graphics.home_scene_state(app)
    print('Pick a home image scene for the HOME screen canvas.')
    print('')
    print(f"Current: {_choice_label(current.get('preset', 'off'))}")
    if current.get('path'):
        print(f"Render: {current.get('path')}")
        print(f"Size: {current.get('width', 0)}x{current.get('height', 0)}")
    else:
        print('Render: off')
    if current.get('rendered_at'):
        print(f"Updated: {current.get('rendered_at')}")
    print('')
    print('Scenes')
    for idx, (label, key) in enumerate(HOME_IMAGE_CHOICES):
        selected = '→' if idx == choice_index else ' '
        applied = '*' if key == current.get('preset', 'off') else ' '
        print(f'  {selected} [{applied}] {label}')


def handle_home_image_key(app, key: str):
    state = _home_image_ui_state(app)
    choice_index = int(state.get('choice_index', 0) or 0)
    if key == 'ESC':
        app.go_back()
        return True
    if key in {'b', 'B'}:
        app.go_back()
        return True
    if key == 'UP':
        state['choice_index'] = (choice_index - 1) % len(HOME_IMAGE_CHOICES)
        return True
    if key == 'DOWN':
        state['choice_index'] = (choice_index + 1) % len(HOME_IMAGE_CHOICES)
        return True
    if key == 'ENTER':
        _apply_home_image_choice(app)
        return True
    if key in {'r', 'R'}:
        _rerender_home_image(app)
        return True
    if key in {'v', 'V', 'o', 'O'}:
        _open_home_image_viewer(app)
        return True
    return True


def enter_home_image_settings(app, previous=None):
    _sync_home_image_cursor(app)


def register_home_image_screen(app) -> None:
    app.add_screen(
        name='home_image',
        title='Home Image',
        options=[],
        actions=[],
        on_enter=enter_home_image_settings,
        main_panel=render_home_image_settings_panel,
        main_title='Home Screen Image',
        screen_type='workspace_full',
    )
    app.screens['home_image']['interaction_mode'] = 'typing'
    app.screens['home_image']['hide_menu'] = True
    app.screens['home_image']['on_key'] = handle_home_image_key
    app.screens['home_image']['footer_text'] = '[Up/Down] Choose  [Enter] Apply + Render  [R] Re-render  [V] View Real Image  [Esc] Back'
