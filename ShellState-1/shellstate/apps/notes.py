"""Quick Notes screens and behavior."""

from shellstate.core.engine import A
from shellstate.core.runtime_model import (
    _notes_store,
    _record_activity,
    _system_settings,
)

NOTES_MAIN_WIDTH = 46
NOTES_MAIN_HEIGHT = 8
NOTES_EDITOR_WIDTH = 58
NOTES_EDITOR_HEIGHT = 12


def _notes_terminal_size(app) -> tuple[int, int]:
    width = 80
    height = 24
    try:
        width = int(app._terminal_width())
    except Exception:
        pass
    try:
        height = int(app._terminal_height())
    except Exception:
        pass
    return max(40, width), max(18, height)


def _notes_main_canvas_size(app) -> tuple[int, int]:
    term_w, term_h = _notes_terminal_size(app)
    width = min(NOTES_MAIN_WIDTH, max(20, term_w - 14))
    height = min(NOTES_MAIN_HEIGHT, max(4, term_h - 18))
    return width, height


def _fullscreen_editor_size(app, screen_name: str, width_attr: str, height_attr: str, width_key: str, height_key: str, default_width: int, default_height: int, *, min_height: int = 6) -> tuple[int, int]:
    screen = app.screens.get(screen_name, {})
    w_default = int(screen.get(width_key, default_width) or default_width)
    h_default = int(screen.get(height_key, default_height) or default_height)
    width = int(getattr(app, width_attr, w_default) or w_default)
    height = int(getattr(app, height_attr, h_default) or h_default)
    term_w, term_h = _notes_terminal_size(app)
    fill_width = bool(screen.get(f"{width_key}_fill", True))
    fill_height = bool(screen.get(f"{height_key}_fill", True))
    # Match wrapping to the visible canvas width inside the full-screen panel.
    max_width = max(20, term_w - 8)
    max_height = max(min_height, term_h - 16)
    final_width = max_width if fill_width else min(width, max_width)
    final_height = max_height if fill_height else min(height, max_height)
    return max(20, final_width), max(min_height, final_height)


def _notes_editor_size(app) -> tuple[int, int]:
    return _fullscreen_editor_size(
        app,
        "notes_draft",
        "notes_editor_width",
        "notes_editor_height",
        "notes_editor_width",
        "notes_editor_height",
        NOTES_EDITOR_WIDTH,
        NOTES_EDITOR_HEIGHT,
        min_height=4,
    )


def _notes_draft_buffer(app) -> str:
    return str(_notes_store(app).get("draft_buffer", "") or "")


def _notes_draft_lines(app) -> list[str]:
    text = _notes_draft_buffer(app)
    lines = text.split("\n")
    return lines if lines else [""]


def _notes_draft_position(app) -> tuple[int, int]:
    store = _notes_store(app)
    lines = _notes_draft_lines(app)
    row = int(store.get("draft_cursor_row", len(lines) - 1) or 0)
    row = max(0, min(row, len(lines) - 1))
    col_default = len(lines[row])
    col = int(store.get("draft_cursor_col", col_default) or 0)
    col = max(0, min(col, len(lines[row])))
    return row, col


def _notes_set_draft_state(app, lines: list[str], row: int | None = None, col: int | None = None) -> None:
    store = _notes_store(app)
    clean_lines = [str(line) for line in (lines or [""])]
    if not clean_lines:
        clean_lines = [""]
    row = len(clean_lines) - 1 if row is None else max(0, min(int(row), len(clean_lines) - 1))
    col_default = len(clean_lines[row])
    col = col_default if col is None else max(0, min(int(col), len(clean_lines[row])))
    store["draft_buffer"] = "\n".join(clean_lines)
    store["draft_cursor_row"] = row
    store["draft_cursor_col"] = col


def _notes_draft_char_count(app) -> int:
    return len(_notes_draft_buffer(app))


def _notes_draft_word_count(app) -> int:
    return len([token for token in _notes_draft_buffer(app).split() if token])


