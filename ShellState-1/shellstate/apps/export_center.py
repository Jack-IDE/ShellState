"""Export Center screens and save/load behavior."""

from shellstate.runtime_model import *

def _notes_text_dump(app) -> str:
    notes = _notes_store(app).get("notes", [])
    if not notes:
        return "No notes saved.\n"
    chunks = []
    for i, note in enumerate(notes, 1):
        chunks.append(f"[Note {i}]\n{note}")
    return "\n\n".join(chunks) + "\n"


def _calculator_text_dump(app) -> str:
    history = _calculator_store(app).get("history", [])
    if not history:
        return "No calculator history.\n"
    return "\n".join(history) + "\n"


def _converter_text_dump(app) -> str:
    converter = _converter_store(app)
    recent = converter.get("recent", [])
    lines = [f"Last result: {converter.get('last_result', '') or '(none)'}", ""]
    if recent:
        lines.append("Recent conversions:")
        lines.extend(f"  {entry}" for entry in recent)
    else:
        lines.append("No recent conversions.")
    return "\n".join(lines) + "\n"


def _editor_text_dump(app) -> str:
    editor = _editor_store(app)
    drafts = editor.get("drafts", {})
    if not drafts:
        return "No drafts saved.\n"
    chunks = []
    for name in sorted(drafts.keys()):
        chunks.append(f"[Draft: {name}]\n{drafts[name]}")
    return "\n\n".join(chunks) + "\n"


def export_notes_txt(app):
    filename = f"notes_export_{_timestamp_slug()}.txt"
    _write_text_export(app, filename, _notes_text_dump(app))


def export_calculator_txt(app):
    filename = f"calculator_history_{_timestamp_slug()}.txt"
    _write_text_export(app, filename, _calculator_text_dump(app))


def export_converter_txt(app):
    filename = f"converter_export_{_timestamp_slug()}.txt"
    _write_text_export(app, filename, _converter_text_dump(app))


def export_editor_txt(app):
    filename = f"editor_drafts_{_timestamp_slug()}.txt"
    _write_text_export(app, filename, _editor_text_dump(app))


def export_app_data_json(app):
    payload = {
        "format": "shellstate-app-data",
        "version": 2,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "apps": app.app_data.get("apps", {}),
    }
    filename = f"shellstate_app_data_{_timestamp_slug()}.json"
    _write_json_export(app, filename, payload)


def export_full_backup_json(app):
    filename = f"shellstate_full_backup_{_timestamp_slug()}.json"
    _write_json_export(app, filename, _build_full_backup_payload(app))


def clear_recent_activity(app):
    _system_store(app)["recent_activity"] = []
    app.set_status("Recent activity cleared.")


def save_main_state_now(app):
    app.save_data()
    if str(app.status_msg).startswith("Save Error"):
        return
    rel = os.path.relpath(DATA_FILE, PROJECT_ROOT)
    _record_activity(app, f"Saved main state to {rel}")
    app.set_status(f"Saved main state to {rel}")


def _loadable_save_entries() -> list[dict]:
    entries: list[dict] = []
    if os.path.exists(DATA_FILE):
        try:
            stat = os.stat(DATA_FILE)
        except OSError:
            stat = None
        entries.append({
            "kind": "main",
            "label": "Current Main Save",
            "filename": os.path.basename(DATA_FILE),
            "path": DATA_FILE,
            "relpath": os.path.relpath(DATA_FILE, PROJECT_ROOT),
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %I:%M %p") if stat else "unknown",
            "size": int(stat.st_size) if stat else 0,
            "sort_key": stat.st_mtime if stat else 0.0,
            "payload": None,
        })

    export_entries: list[dict] = []
    if os.path.isdir(EXPORTS_DIR):
        for filename in os.listdir(EXPORTS_DIR):
            if not filename.lower().endswith('.json'):
                continue
            path = os.path.join(EXPORTS_DIR, filename)
            try:
                with open(path, 'r', encoding='utf-8') as handle:
                    payload = json.load(handle)
                if not isinstance(payload, dict):
                    continue
                fmt = str(payload.get('format') or '')
                if fmt not in {'shellstate-demo-backup', 'shellstate-app-data'}:
                    continue
                stat = os.stat(path)
            except Exception:
                continue
            export_entries.append({
                "kind": "full" if fmt == 'shellstate-demo-backup' else "apps",
                "label": filename,
                "filename": filename,
                "path": path,
                "relpath": os.path.relpath(path, PROJECT_ROOT),
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %I:%M %p"),
                "size": int(stat.st_size),
                "sort_key": stat.st_mtime,
                "payload": payload,
            })
    export_entries.sort(key=lambda item: item.get("sort_key", 0.0), reverse=True)
    entries.extend(export_entries)
    return entries


