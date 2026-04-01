"""Shared shell hubs, speed dials, and home screen wiring."""

from shellstate.runtime_model import *

def render_settings(app):
    return
app.add_screen(
    name="settings",
    title="Settings",
    options=[
        "Export Center",
        "System",
        "Exit",
        "Back",
    ],
    actions=[
        "saves",
        "system",
        A.exit(),
        "back",
    ],
    on_render=render_settings,
    hotkeys={"b": "back", "v": "saves", "i": "system", "q": A.exit()},
)


def render_system_panel(app):
    system = _system_store(app)
    notes_count = len(_notes_store(app).get("notes", []))
    draft_count = len(_editor_store(app).get("drafts", {}))
    recent_exports = len(_recent_exports(app))
    recent_activity = len(_recent_activity(app))
    speed_dials = _speed_dials(app)
    term_size = f"{int(app._terminal_width())}x{int(app._terminal_height())}"
    data_file = os.path.relpath(DATA_FILE, PROJECT_ROOT)

    lines = [
        "State shell with one main save.",
        f"Save file: {data_file}",
        "System keeps prefs, dials, activity.",
        "Apps keep notes, drafts, tool data.",
        "Boot loads state, then fills defaults.",
        "Saves write temp first, then replace.",
        "Snapshots stay separate from the main save.",
        "Use Export Center to export or import data.",
        "",
        f"Ver {system.get('version', 2)}   Term {term_size}",
        f"Dials {len(speed_dials)}/{_SPEED_DIAL_MAX_SLOTS}   Drafts {draft_count}",
        f"Notes {notes_count}   Act {recent_activity}   Exp {recent_exports}",
    ]
    for line in lines:
        print(line)

app.add_screen(
    name="system",
    title="System",
    options=["Back"],
    actions=["back"],
    main_panel=render_system_panel,
    main_title="State / Save",
    panel_mode="auto",
    panel_min_height=14,
    hotkeys={"b": "back"},
)
app.screens["system"]["main_panel_width"] = 54


app.add_screen(
    name="utilities",
    title="Utilities",
    options=["Program Maker", "Calculator", "Quick Notes", "Unit Converter", "Back"],
    actions=["program_maker", "calculator", "notes", "converter", "back"],
    hotkeys={"b": "back", "p": "program_maker", "c": "calculator", "n": "notes", "u": "converter"},
)


# ─────────────────────────────────────────────────────────────────
#  SPEED DIALS
# ─────────────────────────────────────────────────────────────────


def _speed_dial_choice_index_for_target(target: str) -> int:
    for idx, (_, key) in enumerate(_SPEED_DIAL_CHOICES):
        if key == target:
            return idx
    return 0


def _speed_dial_ui_state(app) -> dict:
    system = _system_store(app)
    state = system.setdefault("speed_dial_ui", {})
    if not isinstance(state, dict):
        state = {}
        system["speed_dial_ui"] = state
    slot_count = _speed_dial_slot_count(app)
    raw_slot_index = state.get("slot_index", 0)
    try:
        slot_index = int(raw_slot_index)
    except (TypeError, ValueError):
        slot_index = 0
    if slot_count <= 0:
        slot_index = 0
    else:
        slot_index = max(0, min(slot_index, slot_count - 1))
    raw_choice_index = state.get("choice_index", 0)
    try:
        choice_index = int(raw_choice_index)
    except (TypeError, ValueError):
        choice_index = 0
    choice_index = max(0, min(choice_index, len(_SPEED_DIAL_CHOICES) - 1))
    state["slot_index"] = slot_index
    state["choice_index"] = choice_index
    return state


def _speed_dial_sync_choice_to_slot(app) -> None:
    state = _speed_dial_ui_state(app)
    slot_index = int(state.get("slot_index", 0) or 0)
    dials = _speed_dials(app)
    target = dials[slot_index] if 0 <= slot_index < len(dials) else ""
    state["choice_index"] = _speed_dial_choice_index_for_target(target)


def _set_speed_dial_slot_cursor(app, slot_index: int) -> None:
    state = _speed_dial_ui_state(app)
    slot_count = _speed_dial_slot_count(app)
    if slot_count <= 0:
        state["slot_index"] = 0
    else:
        state["slot_index"] = max(0, min(int(slot_index), slot_count - 1))
    _speed_dial_sync_choice_to_slot(app)