def _notes_canvas_window(app, width: int, height: int) -> tuple[list[str], int, int, int, int]:
    width = max(8, int(width))
    height = max(4, int(height))
    lines = _notes_draft_lines(app)
    row, col = _notes_draft_position(app)

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


def _notes_cursor_cell(app, ch: str, *, insert_mode: bool = False) -> str:
    if app._ansi_enabled:
        if insert_mode:
            return "[7m▏[0m"
        target = ch if ch and ch != " " else " "
        return "[7m" + target + "[0m"
    return "|" if insert_mode else "_"


def _notes_render_canvas_row(app, line: str, target_col: int, width: int, *, insert_mode: bool = False) -> str:
    padded = str(line).ljust(width)[:width]
    if target_col < 0 or target_col > width:
        return padded
    if insert_mode:
        if width <= 0:
            return ""
        if target_col >= width:
            target_col = width - 1
        return padded[:target_col] + _notes_cursor_cell(app, "", insert_mode=True) + padded[target_col + 1:]
    if target_col >= width:
        return padded
    return padded[:target_col] + _notes_cursor_cell(app, padded[target_col], insert_mode=False) + padded[target_col + 1:]


def _notes_canvas_lines(app, width: int = 48, height: int = 8, *, boxed: bool = True, insert_cursor: bool = False) -> list[str]:
    width = max(20, int(width))
    height = max(4, int(height))
    visible, vstart, hstart, row, col = _notes_canvas_window(app, width, height)
    target_index = row - vstart
    target_col = col - hstart
    out: list[str] = []
    for idx, line in enumerate(visible):
        rendered = _notes_render_canvas_row(
            app,
            line,
            target_col if idx == target_index and 0 <= target_index < height else -1,
            width,
            insert_mode=insert_cursor,
        )
        if boxed:
            out.append(f"│ {rendered} │")
        else:
            out.append(rendered)
    if not boxed:
        return out
    top = "┌" + ("─" * (width + 2)) + "┐"
    bottom = "└" + ("─" * (width + 2)) + "┘"
    return [top, *out, bottom]


def _notes_preview_text(note: str, limit: int) -> str:
    single = " / ".join(part.strip() for part in str(note).splitlines() if part.strip())
    single = single or "(blank)"
    return single[:limit] + ("…" if len(single) > limit else "")


def _notes_ui_state(app) -> dict:
    notes_store = _notes_store(app)
    state = notes_store.setdefault("ui", {})
    if not isinstance(state, dict):
        state = {}
        notes_store["ui"] = state
    return state


def _notes_open_index(app):
    notes = _notes_store(app).get("notes", [])
    state = _notes_ui_state(app)
    raw = state.get("open_note_index")
    try:
        index = int(raw)
    except (TypeError, ValueError):
        index = None
    if index is None or not (0 <= index < len(notes)):
        if "open_note_index" in state:
            state.pop("open_note_index", None)
        return None
    return index


def _notes_set_open_index(app, index):
    state = _notes_ui_state(app)
    if index is None:
        state.pop("open_note_index", None)
        return
    state["open_note_index"] = int(index)


def _notes_edit_index(app):
    notes = _notes_store(app).get("notes", [])
    state = _notes_ui_state(app)
    raw = state.get("editing_note_index")
    try:
        index = int(raw)
    except (TypeError, ValueError):
        index = None
    if index is None or not (0 <= index < len(notes)):
        if "editing_note_index" in state:
            state.pop("editing_note_index", None)
        return None
    return index


def _notes_set_edit_index(app, index):
    state = _notes_ui_state(app)
    if index is None:
        state.pop("editing_note_index", None)
        return
    state["editing_note_index"] = int(index)


