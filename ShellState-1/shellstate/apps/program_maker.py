"""Program Maker screens and editor behavior."""

from shellstate.core.runtime_model import (
    _current_editor_draft_name,
    _editor_store,
    _notes_store,
    _record_activity,
    _save_current_draft,
    _set_editor_buffer,
)
from shellstate.apps.notes import _fullscreen_editor_size, _notes_render_canvas_row

_PROGRAM_MAKER_ROWS = 8
_PROGRAM_MAKER_COLS = 2
_PROGRAM_MAKER_SLOT_COUNT = _PROGRAM_MAKER_ROWS * _PROGRAM_MAKER_COLS
_PROGRAM_MAKER_ACTION_COUNT = 2
_PROGRAM_DRAFT_NAME_MAX = 20


def _program_display_name(name: str, *, limit: int = _PROGRAM_DRAFT_NAME_MAX) -> str:
    value = str(name or "")
    if limit <= 0 or len(value) <= limit:
        return value
    if limit <= 3:
        return value[:limit]
    return value[: limit - 3] + "..."


def _open_program_editor(app) -> None:
    current = _current_editor_draft_name(app).strip()
    try:
        app.screens["program_editor"]["main_title"] = current or "Program Editor"
    except Exception:
        pass
    row, col = _program_editor_position(app)
    wrapped_lines, row, col = app._multiline_hard_wrap(_program_editor_lines(app), row, col, _program_editor_text_width(app))
    _program_set_editor_state(
        app,
        wrapped_lines,
        row,
        col,
        mark_unsaved=bool(_editor_store(app).get("unsaved", False)),
    )
    setter = getattr(app, "set_screen", None)
    if callable(setter):
        setter("program_editor")
        return
    goto = getattr(app, "goto_screen", None)
    if callable(goto):
        goto("program_editor")
        return
    app.set_status("Draft loaded. Open Program Editor to continue.")


def _draft_names(app) -> list[str]:
    drafts = _editor_store(app).get("drafts", {})
    if not isinstance(drafts, dict):
        return []
    return sorted(str(name) for name in drafts.keys())


def _load_draft_into_editor(app, name: str) -> None:
    drafts = _editor_store(app).get("drafts", {})
    if name not in drafts:
        app.set_status("Draft not found.")
        return
    editor = _editor_store(app)
    editor["current_draft"] = name
    _set_editor_buffer(app, drafts.get(name, ""), mark_unsaved=False)
    _record_activity(app, f"Opened draft '{name}'")
    _open_program_editor(app)


def _next_program_draft_name(app, base: str = "Draft") -> str:
    drafts = _editor_store(app).get("drafts", {})
    existing = {str(name) for name in drafts.keys()} if isinstance(drafts, dict) else set()
    index = 1
    while True:
        candidate = f"{base} {index}"
        if candidate not in existing:
            return candidate
        index += 1


def _program_maker_ui_state(app) -> dict:
    editor = _editor_store(app)
    state = editor.setdefault("maker_ui", {})
    if not isinstance(state, dict):
        state = {}
        editor["maker_ui"] = state
    section = str(state.get("section", "drafts") or "drafts").lower()
    if section not in {"actions", "drafts"}:
        section = "drafts"
    state["section"] = section
    action_col = int(state.get("action_col", 0) or 0)
    state["action_col"] = max(0, min(action_col, 1))
    draft_index = int(state.get("draft_index", 0) or 0)
    state["draft_index"] = max(0, min(draft_index, _PROGRAM_MAKER_SLOT_COUNT - 1))
    return state


def _program_maker_sync_selection(app) -> None:
    state = _program_maker_ui_state(app)
    current = _current_editor_draft_name(app).strip()
    names = _draft_names(app)
    if current in names:
        state["draft_index"] = names.index(current)
    else:
        state["draft_index"] = max(0, min(int(state.get("draft_index", 0) or 0), _PROGRAM_MAKER_SLOT_COUNT - 1))