def _speed_dial_assign_current_choice(app) -> None:
    state = _speed_dial_ui_state(app)
    slot_index = int(state.get("slot_index", 0) or 0)
    choice_index = int(state.get("choice_index", 0) or 0)
    choice_index = max(0, min(choice_index, len(_SPEED_DIAL_CHOICES) - 1))
    label, target = _SPEED_DIAL_CHOICES[choice_index]
    dials = _speed_dials(app)
    if not dials:
        app.set_status("Add a speed dial slot first.")
        return
    dials[slot_index] = target
    _system_store(app)["speed_dials"] = dials
    _configure_home_screen(app)
    _record_activity(app, f"Set speed dial {slot_index + 1} to {label}")
    app.set_status(f"Speed Dial {slot_index + 1}: {label}")


def _add_speed_dial_slot(app) -> None:
    dials = _speed_dials(app)
    if len(dials) >= _SPEED_DIAL_MAX_SLOTS:
        app.set_status(f"Speed dials already at max ({_SPEED_DIAL_MAX_SLOTS}).")
        return
    dials.append("")
    _system_store(app)["speed_dials"] = dials
    _set_speed_dial_slot_cursor(app, len(dials) - 1)
    _configure_home_screen(app)
    _record_activity(app, "Added speed dial slot")
    app.set_status(f"Added speed dial slot {len(dials)}.")


def _delete_speed_dial_slot(app) -> None:
    dials = _speed_dials(app)
    if not dials:
        app.set_status("No speed dial slots to delete.")
        return
    state = _speed_dial_ui_state(app)
    slot_index = max(0, min(int(state.get("slot_index", 0) or 0), len(dials) - 1))
    removed_label = _speed_dial_label_from_target(dials[slot_index])
    del dials[slot_index]
    _system_store(app)["speed_dials"] = dials
    _set_speed_dial_slot_cursor(app, min(slot_index, len(dials) - 1))
    _configure_home_screen(app)
    _record_activity(app, f"Deleted speed dial slot {slot_index + 1}")
    if dials:
        app.set_status(f"Deleted speed dial slot {slot_index + 1} ({removed_label}).")
    else:
        app.set_status("Deleted last speed dial slot.")


def _reset_speed_dials(app) -> None:
    _system_store(app)["speed_dials"] = list(_SPEED_DIAL_DEFAULTS)
    _set_speed_dial_slot_cursor(app, 0)
    _configure_home_screen(app)
    _record_activity(app, "Reset speed dials")
    app.set_status("Speed dials reset.")


def _speed_dial_style(app, text: str, *, selected: bool = False) -> str:
    value = str(text)
    if not selected:
        return value
    if getattr(app, "_ansi_enabled", False):
        return f"[7m{value}[0m"
    return f"> {value} <"


def render_speed_dials_panel(app):
    width = max(40, int(app._terminal_width()))
    state = _speed_dial_ui_state(app)
    slot_index = int(state.get("slot_index", 0) or 0)
    choice_index = int(state.get("choice_index", 0) or 0)
    dials = _speed_dials(app)
    slot_count = len(dials)

    if slot_count <= 0:
        print(app._align_line("No speed dial slots.", max(20, width - 8), "center"))
        print("")
        print(app._align_line("Press [A] to add one.", max(20, width - 8), "center"))
        print("")
        print("  Slot controls: [A] Add  [R] Reset")
        return

    slot_chunks = []
    for idx in range(slot_count):
        label = _speed_dial_label_from_target(dials[idx])
        chunk = f"[{idx + 1}] {label}"
        slot_chunks.append(_speed_dial_style(app, chunk, selected=(idx == slot_index)))
    slot_line = "   ".join(slot_chunks)
    print(app._align_line(slot_line, max(20, width - 8), "center"))
    print("")
    print(f"  Editing slot {slot_index + 1} of {slot_count}")
    print(f"  Slot controls: [A] Add  [D] Delete  [R] Reset")
    print("")
    print("  Targets")
    current_target = dials[slot_index] if 0 <= slot_index < slot_count else ""
    for idx, (label, target) in enumerate(_SPEED_DIAL_CHOICES):
        assigned = "*" if current_target == target else " "
        marker = "→" if idx == choice_index else " "
        line = f"{marker} [{assigned}] {label}"
        print("  " + _speed_dial_style(app, line, selected=(idx == choice_index)))