def _notes_info_inner_width(app) -> int:
    screen = app.screens.get("notes") or {}
    term_w, _ = _notes_terminal_size(app)
    total_width = max(28, term_w - 2)
    info_width = screen.get("info_panel_width")
    try:
        info_width = int(info_width) if info_width is not None else None
    except Exception:
        info_width = None
    if info_width is None:
        gap = max(2, int(screen.get("panel_gap", 4) or 4))
        ratio = 0.34
        info_width = int((total_width - gap) * ratio)
    return max(12, int(info_width) - 6)


def render_notes_list_panel(app):
    notes = _notes_store(app).get("notes", [])
    preview_len = max(8, int(_system_settings(app).get("notes_preview_len", 64)))
    if not notes:
        _notes_set_open_index(app, None)
        _notes_set_edit_index(app, None)
        print("  No notes saved yet.")
        print("")
        print("  Open the draft canvas")
        print("  to type a quick note.")
        return

    open_index = _notes_open_index(app)
    edit_index = _notes_edit_index(app)
    print(f"  {len(notes)} note(s):")
    for i, note in enumerate(notes[-12:], max(1, len(notes) - min(len(notes), 12) + 1)):
        preview = _notes_preview_text(note, preview_len)
        marker = ">" if open_index == i - 1 else " "
        suffix = " [editing]" if edit_index == i - 1 else ""
        print(f"  {marker} {i:>2}. {preview}{suffix}")

    print("")
    print("  Open Saved Note loads a")
    print("  saved note into the draft")
    print("  editor screen.")


def render_notes_main_panel(app):
    draft = _notes_draft_buffer(app)
    notes = _notes_store(app).get("notes", [])
    canvas_width, canvas_height = _notes_main_canvas_size(app)
    print("  Draft canvas")
    print("")
    for line in _notes_canvas_lines(app, width=canvas_width, height=canvas_height):
        print(f"  {line}")
    print("")
    print(f"  Draft chars: {len(draft)}")
    print(f"  Draft lines: {len(_notes_draft_lines(app))}")
    print(f"  Saved notes: {len(notes)}")
    print("")
    print("  Edit Draft opens the live")
    print("  multiline canvas editor.")


def render_notes_editor_panel(app):
    draft = _notes_draft_buffer(app)
    row, col = _notes_draft_position(app)
    editor_width, editor_height = _notes_editor_size(app)
    word_count = _notes_draft_word_count(app)
    print(f"  Draft chars: {len(draft)}  |  words: {word_count}  |  line {row + 1}, col {col + 1}")
    print("  Typing mode active — Enter=new line, Esc=save + back.")
    print("")
    for line in _notes_canvas_lines(app, width=editor_width, height=editor_height, boxed=False, insert_cursor=True):
        print(f"  {line}")


def save_notes_draft(app):
    value = _notes_draft_buffer(app).strip()
    if not value:
        app.set_status("Draft is empty.")
        return
    notes = _notes_store(app).setdefault("notes", [])
    edit_index = _notes_edit_index(app)
    if edit_index is not None and 0 <= edit_index < len(notes):
        notes[edit_index] = _notes_draft_buffer(app).rstrip()
        _notes_set_open_index(app, edit_index)
        _record_activity(app, f"Updated note {edit_index + 1} from the draft canvas")
        app.set_status(f"Note {edit_index + 1} updated.")
    else:
        notes.append(_notes_draft_buffer(app).rstrip())
        _notes_set_open_index(app, len(notes) - 1)
        _record_activity(app, "Saved a note from the draft canvas")
        app.set_status(f"Note {len(notes)} saved.")
    _notes_set_edit_index(app, None)
    _notes_set_draft_state(app, [""], 0, 0)


def clear_notes_draft(app):
    _notes_set_edit_index(app, None)
    _notes_set_draft_state(app, [""], 0, 0)
    app.set_status("Draft cleared.")