def _refresh_load_saves_screen(app) -> None:
    screen = app.screens.get("load_saves")
    if not screen:
        return
    entries = _loadable_save_entries()
    screen["_load_entries"] = entries
    if not entries:
        screen["options"] = []
        screen["actions"] = []
        return
    screen["options"] = [entry["label"] for entry in entries]
    screen["actions"] = [_make_load_save_action(entry) for entry in entries]


def _load_save_kind_label(entry: dict) -> str:
    kind = str(entry.get("kind") or "")
    if kind == "main":
        return "Main Save"
    if kind == "full":
        return "Full Backup"
    if kind == "apps":
        return "App Data Export"
    return "JSON Save"


def _load_save_counts(payload: dict) -> tuple[int, int]:
    apps_payload = payload.get('apps', {}) if isinstance(payload.get('apps'), dict) else {}
    notes_payload = apps_payload.get('notes', {}) if isinstance(apps_payload.get('notes'), dict) else {}
    editor_payload = apps_payload.get('editor', {}) if isinstance(apps_payload.get('editor'), dict) else {}
    notes_count = len(notes_payload.get('notes', [])) if isinstance(notes_payload.get('notes', []), list) else 0
    drafts_count = len(editor_payload.get('drafts', {})) if isinstance(editor_payload.get('drafts', {}), dict) else 0
    return notes_count, drafts_count


def render_saves_panel(app):
    rel_data = os.path.relpath(DATA_FILE, PROJECT_ROOT)
    rel_exports = os.path.relpath(EXPORTS_DIR, PROJECT_ROOT)
    rel_snapshots = os.path.relpath(SNAPSHOTS_DIR, PROJECT_ROOT)
    recent_exports = _recent_exports(app)
    recent_line = "No exports yet."
    if recent_exports:
        preview = " | ".join(os.path.basename(name) for name in recent_exports[:2])
        recent_line = preview
    lines = [
        f"Main save: {rel_data}",
        f"Exports: {rel_exports}/",
        f"Snapshots: {rel_snapshots}/",
        "",
        "Save writes the live shell state to the main JSON.",
        "Load opens a saved JSON and lets you replace live state.",
        "Export writes TXT or JSON copies you can keep or share.",
        f"Recent: {recent_line}",
    ]
    for line in lines:
        print(line)


def render_load_saves_panel(app):
    screen = app.screens.get("load_saves", {})
    entries = list(screen.get("_load_entries", []))
    if not entries:
        for line in [
            "No loadable JSON saves found.",
            "",
            "Create one from Export Center:",
            "- Export Full Backup as JSON",
            "- Export App Data as JSON",
        ]:
            print(line)
        return

    selected = max(0, min(app.selected_index, len(entries) - 1))
    entry = entries[selected]
    payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else None
    lines = [
        f"Type: {_load_save_kind_label(entry)}",
        f"File: {entry.get('filename', '')}",
        f"Path: {entry.get('relpath', '')}",
        f"Modified: {entry.get('modified', 'unknown')}",
        f"Size: {int(entry.get('size', 0))} bytes",
        "",
    ]
    if payload is None:
        lines.extend([
            "Reloads the current main save file.",
            "Use this if you want to pull state back from disk.",
        ])
    else:
        exported_at = str(payload.get('exported_at') or 'unknown')
        notes_count, drafts_count = _load_save_counts(payload)
        lines.extend([
            f"Exported: {exported_at}",
            f"Notes: {notes_count}   Drafts: {drafts_count}",
            "",
            "Loading will replace the current live state.",
            "A safety backup is written first.",
        ])
    for line in lines:
        print(line)


