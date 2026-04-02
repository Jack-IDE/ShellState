"""Core shell screen registration."""

import os

from shellstate.core.engine import A
from shellstate.core.runtime_model import (
    DATA_FILE,
    PROJECT_ROOT,
    _SPEED_DIAL_MAX_SLOTS,
    _editor_store,
    _notes_store,
    _recent_activity,
    _recent_exports,
    _speed_dials,
    _system_store,
    graphics,
)


def render_settings(app):
    return


def render_system_panel(app):
    system = _system_store(app)
    notes_count = len(_notes_store(app).get('notes', []))
    draft_count = len(_editor_store(app).get('drafts', {}))
    recent_exports = len(_recent_exports(app))
    recent_activity = len(_recent_activity(app))
    speed_dials = _speed_dials(app)
    graphics_items = graphics.latest_exports(app, limit=3)
    term_size = f"{int(app._terminal_width())}x{int(app._terminal_height())}"
    data_file = os.path.relpath(DATA_FILE, PROJECT_ROOT)

    lines = [
        'State shell with one main save.',
        f'Save file: {data_file}',
        'System keeps prefs, dials, activity.',
        'Apps keep notes, drafts, tool data.',
        'Boot loads state, then fills defaults.',
        'Saves write temp first, then replace.',
        'Snapshots stay separate from the main save.',
        'Graphics remains a dedicated subsystem launched from Utilities.',
        '',
        f"Ver {system.get('version', 2)}   Term {term_size}",
        f'Dials {len(speed_dials)}/{_SPEED_DIAL_MAX_SLOTS}   Drafts {draft_count}',
        f'Notes {notes_count}   Act {recent_activity}   Exp {recent_exports}',
        '',
        'Recent graphics exports:',
    ]
    if graphics_items:
        for item in graphics_items:
            lines.append(f"  {item.get('kind', 'item')}: {item.get('path', '')}")
    else:
        lines.append('  none yet')
    for line in lines:
        print(line)


def register_shell_screens(app) -> None:
    app.add_screen(
        name='settings',
        title='Settings',
        options=['Export Center', 'System', 'Exit', 'Back'],
        actions=['saves', 'system', A.exit(), 'back'],
        on_render=render_settings,
        hotkeys={'b': 'back', 'v': 'saves', 'i': 'system', 'q': A.exit()},
    )

    app.add_screen(
        name='system',
        title='System',
        options=['Back'],
        actions=['back'],
        main_panel=render_system_panel,
        main_title='State / Save',
        panel_mode='auto',
        panel_min_height=14,
        hotkeys={'b': 'back'},
    )
    app.screens['system']['main_panel_width'] = 54

    app.add_screen(
        name='utilities',
        title='Utilities',
        options=['Program Maker', 'Calculator', 'Quick Notes', 'Unit Converter', 'Graphics Lab', 'Back'],
        actions=['program_maker', 'calculator', 'notes', 'converter', 'graphics_lab', 'back'],
        hotkeys={'b': 'back', 'p': 'program_maker', 'c': 'calculator', 'n': 'notes', 'u': 'converter', 'g': 'graphics_lab'},
    )

    app.add_screen(
        name='main',
        title='HOME',
        options=['Utilities', 'Settings'],
        actions=['utilities', 'settings'],
        hotkeys={'u': 'utilities', 's': 'settings'},
        screen_type='home',
    )