def save_notes_draft_and_back(app):
    value = _notes_draft_buffer(app).strip()
    notes = _notes_store(app).setdefault("notes", [])
    edit_index = _notes_edit_index(app)
    if value:
        if edit_index is not None and 0 <= edit_index < len(notes):
            notes[edit_index] = _notes_draft_buffer(app).rstrip()
            _notes_set_open_index(app, edit_index)
            _record_activity(app, f"Updated note {edit_index + 1} from the draft canvas")
            app.set_status(f"Note {edit_index + 1} updated.")
        else:
            notes.append(_notes_draft_buffer(app).rstrip())
            _notes_set_open_index(app, len(notes) - 1)
            _record_activity(app, "Saved a note from the draft canvas")
            app.set_status(f"Note {len(notes)} saved.")
    else:
        if edit_index is not None and 0 <= edit_index < len(notes):
            app.set_status(f"Note {edit_index + 1} unchanged.")
        else:
            app.set_status("Empty draft discarded.")
    _notes_set_edit_index(app, None)
    _notes_set_draft_state(app, [""], 0, 0)
    app.go_back()


def handle_notes_editor_key(app, key: str):
    lines = _notes_draft_lines(app)
    row, col = _notes_draft_position(app)
    goal_col = int(_notes_store(app).get("draft_goal_col", col) or 0)
    mutated = False

    if key == "ESC":
        save_notes_draft_and_back(app)
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
        wrap_width, _ = _notes_editor_size(app)
        lines, row, col = app._multiline_hard_wrap(
            lines,
            row,
            col,
            wrap_width,
            cursor_wrap_at_boundary=True,
        )
        goal_col = col
        _notes_store(app)["draft_goal_col"] = goal_col
        _notes_set_draft_state(app, lines, row, col)
        return True
    else:
        return True

    if mutated:
        wrap_width, _ = _notes_editor_size(app)
        lines, row, col = app._multiline_hard_wrap(lines, row, col, wrap_width)
        goal_col = col

    _notes_store(app)["draft_goal_col"] = goal_col
    _notes_set_draft_state(app, lines, row, col)
    return True


def open_notes_canvas_editor(app):
    _notes_set_edit_index(app, None)
    width, height = _notes_editor_size(app)
    app.notes_editor_width = width
    app.notes_editor_height = height
    row, col = _notes_draft_position(app)
    wrapped_lines, row, col = app._multiline_hard_wrap(_notes_draft_lines(app), row, col, width)
    _notes_store(app)["draft_goal_col"] = col
    _notes_set_draft_state(app, wrapped_lines, row, col)
    app.set_screen("notes_draft")
    app._needs_render = True


def open_saved_note(app):
    notes = _notes_store(app).get("notes", [])
    if not notes:
        app.set_status("No saved notes to open.")
        return
    initial = ""
    current = _notes_open_index(app)
    if current is not None:
        initial = str(current + 1)
    raw = app.prompt_text(
        f"Open note number (1-{len(notes)})",
        title="OPEN NOTE",
        initial=initial,
        allow_empty=False,
    )
    if raw is None:
        app.set_status("Input canceled.")
        return
    try:
        picked = int(str(raw).strip())
    except ValueError:
        app.set_status("Enter a note number.")
        return
    if not (1 <= picked <= len(notes)):
        app.set_status("Invalid note number.")
        return
    index = picked - 1
    _notes_set_open_index(app, index)
    _notes_set_edit_index(app, index)
    source_text = str(notes[index])
    source_lines = source_text.splitlines() or [""]
    row = len(source_lines) - 1
    col = len(source_lines[row])
    width, height = _notes_editor_size(app)
    app.notes_editor_width = width
    app.notes_editor_height = height
    wrapped_lines, row, col = app._multiline_hard_wrap(source_lines, row, col, width)
    _notes_store(app)["draft_goal_col"] = col
    _notes_set_draft_state(app, wrapped_lines, row, col)
    _record_activity(app, f"Opened note {picked} in the draft editor")
    app.set_status(f"Editing note {picked}.")
    app.set_screen("notes_draft")
    app._needs_render = True