def _finish_loaded_state(app, status_message: str, activity_message: str) -> None:
    from shellstate.apps.shell_ui import _finalize_shell_ui

    _init_defaults(app)
    _finalize_shell_ui(app)
    _refresh_load_saves_screen(app)
    _record_activity(app, activity_message)
    app.set_screen("saves", push_history=False)
    app.set_status(status_message)


def _load_save_entry(app, entry: dict) -> None:
    kind = str(entry.get("kind") or "")
    try:
        if kind == "main":
            app.load_data()
            if str(app.status_msg).startswith("Data reset:"):
                return
            _finish_loaded_state(
                app,
                f"Reloaded main save from {entry.get('relpath', '')}",
                f"Reloaded main save from {entry.get('relpath', '')}",
            )
            return

        source_name, payload = _load_import_payload(str(entry.get("filename") or ""))
        backup_name = _make_auto_backup_file(app)
        _apply_payload_import(app, payload, source_name, "replace")
        _finish_loaded_state(
            app,
            f"Loaded save {source_name}  |  Safety backup: {backup_name}",
            f"Loaded save {source_name}",
        )
    except FileNotFoundError:
        app.set_status("Save file not found.")
    except json.JSONDecodeError:
        app.set_status("Save file is not valid JSON.")
    except ValueError as exc:
        app.set_status(str(exc))
    except OSError as exc:
        app.set_status(f"Load failed: {exc}")


def _make_load_save_action(entry: dict):
    def _action(app):
        title = "Load Save"
        kind_label = _load_save_kind_label(entry)
        message_lines = [
            f"Load {kind_label}?",
            str(entry.get("filename") or entry.get("label") or ""),
            "",
            "Current live state will be replaced.",
        ]
        if str(entry.get("kind") or "") != "main":
            message_lines.append("A safety backup will be created first.")
        app.open_confirm_dialog(
            title=title,
            message="\n".join(message_lines),
            on_yes=lambda inner_app, payload=entry: _load_save_entry(inner_app, payload),
            on_no=None,
            yes_label="Load",
            no_label="Cancel",
        )
    return _action


def enter_load_saves(app, _previous=None):
    _refresh_load_saves_screen(app)


app.add_screen(
    name="saves",
    title="Export Center",
    options=[
        "Save Main State Now",
        "Load Saved JSON",
        "Export Notes as TXT",
        "Export Calculator History as TXT",
        "Export Converter Data as TXT",
        "Export Program Drafts as TXT",
        "Export App Data as JSON",
        "Export Full Backup as JSON",
        "Clear Recent Activity",
        "Back",
    ],
    actions=[
        save_main_state_now,
        "load_saves",
        export_notes_txt,
        export_calculator_txt,
        export_converter_txt,
        export_editor_txt,
        export_app_data_json,
        export_full_backup_json,
        clear_recent_activity,
        "back",
    ],
    main_panel=render_saves_panel,
    main_title="Export Center",
    panel_mode="auto",
    panel_min_height=8,
    panel_max_height=8,
    screen_type="detail",
    hotkeys={"b": "back", "s": save_main_state_now, "l": "load_saves"},
)
app.screens["saves"]["main_panel_width"] = 86
app.screens["saves"]["main_columns"] = 2
app.screens["saves"]["menu_row_gap"] = 0
app.screens["saves"]["menu_box_gap"] = 4
app.screens["saves"]["menu_center_seam"] = True
app.screens["saves"]["footer_text"] = "[Arrows] Move  [Enter] Select  [S] Save  [L] Load  [Esc] Back"
app.screens["saves"]["status_near_footer"] = True

app.add_screen(
    name="load_saves",
    title="Load Saved JSON",
    options=[],
    actions=[],
    on_enter=enter_load_saves,
    main_panel=render_load_saves_panel,
    main_title="Saved JSON Files",
    panel_mode="auto",
    panel_min_height=10,
    panel_max_height=11,
    screen_type="detail",
    hotkeys={"b": "back"},
)
app.screens["load_saves"]["main_panel_width"] = 78