def _program_maker_entry_text(app, index: int) -> str:
    names = _draft_names(app)
    if index < len(names):
        name = names[index]
        shown = _program_display_name(name)
        if name == _current_editor_draft_name(app).strip():
            return f"[{index + 1:>2}] {shown}  (open)"
        return f"[{index + 1:>2}] {shown}"
    return f"[{index + 1:>2}] (empty)"


def _program_maker_render_action_row(app, selected: bool, action_col: int) -> list[str]:
    gap = " " * 4
    left = app._box_lines("New Draft", selected=selected and action_col == 0)
    right = app._box_lines("Delete Draft", selected=selected and action_col == 1)
    visible_row = app._visible_len(left[0]) + app._visible_len(right[0]) + len(gap)
    pad = " " * max(0, (max(20, int(app._terminal_width()) - 6) - visible_row) // 2)
    return [pad + left[i] + gap + right[i] for i in range(3)]


def render_program_maker_panel(app):
    width = max(48, int(app._terminal_width()) - 6)
    state = _program_maker_ui_state(app)
    section = state.get("section", "drafts")
    action_col = int(state.get("action_col", 0) or 0)
    selected_index = int(state.get("draft_index", 0) or 0)

    for line in _program_maker_render_action_row(app, section == "actions", action_col):
        print(line)
    print("")

    col_gap = 6
    left_width = max(18, (width - col_gap) // 2)
    right_width = max(18, width - col_gap - left_width)
    for row in range(_PROGRAM_MAKER_ROWS):
        left_index = row
        right_index = row + _PROGRAM_MAKER_ROWS
        left_text = _program_maker_entry_text(app, left_index)
        right_text = _program_maker_entry_text(app, right_index)
        left_line = _program_delete_style(app, left_text.ljust(left_width), selected=(section == "drafts" and selected_index == left_index))
        right_line = _program_delete_style(app, right_text.ljust(right_width), selected=(section == "drafts" and selected_index == right_index))
        print(f"  {left_line}{' ' * col_gap}{right_line}")


def render_program_maker(app):
    return


def _program_maker_display_order() -> list[int]:
    order: list[int] = []
    for row in range(_PROGRAM_MAKER_ROWS):
        order.append(row)
        if row + _PROGRAM_MAKER_ROWS < _PROGRAM_MAKER_SLOT_COUNT:
            order.append(row + _PROGRAM_MAKER_ROWS)
    return order


def _program_maker_menu_index_for_slot(slot_index: int) -> int:
    order = _program_maker_display_order()
    try:
        return order.index(slot_index)
    except ValueError:
        return max(0, min(int(slot_index), len(order) - 1))


def _program_maker_option_index_for_slot(slot_index: int) -> int:
    return _PROGRAM_MAKER_ACTION_COUNT + _program_maker_menu_index_for_slot(slot_index)


def enter_program_maker(app, previous=None):
    names = _draft_names(app)
    current = _current_editor_draft_name(app).strip()
    if current in names:
        slot_index = names.index(current)
        app.selected_index = _program_maker_option_index_for_slot(slot_index)
    else:
        app.selected_index = 0


def program_new_draft(app):
    editor = _editor_store(app)
    drafts = editor.setdefault("drafts", {})
    if len(drafts) >= _PROGRAM_MAKER_SLOT_COUNT:
        app.set_status(f"Draft limit reached ({_PROGRAM_MAKER_SLOT_COUNT}).")
        return
    name = _next_program_draft_name(app)
    drafts[name] = ""
    editor["current_draft"] = name
    _set_editor_buffer(app, "", mark_unsaved=False)
    _program_maker_sync_selection(app)
    _record_activity(app, f"Created draft '{name}'")
    app.set_status(f"Created draft: {name}")
    _open_program_editor(app)


def _program_delete_ui_state(app) -> dict:
    editor = _editor_store(app)
    state = editor.setdefault("delete_ui", {})
    if not isinstance(state, dict):
        state = {}
        editor["delete_ui"] = state
    names = _draft_names(app)
    selected_index = int(state.get("selected_index", 0) or 0)
    if names:
        selected_index = max(0, min(selected_index, len(names) - 1))
    else:
        selected_index = 0
    state["selected_index"] = selected_index
    return state


def _program_delete_sync_selection(app) -> None:
    names = _draft_names(app)
    state = _program_delete_ui_state(app)
    if not names:
        state["selected_index"] = 0
        return
    current = _current_editor_draft_name(app).strip()
    if current in names:
        state["selected_index"] = names.index(current)
    else:
        state["selected_index"] = max(0, min(int(state.get("selected_index", 0) or 0), len(names) - 1))


def _program_delete_style(app, text: str, *, selected: bool = False) -> str:
    value = str(text)
    if not selected:
        return value
    if getattr(app, "_ansi_enabled", False):
        return f"[7m{value}[0m"
    return f"> {value} <"


def _delete_program_draft_by_name(app, name: str) -> None:
    drafts = _editor_store(app).get("drafts", {})
    if name not in drafts:
        app.set_status("Draft not found.")
        return
    del drafts[name]
    editor = _editor_store(app)
    if editor.get("current_draft") == name:
        remaining = sorted(drafts.keys())
        if remaining:
            fallback = remaining[0]
            editor["current_draft"] = fallback
            editor["buffer"] = drafts.get(fallback, "")
        else:
            editor["current_draft"] = ""
            editor["buffer"] = ""
        editor["unsaved"] = False
    _program_delete_sync_selection(app)
    _record_activity(app, f"Deleted draft '{name}'")
    app.set_status(f"Deleted draft: {name}")


def render_program_delete_draft_panel(app):
    width = max(40, int(app._terminal_width()))
    names = _draft_names(app)
    state = _program_delete_ui_state(app)
    selected_index = int(state.get("selected_index", 0) or 0)

    action_line = "[New Draft]   [Delete Draft]   [Back]"
    print(app._align_line(action_line, max(20, width - 8), "center"))
    print("")
    print("  Select a draft and press Enter to delete it.")
    print("")

    if not names:
        print("  No drafts to delete.")
        return

    current_name = _current_editor_draft_name(app).strip()
    for idx, name in enumerate(names):
        marker = "*" if name == current_name else " "
        line = f"[{idx + 1}] {name}"
        if marker == "*":
            line += "  (open)"
        print("  " + _program_delete_style(app, line, selected=(idx == selected_index)))


def handle_program_delete_draft_key(app, key: str):
    names = _draft_names(app)
    state = _program_delete_ui_state(app)
    selected_index = int(state.get("selected_index", 0) or 0)

    if key == "ESC" or key in {"b", "B"}:
        app.go_back()
        return True

    if not names:
        return True

    if key == "UP":
        state["selected_index"] = (selected_index - 1) % len(names)
        return True
    if key == "DOWN":
        state["selected_index"] = (selected_index + 1) % len(names)
        return True
    if key in {"LEFT", "RIGHT"}:
        return True
    if key.isdigit():
        index = int(key) - 1
        if 0 <= index < len(names):
            state["selected_index"] = index
        return True
    if key == "ENTER":
        name = names[selected_index]
        app.open_confirm_dialog(
            title="Delete Draft",
            message=f"Are you sure you want to delete '{name}'?",
            on_yes=(lambda app, name=name: _delete_program_draft_by_name(app, name)),
            on_no=(lambda app: app.set_status("Delete canceled.")),
            yes_label="Yes",
            no_label="No",
        )
        return True
    return True


def enter_program_delete_draft(app, previous=None):
    _program_delete_sync_selection(app)


def program_delete_draft(app):
    drafts = _editor_store(app).get("drafts", {})
    if not drafts:
        app.set_status("No drafts to delete.")
        return
    app.set_screen("program_delete_draft")


def _program_slot_label(index: int):
    def label(app):
        names = _draft_names(app)
        if index < len(names):
            return f"Open: {_program_display_name(names[index])}"
        return "(empty slot)"
    return label


def _program_slot_action(index: int):
    def action(app):
        names = _draft_names(app)
        if index >= len(names):
            app.set_status("No draft in that slot.")
            return
        _load_draft_into_editor(app, names[index])
    return action


def _program_maker_selected_draft_name(app) -> str:
    names = _draft_names(app)
    if not names:
        return ""
    selected = int(getattr(app, "selected_index", 0) or 0)
    slot_offset = _PROGRAM_MAKER_ACTION_COUNT
    slot_count = _PROGRAM_MAKER_SLOT_COUNT
    if slot_offset <= selected < slot_offset + slot_count:
        slot_index = selected - slot_offset
        if 0 <= slot_index < len(_program_slot_display_order):
            actual_index = _program_slot_display_order[slot_index]
            if 0 <= actual_index < len(names):
                return names[actual_index]
    current = _current_editor_draft_name(app).strip()
    if current in names:
        return current
    return names[0]


def _rename_program_draft(app, old_name: str, new_name: str) -> None:
    editor = _editor_store(app)
    drafts = editor.setdefault("drafts", {})
    if old_name not in drafts:
        app.set_status("Draft not found.")
        return
    normalized = str(new_name or "").strip()
    if not normalized:
        app.set_status("Draft name cannot be empty.")
        return
    if normalized == old_name:
        app.set_status("Draft name unchanged.")
        return
    if len(normalized) > _PROGRAM_DRAFT_NAME_MAX:
        app.set_status(f"Draft names max {_PROGRAM_DRAFT_NAME_MAX} chars.")
        return
    if normalized in drafts:
        app.set_status("A draft with that name already exists.")
        return
    buffer = drafts.pop(old_name)
    drafts[normalized] = buffer
    if str(editor.get("current_draft") or "") == old_name:
        editor["current_draft"] = normalized
    if app.current_screen == "program_editor":
        app.screens["program_editor"]["main_title"] = normalized or "Program Editor"
    _record_activity(app, f"Renamed draft '{old_name}' to '{normalized}'")
    app.set_status(f"Renamed draft: {normalized}")


def program_rename_draft(app):
    target = _program_maker_selected_draft_name(app)
    if not target:
        app.set_status("No draft selected.")
        return
    new_name = app.prompt_text(
        f"Rename '{_program_display_name(target, limit=24)}' to",
        title="RENAME DRAFT",
        allow_empty=False,
        initial=target[:_PROGRAM_DRAFT_NAME_MAX],
        max_length=_PROGRAM_DRAFT_NAME_MAX,
    )
    if new_name is None:
        app.set_status("Rename canceled.")
        return
    _rename_program_draft(app, target, new_name)


PROGRAM_EDITOR_WIDTH = 62
PROGRAM_EDITOR_HEIGHT = 12


def _program_editor_size(app) -> tuple[int, int]:
    return _fullscreen_editor_size(
        app,
        "program_editor",
        "program_editor_width",
        "program_editor_height",
        "program_editor_width",
        "program_editor_height",
        PROGRAM_EDITOR_WIDTH,
        PROGRAM_EDITOR_HEIGHT,
        min_height=6,
    )


def _program_editor_lines(app) -> list[str]:
    text = str(_editor_store(app).get("buffer", "") or "")
    lines = text.split("\n")
    return lines if lines else [""]


def _program_editor_position(app) -> tuple[int, int]:
    editor = _editor_store(app)
    lines = _program_editor_lines(app)
    row = int(editor.get("cursor_row", len(lines) - 1) or 0)
    row = max(0, min(row, len(lines) - 1))
    col_default = len(lines[row])
    col = int(editor.get("cursor_col", col_default) or 0)
    col = max(0, min(col, len(lines[row])))
    return row, col


def _program_set_editor_state(app, lines: list[str], row: int | None = None, col: int | None = None, *, mark_unsaved: bool = True) -> None:
    editor = _editor_store(app)
    clean_lines = [str(line) for line in (lines or [""])]
    if not clean_lines:
        clean_lines = [""]
    row = len(clean_lines) - 1 if row is None else max(0, min(int(row), len(clean_lines) - 1))
    col_default = len(clean_lines[row])
    col = col_default if col is None else max(0, min(int(col), len(clean_lines[row])))
    editor["buffer"] = "\n".join(clean_lines)
    editor["cursor_row"] = row
    editor["cursor_col"] = col
    editor["goal_col"] = col
    editor["unsaved"] = mark_unsaved


def _program_editor_window(app, width: int, height: int) -> tuple[list[str], int, int, int, int]:
    width = max(8, int(width))
    height = max(4, int(height))
    lines = _program_editor_lines(app)
    row, col = _program_editor_position(app)

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
        visible.append("")
    return visible, vstart, hstart, row, col


def _program_editor_gutter_width(app, visible_height: int) -> int:
    total_lines = len(_program_editor_lines(app))
    visible_height = max(1, int(visible_height))
    digits = max(2, len(str(max(total_lines, visible_height))))
    return digits


def _program_editor_canvas_lines(app, width: int, height: int) -> tuple[list[str], int]:
    visible, vstart, hstart, row, col = _program_editor_window(app, width, height)
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
    return out, vstart


def _program_editor_text_width(app) -> int:
    total_width, height = _program_editor_size(app)
    gutter_width = _program_editor_gutter_width(app, height)
    return max(8, total_width - gutter_width - 3)


def render_program_editor_panel(app):
    total_width, height = _program_editor_size(app)
    gutter_width = _program_editor_gutter_width(app, height)
    text_width = max(8, total_width - gutter_width - 3)
    lines, vstart = _program_editor_canvas_lines(app, text_width, height)
    for idx, line in enumerate(lines, start=vstart + 1):
        gutter = str(idx).rjust(gutter_width)
        print(f"  {gutter} │ {line}")


def handle_program_editor_key(app, key: str):
    lines = _program_editor_lines(app)
    row, col = _program_editor_position(app)
    goal_col = int(_editor_store(app).get("goal_col", col) or 0)
    mutated = False

    if key == "ESC":
        try:
            _save_current_draft(app)
            app.set_status(f"Saved draft: {_current_editor_draft_name(app)}")
        except ValueError as exc:
            app.set_status(str(exc))
        app.go_back()
        return True

    if key == "BACKSPACE":
        if col > 0:
            line = lines[row]
            lines[row] = line[:col - 1] + line[col:]
            col -= 1
            mutated = True
        elif row > 0:
            prev_len = len(lines[row - 1])
            lines[row - 1] += lines[row]
            del lines[row]
            row -= 1
            col = prev_len
            mutated = True
        goal_col = col
    elif key == "LEFT":
        if col > 0:
            col -= 1
        elif row > 0:
            row -= 1
            col = len(lines[row])
        goal_col = col
    elif key == "RIGHT":
        if col < len(lines[row]):
            col += 1
        elif row < len(lines) - 1:
            row += 1
            col = 0
        goal_col = col
    elif key == "UP":
        if row > 0:
            row -= 1
            col = min(goal_col, len(lines[row]))
    elif key == "DOWN":
        if row < len(lines) - 1:
            row += 1
            col = min(goal_col, len(lines[row]))
    elif key == "ENTER":
        line = lines[row]
        lines[row] = line[:col]
        lines.insert(row + 1, line[col:])
        row += 1
        col = 0
        goal_col = col
        mutated = True
    elif isinstance(key, str) and len(key) == 1 and key.isprintable():
        line = lines[row]
        lines[row] = line[:col] + key + line[col:]
        col += 1
        goal_col = col
        mutated = True
        wrap_width = _program_editor_text_width(app)
        lines, row, col = app._multiline_hard_wrap(
            lines,
            row,
            col,
            wrap_width,
            cursor_wrap_at_boundary=True,
        )
        goal_col = col
        _editor_store(app)["goal_col"] = goal_col
        _program_set_editor_state(app, lines, row, col, mark_unsaved=True)
        return True
    else:
        return True

    if mutated:
        wrap_width = _program_editor_text_width(app)
        lines, row, col = app._multiline_hard_wrap(lines, row, col, wrap_width)
        goal_col = col

    _editor_store(app)["goal_col"] = goal_col
    _program_set_editor_state(app, lines, row, col, mark_unsaved=True)
    return True


def render_program_editor(app):
    render_program_editor_panel(app)


def program_replace_text(app):
    raw = app.prompt_text("Replace program text with", title="PROGRAM EDITOR")
    if raw is None:
        app.set_status("Input canceled.")
        return
    _set_editor_buffer(app, raw, mark_unsaved=True)
    _record_activity(app, "Replaced program text")
    app.set_status("Program text replaced.")


def program_add_line(app):
    raw = app.prompt_text("Add line", title="PROGRAM EDITOR", allow_empty=False)
    if raw is None:
        app.set_status("Input canceled.")
        return
    editor = _editor_store(app)
    current = editor.get("buffer", "")
    if current:
        current += "\n"
    current += raw
    editor["buffer"] = current
    editor["unsaved"] = True
    _record_activity(app, "Added a line to the program")
    app.set_status("Line added.")


def program_save_draft(app):
    try:
        _save_current_draft(app)
        app.set_status(f"Saved draft: {_current_editor_draft_name(app)}")
    except ValueError as exc:
        app.set_status(str(exc))


def program_save_as_new_draft(app):
    editor = _editor_store(app)
    drafts = editor.setdefault("drafts", {})
    name = _next_program_draft_name(app)
    drafts[name] = editor.get("buffer", "")
    editor["current_draft"] = name
    editor["unsaved"] = False
    _record_activity(app, f"Saved as draft '{name}'")
    app.set_status(f"Saved as draft: {name}")


def program_load_quick_notes(app):
    notes = _notes_store(app).get("notes", [])
    if not notes:
        app.set_status("No quick notes available.")
        return
    _set_editor_buffer(app, "\n".join(notes), mark_unsaved=True)
    _record_activity(app, "Loaded quick notes into the program editor")
    app.set_status("Loaded quick notes into the editor.")


_program_slot_display_order = _program_maker_display_order()
_program_slot_labels = [_program_slot_label(i) for i in _program_slot_display_order]
_program_slot_actions = [_program_slot_action(i) for i in _program_slot_display_order]


def register_program_maker_screens(app) -> None:
    app.add_screen(
        name="program_maker",
        title="Program Maker",
        options=[
            "New Draft",
            "Delete Draft",
            *_program_slot_labels,
            "Back",
        ],
        actions=[
            program_new_draft,
            program_delete_draft,
            *_program_slot_actions,
            "back",
        ],
        on_render=render_program_maker,
        on_enter=enter_program_maker,
        hotkeys={
            "n": program_new_draft,
            "d": program_delete_draft,
            "r": program_rename_draft,
            "b": "back",
        },
    )
    app.screens["program_maker"]["main_columns"] = 2
    app.screens["program_maker"]["menu_row_gap"] = 0
    app.screens["program_maker"]["menu_box_gap"] = 4
    app.screens["program_maker"]["menu_center_seam"] = True
    app.screens["program_maker"]["footer_text"] = "[Arrows] Move  [Enter] Open  [N] New  [D] Delete  [R] Rename  [Esc] Back"

    app.add_screen(
        name="program_delete_draft",
        title="Program Maker",
        options=[],
        actions=[],
        on_enter=enter_program_delete_draft,
        main_panel=render_program_delete_draft_panel,
        main_title="Delete Draft",
        screen_type="workspace_full",
    )
    app.screens["program_delete_draft"]["interaction_mode"] = "typing"
    app.screens["program_delete_draft"]["hide_menu"] = True
    app.screens["program_delete_draft"]["on_key"] = handle_program_delete_draft_key
    app.screens["program_delete_draft"]["footer_text"] = "[Up/Down] Select Draft  [Enter] Delete  [Esc] Back"

    app.add_screen(
        name="program_editor",
        title="Program Editor",
        options=[],
        actions=[],
        main_panel=render_program_editor_panel,
        main_title="Program Editor",
        screen_type="workspace_full",
    )
    app.screens["program_editor"]["interaction_mode"] = "typing"
    app.screens["program_editor"]["hide_menu"] = True
    app.screens["program_editor"]["on_key"] = handle_program_editor_key
    app.screens["program_editor"]["footer_text"] = "[Arrows] Move  [Enter] New Line  [Backspace] Delete  [Esc] Save + Back"
    app.screens["program_editor"]["program_editor_width_fill"] = True
    app.screens["program_editor"]["program_editor_height_fill"] = True