def delete_note_by_number(app):
    notes = _notes_store(app).get("notes", [])
    if not notes:
        app.set_status("No notes to delete.")
        return
    raw = app.prompt_text(f"Delete note number (1-{len(notes)})", title="DELETE NOTE", allow_empty=False)
    if raw is None:
        app.set_status("Input canceled.")
        return
    try:
        picked = int(str(raw).strip())
    except ValueError:
        app.set_status("Enter a note number.")
        return
    if not (1 <= picked <= len(notes)):
        app.set_status("Invalid note number.")
        return
    removed = notes.pop(picked - 1)
    open_index = _notes_open_index(app)
    if open_index is not None:
        if open_index == picked - 1:
            _notes_set_open_index(app, None)
        elif open_index > picked - 1:
            _notes_set_open_index(app, open_index - 1)
    edit_index = _notes_edit_index(app)
    if edit_index is not None:
        if edit_index == picked - 1:
            _notes_set_edit_index(app, None)
        elif edit_index > picked - 1:
            _notes_set_edit_index(app, edit_index - 1)
    preview = _notes_preview_text(removed, 48)
    _record_activity(app, f"Deleted note {picked}")
    app.set_status(f'Note {picked} deleted: "{preview}"')



def clear_all_notes(app):
    _notes_store(app)["notes"] = []
    _notes_set_open_index(app, None)
    _notes_set_edit_index(app, None)
    _record_activity(app, "Cleared all notes")
    app.set_status("All notes cleared.")


def label_edit_draft(app):
    chars = _notes_draft_char_count(app)
    suffix = f"({chars} chars)" if chars else "(empty)"
    return f"Edit Draft Canvas  {suffix}"


def configure_notes_screen(app, *_args) -> None:
    screen = app.screens.get("notes")
    if not screen:
        return
    term_w, _ = _notes_terminal_size(app)
    total_width = max(28, term_w - 2)
    gap = max(2, int(screen.get("panel_gap", 4) or 4))
    info_width = int((total_width - gap) * 0.34)
    screen["panel_mode"] = "auto"
    screen["info_panel_width"] = max(22, min(info_width, max(22, total_width - 10)))


def notes_draft_footer(app):
    width, _ = _notes_terminal_size(app)
    if width < 56:
        return "[Typing] Arrows move  Enter line  Esc save"
    return "[Typing Mode]  [Arrows] Move  [Enter] New Line  [Backspace] Delete  [Esc] Save + Back"


def register_notes_screens(app) -> None:
    app.add_screen(
        name="notes",
        title="Quick Notes",
        options=[
            label_edit_draft,
            "Open Saved Note",
            "Delete Note by Number",
            "Clear All Notes",
            "Back",
        ],
        actions=[
            open_notes_canvas_editor,
            open_saved_note,
            delete_note_by_number,
            A.confirm(
                title="Clear All Notes",
                message="Delete ALL notes? This cannot be undone.",
                on_yes=clear_all_notes,
                on_no=A.status("Canceled."),
            ),
            "back",
        ],
        info_panel=render_notes_list_panel,
        info_title="Saved Notes",
        screen_type="workspace_split",
        on_enter=configure_notes_screen,
        hotkeys={"a": open_notes_canvas_editor, "o": open_saved_note, "b": "back"},
    )

    app.add_screen(
        name="notes_draft",
        title="Note Draft",
        options=[],
        actions=[],
        main_panel=render_notes_editor_panel,
        main_title="Canvas Editor",
        screen_type="workspace_full",
    )
    app.screens["notes_draft"]["interaction_mode"] = "typing"
    app.screens["notes_draft"]["hide_menu"] = True
    app.screens["notes_draft"]["on_key"] = handle_notes_editor_key
    app.screens["notes_draft"]["notes_editor_width"] = NOTES_EDITOR_WIDTH
    app.screens["notes_draft"]["notes_editor_height"] = NOTES_EDITOR_HEIGHT
    app.screens["notes_draft"]["notes_editor_width_fill"] = True
    app.screens["notes_draft"]["notes_editor_height_fill"] = True
    app.screens["notes_draft"]["footer_text"] = notes_draft_footer