def handle_speed_dials_key(app, key: str):
    state = _speed_dial_ui_state(app)
    slot_index = int(state.get("slot_index", 0) or 0)
    choice_index = int(state.get("choice_index", 0) or 0)

    if key == "ESC":
        app.go_back()
        return True
    if key in {"b", "B"}:
        app.go_back()
        return True
    if key == "LEFT":
        _set_speed_dial_slot_cursor(app, max(0, slot_index - 1))
        return True
    if key == "RIGHT":
        _set_speed_dial_slot_cursor(app, slot_index + 1)
        return True
    if key in {"a", "A"}:
        _add_speed_dial_slot(app)
        return True
    if key in {"d", "D", "BACKSPACE", "DELETE"}:
        _delete_speed_dial_slot(app)
        return True
    if key == "UP":
        state["choice_index"] = (choice_index - 1) % len(_SPEED_DIAL_CHOICES)
        return True
    if key == "DOWN":
        state["choice_index"] = (choice_index + 1) % len(_SPEED_DIAL_CHOICES)
        return True
    if key == "ENTER":
        _speed_dial_assign_current_choice(app)
        return True
    if key in {"r", "R"}:
        _reset_speed_dials(app)
        return True
    if key.isdigit() and 1 <= int(key) <= _SPEED_DIAL_MAX_SLOTS:
        _set_speed_dial_slot_cursor(app, int(key) - 1)
        return True
    return True


def enter_speed_dials(app, previous=None):
    _speed_dial_sync_choice_to_slot(app)


app.add_screen(
    name="speed_dials",
    title="Speed Dials",
    options=[],
    actions=[],
    on_enter=enter_speed_dials,
    main_panel=render_speed_dials_panel,
    main_title="Set Speed Dial",
    screen_type="workspace_full",
)
app.screens["speed_dials"]["interaction_mode"] = "typing"
app.screens["speed_dials"]["hide_menu"] = True
app.screens["speed_dials"]["on_key"] = handle_speed_dials_key
app.screens["speed_dials"]["footer_text"] = "[Left/Right] Slot  [Up/Down] Target  [Enter] Assign  [A] Add  [D] Delete  [R] Reset  [Esc] Back"


# ─────────────────────────────────────────────────────────────────
#  MAIN MENU
# ─────────────────────────────────────────────────────────────────


def render_main(app):
    return None
app.add_screen(
    name="main",
    title="HOME",
    options=["Utilities", "Settings"],
    actions=["utilities", "settings"],
    on_render=render_main,
    hotkeys={
        "u": "utilities",
        "s": "settings",
    },
    screen_type="home",
)


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



def _configure_home_screen(app) -> None:
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
    main_screen.setdefault("hotkeys", {})
    main_screen["hotkeys"].update({
        "u": "utilities",
        "s": "settings",
    })
    for idx in range(_SPEED_DIAL_MAX_SLOTS):
        key = str(idx + 1)
        if idx < len(speed_actions):
            main_screen["hotkeys"][key] = speed_actions[idx]
        else:
            main_screen["hotkeys"].pop(key, None)


def _configure_settings_screen(app) -> None:
    screen = app.screens.get("settings")
    if not screen:
        return
    screen["options"] = ["Speed Dials", "Export Center", "System", "Exit", "Back"]
    screen["actions"] = ["speed_dials", "saves", "system", A.exit(), "back"]
    screen.setdefault("hotkeys", {})
    screen["hotkeys"].update({"d": "speed_dials", "v": "saves", "i": "system", "q": A.exit()})


def _normalize_navigation(app) -> None:
    for name, screen in app.screens.items():
        if name == "main":
            continue
        options = list(screen.get("options", []))
        actions = list(screen.get("actions", []))
        new_options = []
        new_actions = []
        for option, action in zip(options, actions):
            if isinstance(action, str) and action in {"main", "home"}:
                continue
            if isinstance(option, str) and option == "Home":
                continue
            if isinstance(action, str) and action == "back" and isinstance(option, str) and option == "Back":
                continue
            new_options.append(option)
            new_actions.append(action)
        screen["options"] = new_options
        screen["actions"] = new_actions
        screen["nav_options"] = ["Home", "Back"]
        screen["nav_actions"] = ["home", "back"]
        hotkeys = screen.setdefault("hotkeys", {})
        hotkeys.setdefault("h", "home")
        hotkeys.setdefault("b", "back")


def _apply_screen_types(app) -> None:
    screen_types = {
        "main": "home",
        "utilities": "hub",
        "settings": "hub",
        "speed_dials": "workspace_full",
        "calculator": "workspace_full",
        "saves": "detail",
        "system": "detail",
    }
    for name, screen in app.screens.items():
        screen["screen_type"] = screen_types.get(name, screen.get("screen_type") or "menu")
        for key in ("title_style", "title_align", "menu_layout", "menu_align", "show_utility_bar"):
            if key in screen:
                screen[key] = None

        if name == "calculator":
            for key in ("panel_mode", "info_panel_ratio", "panel_min_height"):
                if key in screen:
                    screen[key] = None


def _finalize_shell_ui(app) -> None:
    _configure_settings_screen(app)
    _configure_home_screen(app)
    _normalize_navigation(app)
    _apply_screen_types(app)


_finalize_shell_ui(app)
