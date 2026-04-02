"""Shared ShellState app state, constants, paths, and save helpers."""

import json
import os
from datetime import datetime

from shellstate.core.engine import TerminalApp
from shellstate.graphics import GraphicsService


PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(PACKAGE_DIR))
RUNTIME_DIR = os.path.join(PROJECT_ROOT, "runtime")
SNAPSHOTS_DIR = os.path.join(RUNTIME_DIR, "snapshots")
EXPORTS_DIR = os.path.join(RUNTIME_DIR, "exports")
GRAPHICS_EXPORTS_DIR = os.path.join(EXPORTS_DIR, "graphics")
PRIMARY_DATA_FILE = os.path.join(RUNTIME_DIR, "shellstate_save.json")
LEGACY_DATA_FILE = os.path.join(RUNTIME_DIR, "demo_save.json")
PRIMARY_SNAPSHOT_BASE = os.path.join(SNAPSHOTS_DIR, "shellstate_save")
LEGACY_SNAPSHOT_BASE = os.path.join(SNAPSHOTS_DIR, "demo_save")
APP_DATA_FORMAT = "shellstate-app-data"
FULL_BACKUP_FORMAT = "shellstate-full-backup"
LEGACY_FULL_BACKUP_FORMAT = "shellstate-demo-backup"
FULL_BACKUP_FORMATS = {FULL_BACKUP_FORMAT, LEGACY_FULL_BACKUP_FORMAT}


def _prefer_runtime_path(primary: str, legacy: str) -> str:
    if os.path.exists(primary):
        return primary
    if os.path.exists(legacy):
        return legacy
    return primary


def _snapshot_base_has_files(base: str) -> bool:
    directory = os.path.dirname(base)
    prefix = os.path.basename(base)
    if not os.path.isdir(directory):
        return False
    try:
        return any(name.startswith(prefix) for name in os.listdir(directory))
    except OSError:
        return False


DATA_FILE = _prefer_runtime_path(PRIMARY_DATA_FILE, LEGACY_DATA_FILE)
SNAPSHOT_BASE = PRIMARY_SNAPSHOT_BASE
if not _snapshot_base_has_files(PRIMARY_SNAPSHOT_BASE) and _snapshot_base_has_files(LEGACY_SNAPSHOT_BASE):
    SNAPSHOT_BASE = LEGACY_SNAPSHOT_BASE

app = TerminalApp(data_file=DATA_FILE)
graphics = GraphicsService(RUNTIME_DIR, EXPORTS_DIR)

_MAX_CALC_EXPR_LEN = 128
_MAX_CALC_ABS_VALUE = 10 ** 12
_MAX_RECENT_ACTIVITY = 40
_MAX_CONVERTER_RECENT = 20
_SPEED_DIAL_MIN_SLOTS = 0
_SPEED_DIAL_MAX_SLOTS = 5
_SPEED_DIAL_DEFAULTS = ["", "notes", ""]
_SPEED_DIAL_CHOICES = [
    ("Empty", ""),
    ("Program Maker", "program_maker"),
    ("Calculator", "calculator"),
    ("Quick Notes", "notes"),
    ("Unit Converter", "converter"),
    ("Graphics Lab", "graphics_lab"),
    ("Export Center", "saves"),
    ("System", "system"),
]


# ─────────────────────────────────────────────────────────────────
#  SHARED HELPERS / STATE MODEL
# ─────────────────────────────────────────────────────────────────


def _ensure_runtime_dirs() -> None:
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
    os.makedirs(EXPORTS_DIR, exist_ok=True)
    os.makedirs(GRAPHICS_EXPORTS_DIR, exist_ok=True)
    graphics.ensure_dirs()


def _system_store(app) -> dict:
    return app.app_data.setdefault("system", {})


def _system_settings(app) -> dict:
    return _system_store(app).setdefault("settings", {})


def _app_store(app, name: str) -> dict:
    return app.app_data.setdefault("apps", {}).setdefault(name, {})


def _calculator_store(app) -> dict:
    return _app_store(app, "calculator")


def _notes_store(app) -> dict:
    return _app_store(app, "notes")


def _converter_store(app) -> dict:
    return _app_store(app, "converter")


def _editor_store(app) -> dict:
    return _app_store(app, "editor")


def _speed_dials(app) -> list:
    system = _system_store(app)
    if "speed_dials" not in system:
        system["speed_dials"] = list(_SPEED_DIAL_DEFAULTS)
    dials = system.get("speed_dials")
    if not isinstance(dials, list):
        dials = list(_SPEED_DIAL_DEFAULTS)
    valid_targets = {target for _, target in _SPEED_DIAL_CHOICES}
    cleaned = [str(item) for item in dials if str(item) in valid_targets]
    while len(cleaned) < _SPEED_DIAL_MIN_SLOTS:
        cleaned.append("")
    cleaned = cleaned[:_SPEED_DIAL_MAX_SLOTS]
    system["speed_dials"] = cleaned
    return cleaned


def _speed_dial_slot_count(app) -> int:
    return len(_speed_dials(app))


def _speed_dial_label_from_target(target: str) -> str:
    for label, key in _SPEED_DIAL_CHOICES:
        if key == target:
            return label
    return str(target or "Unassigned")


def _recent_activity(app) -> list:
    return _system_store(app).setdefault("recent_activity", [])


def _recent_exports(app) -> list:
    return _system_store(app).setdefault("recent_exports", [])


def _trim_list(values: list, limit: int) -> list:
    limit = max(1, int(limit))
    return values[-limit:] if len(values) > limit else values


def _record_activity(app, message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    activity = _recent_activity(app)
    activity.append(f"{timestamp}  {message}")
    _system_store(app)["recent_activity"] = activity[-_MAX_RECENT_ACTIVITY:]


def _record_export(app, filename: str) -> None:
    settings = _system_settings(app)
    limit = max(1, int(settings.get("recent_exports_limit", 12)))
    exports = [name for name in _recent_exports(app) if name != filename]
    exports.insert(0, filename)
    _system_store(app)["recent_exports"] = exports[:limit]
    _record_activity(app, f"Exported {filename}")


def _timestamp_slug() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _export_path(filename: str) -> str:
    safe = filename.replace("/", "_").replace("\\", "_")
    return os.path.join(EXPORTS_DIR, safe)


def _write_text_export(app, filename: str, text: str) -> None:
    path = _export_path(filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    _record_export(app, os.path.basename(path))
    app.set_status(f"Exported: {os.path.basename(path)}")


def _write_json_export(app, filename: str, payload: dict) -> None:
    path = _export_path(filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")
    _record_export(app, os.path.basename(path))
    app.set_status(f"Exported: {os.path.basename(path)}")


def _write_json_file(path: str, payload: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def _safe_import_filename(raw: str) -> str:
    name = os.path.basename((raw or "").strip())
    if not name:
        raise ValueError("Enter a filename.")
    if name.startswith('.'):
        raise ValueError("Hidden filenames are not allowed.")
    if '/' in name or '\\' in name:
        raise ValueError("Invalid filename.")
    if not name.lower().endswith('.json'):
        raise ValueError("Import expects a .json file.")
    return name


def _load_import_payload(filename: str) -> tuple[str, dict]:
    safe_name = _safe_import_filename(filename)
    path = _export_path(safe_name)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"No such export: {safe_name}")
    with open(path, 'r', encoding='utf-8') as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError("Import JSON must contain an object at the top level.")

    fmt = str(payload.get('format') or '')
    if fmt in FULL_BACKUP_FORMATS:
        if not isinstance(payload.get('system'), dict):
            raise ValueError("Backup is missing a valid 'system' object.")
        if not isinstance(payload.get('apps'), dict):
            raise ValueError("Backup is missing a valid 'apps' object.")
    elif fmt == APP_DATA_FORMAT:
        if not isinstance(payload.get('apps'), dict):
            raise ValueError("App-data export is missing a valid 'apps' object.")
    else:
        raise ValueError(f"Unsupported import format. Supported: {FULL_BACKUP_FORMAT}, {APP_DATA_FORMAT}.")
    return safe_name, payload


def _make_auto_backup_file(app) -> str:
    filename = f"pre_import_backup_{_timestamp_slug()}.json"
    _write_json_file(_export_path(filename), _build_full_backup_payload(app))
    return filename


def _import_payload_summary(payload: dict) -> list[str]:
    fmt = str(payload.get('format') or '')
    exported_at = str(payload.get('exported_at') or 'unknown')
    apps_payload = payload.get('apps', {}) if isinstance(payload.get('apps'), dict) else {}
    system_payload = payload.get('system', {}) if isinstance(payload.get('system'), dict) else {}

    calculator = apps_payload.get('calculator', {}) if isinstance(apps_payload.get('calculator'), dict) else {}
    notes = apps_payload.get('notes', {}) if isinstance(apps_payload.get('notes'), dict) else {}
    converter = apps_payload.get('converter', {}) if isinstance(apps_payload.get('converter'), dict) else {}
    editor = apps_payload.get('editor', {}) if isinstance(apps_payload.get('editor'), dict) else {}

    calc_history = len(calculator.get('history', [])) if isinstance(calculator.get('history', []), list) else 0
    note_count = len(notes.get('notes', [])) if isinstance(notes.get('notes', []), list) else 0
    conv_recent = len(converter.get('recent', [])) if isinstance(converter.get('recent', []), list) else 0
    draft_count = len(editor.get('drafts', {})) if isinstance(editor.get('drafts', {}), dict) else 0

    if fmt in FULL_BACKUP_FORMATS:
        scope = 'Replace system + apps'
        mode = 'Replace only'
        settings_count = len(system_payload.get('settings', {})) if isinstance(system_payload.get('settings', {}), dict) else 0
        activity_count = len(system_payload.get('recent_activity', [])) if isinstance(system_payload.get('recent_activity', []), list) else 0
        extra = [
            f"  Import modes: {mode}",
            f"  System settings: {settings_count}",
            f"  Recent activity entries: {activity_count}",
        ]
    else:
        scope = 'Apps only (keep current system state)'
        extra = [
            '  Import modes: REPLACE or MERGE',
            '  MERGE keeps current app data and adds imported data on top.',
        ]

    return [
        f"  Format: {fmt}",
        f"  Exported at: {exported_at}",
        f"  Import scope: {scope}",
        f"  Notes: {note_count}",
        f"  Calculator history: {calc_history}",
        f"  Converter recent: {conv_recent}",
        f"  Editor drafts: {draft_count}",
        *extra,
    ]


def _merge_unique_list(existing: list, incoming: list) -> list:
    merged = list(existing)
    for item in incoming:
        if item not in merged:
            merged.append(item)
    return merged


def _merge_app_payloads(current_apps: dict, imported_apps: dict) -> dict:
    merged = {
        'calculator': dict(current_apps.get('calculator', {})),
        'notes': dict(current_apps.get('notes', {})),
        'converter': dict(current_apps.get('converter', {})),
        'editor': dict(current_apps.get('editor', {})),
    }

    cur_calc = merged['calculator']
    imp_calc = imported_apps.get('calculator', {}) if isinstance(imported_apps.get('calculator'), dict) else {}
    cur_calc['history'] = _merge_unique_list(
        cur_calc.get('history', []) if isinstance(cur_calc.get('history', []), list) else [],
        imp_calc.get('history', []) if isinstance(imp_calc.get('history', []), list) else [],
    )
    cur_sessions = cur_calc.get('sessions', {}) if isinstance(cur_calc.get('sessions', {}), dict) else {}
    imp_sessions = imp_calc.get('sessions', {}) if isinstance(imp_calc.get('sessions', {}), dict) else {}
    cur_calc['sessions'] = {**cur_sessions, **imp_sessions}

    cur_notes = merged['notes']
    imp_notes = imported_apps.get('notes', {}) if isinstance(imported_apps.get('notes'), dict) else {}
    cur_notes['notes'] = _merge_unique_list(
        cur_notes.get('notes', []) if isinstance(cur_notes.get('notes', []), list) else [],
        imp_notes.get('notes', []) if isinstance(imp_notes.get('notes', []), list) else [],
    )
    cur_collections = cur_notes.get('collections', {}) if isinstance(cur_notes.get('collections', {}), dict) else {}
    imp_collections = imp_notes.get('collections', {}) if isinstance(imp_notes.get('collections', {}), dict) else {}
    cur_notes['collections'] = {**cur_collections, **imp_collections}

    cur_conv = merged['converter']
    imp_conv = imported_apps.get('converter', {}) if isinstance(imported_apps.get('converter'), dict) else {}
    cur_conv['recent'] = _merge_unique_list(
        cur_conv.get('recent', []) if isinstance(cur_conv.get('recent', []), list) else [],
        imp_conv.get('recent', []) if isinstance(imp_conv.get('recent', []), list) else [],
    )
    cur_presets = cur_conv.get('presets', {}) if isinstance(cur_conv.get('presets', {}), dict) else {}
    imp_presets = imp_conv.get('presets', {}) if isinstance(imp_conv.get('presets', {}), dict) else {}
    cur_conv['presets'] = {**cur_presets, **imp_presets}
    imported_last = str(imp_conv.get('last_result') or '')
    if imported_last:
        cur_conv['last_result'] = imported_last

    cur_editor = merged['editor']
    imp_editor = imported_apps.get('editor', {}) if isinstance(imported_apps.get('editor'), dict) else {}
    cur_drafts = cur_editor.get('drafts', {}) if isinstance(cur_editor.get('drafts', {}), dict) else {}
    imp_drafts = imp_editor.get('drafts', {}) if isinstance(imp_editor.get('drafts', {}), dict) else {}
    cur_editor['drafts'] = {**cur_drafts, **imp_drafts}
    imported_current_draft = str(imp_editor.get('current_draft') or '')
    if imported_current_draft:
        cur_editor['current_draft'] = imported_current_draft
    imported_buffer = imp_editor.get('buffer')
    if isinstance(imported_buffer, str):
        cur_editor['buffer'] = imported_buffer
    if 'unsaved' in imp_editor:
        cur_editor['unsaved'] = bool(imp_editor.get('unsaved'))

    for key, value in imported_apps.items():
        if key not in merged and isinstance(value, dict):
            merged[key] = value

    return merged


def _apply_payload_import(app, payload: dict, source_name: str, mode: str) -> None:
    fmt = str(payload.get('format') or '')
    old_data = app.app_data
    mode = mode.upper().strip()

    if fmt in FULL_BACKUP_FORMATS:
        if mode != 'REPLACE':
            raise ValueError('Full backups support REPLACE only.')
        new_data = {
            'system': payload.get('system', {}),
            'apps': payload.get('apps', {}),
        }
        activity_message = f"Imported {source_name} (replace full backup)"
    elif fmt == APP_DATA_FORMAT:
        if mode == 'REPLACE':
            new_apps = payload.get('apps', {})
            activity_message = f"Imported {source_name} (replace app data)"
        elif mode == 'MERGE':
            current_apps = old_data.get('apps', {}) if isinstance(old_data.get('apps'), dict) else {}
            imported_apps = payload.get('apps', {}) if isinstance(payload.get('apps'), dict) else {}
            new_apps = _merge_app_payloads(current_apps, imported_apps)
            activity_message = f"Imported {source_name} (merge app data)"
        else:
            raise ValueError('App-data imports support REPLACE or MERGE.')
        new_data = {
            'system': old_data.get('system', {}),
            'apps': new_apps,
        }
    else:
        raise ValueError('Unsupported import format.')

    app.app_data.clear()
    app.app_data.update(new_data)
    _init_defaults(app)
    _record_activity(app, activity_message)


def import_json_backup(app):
    raw = app.prompt_text('Import JSON filename from exports/: ', title='IMPORT JSON', allow_empty=False)
    if raw is None:
        app.set_status('Input canceled.')
        return
    try:
        source_name, payload = _load_import_payload(raw)
        fmt = str(payload.get('format') or '')
        print('  Import preview:')
        print(f'    Source: {source_name}')
        for line in _import_payload_summary(payload):
            print(line)
        print('  This will create a safety backup before applying the import.')
        if fmt == 'shellstate-app-data':
            confirm = app.prompt_text('Type REPLACE or MERGE to apply, or anything else to cancel: ', title='IMPORT MODE', allow_empty=False)
            mode = (confirm or '').strip().upper()
            if mode not in {'REPLACE', 'MERGE'}:
                app.set_status('Import canceled.')
                return
        else:
            confirm = app.prompt_text('Type IMPORT to apply, or anything else to cancel: ', title='IMPORT MODE', allow_empty=False)
            if confirm is None or confirm.strip().upper() != 'IMPORT':
                app.set_status('Import canceled.')
                return
            mode = 'REPLACE'
        backup_name = _make_auto_backup_file(app)
        _apply_payload_import(app, payload, source_name, mode)
        app.set_status(f"Imported: {source_name} [{mode}] (safety backup: {backup_name})")
    except FileNotFoundError as exc:
        app.set_status(str(exc))
    except ValueError as exc:
        app.set_status(f"Import error: {exc}")
    except json.JSONDecodeError as exc:
        app.set_status(f"Import error: invalid JSON ({exc.msg})")
    except Exception as exc:
        app.set_status(f"Import failed: {type(exc).__name__}: {exc}")


def _build_full_backup_payload(app) -> dict:
    return {
        "format": FULL_BACKUP_FORMAT,
        "version": 2,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "system": _system_store(app),
        "apps": app.app_data.get("apps", {}),
    }


def _migrate_legacy_state(app) -> None:
    data = app.app_data
    system = data.setdefault("system", {})
    apps = data.setdefault("apps", {})
    settings = system.setdefault("settings", {})

    calculator = apps.setdefault("calculator", {})
    notes = apps.setdefault("notes", {})
    converter = apps.setdefault("converter", {})
    editor = apps.setdefault("editor", {})

    if "calc_history" in data:
        history = calculator.setdefault("history", [])
        history.extend(x for x in data.get("calc_history", []) if x not in history)
        del data["calc_history"]

    if "notes" in data and isinstance(data.get("notes"), list):
        note_list = notes.setdefault("notes", [])
        note_list.extend(data.get("notes", []))
        del data["notes"]

    if "last_conversion" in data:
        last = str(data.get("last_conversion") or "")
        if last:
            converter.setdefault("last_result", last)
            recent = converter.setdefault("recent", [])
            if last not in recent:
                recent.append(last)
        del data["last_conversion"]

    if "calc_history_limit" in data:
        settings.setdefault("calc_history_limit", data.get("calc_history_limit"))
        del data["calc_history_limit"]

    if "notes_preview_len" in data:
        settings.setdefault("notes_preview_len", data.get("notes_preview_len"))
        del data["notes_preview_len"]

    if "recent_files_limit" in data:
        settings.setdefault("recent_exports_limit", data.get("recent_files_limit"))
        del data["recent_files_limit"]

    legacy_buffer = data.pop("editor_buffer", "")
    legacy_current = data.pop("current_file", "")
    legacy_unsaved = bool(data.pop("editor_unsaved", False))
    data.pop("current_dir", None)
    data.pop("recent_files", None)

    drafts = editor.setdefault("drafts", {})
    recovered_name = os.path.splitext(os.path.basename(legacy_current or ""))[0].strip() or "default"
    if legacy_buffer:
        drafts.setdefault(recovered_name, legacy_buffer)
        editor.setdefault("current_draft", recovered_name)
        editor.setdefault("buffer", legacy_buffer)
        editor.setdefault("unsaved", legacy_unsaved)


def _init_defaults(app) -> None:
    _migrate_legacy_state(app)

    system = _system_store(app)
    settings = _system_settings(app)
    settings.setdefault("calc_history_limit", 30)
    settings.setdefault("notes_preview_len", 64)
    settings.setdefault("recent_exports_limit", 12)

    system.setdefault("recent_activity", [])
    system.setdefault("recent_exports", [])
    system.setdefault("scratch", {})
    system.setdefault("version", 2)
    current_speed_dials = system.get("speed_dials")
    if current_speed_dials in (["program_maker", "calculator", "notes"], ["", "", ""]):
        system["speed_dials"] = list(_SPEED_DIAL_DEFAULTS)
    elif "speed_dials" not in system or not isinstance(current_speed_dials, list):
        system["speed_dials"] = list(_SPEED_DIAL_DEFAULTS)
    else:
        system["speed_dials"] = [str(item) for item in current_speed_dials]

    calculator = _calculator_store(app)
    calculator.setdefault("history", [])
    calculator.setdefault("sessions", {})
    calculator.setdefault("expr_buffer", "")
    calculator.setdefault("expr_cursor", 0)
    calculator.setdefault("history_browse_index", -1)

    notes = _notes_store(app)
    notes.setdefault("notes", [])
    notes.setdefault("collections", {})
    notes.setdefault("draft_buffer", "")
    notes.setdefault("draft_cursor", 0)

    converter = _converter_store(app)
    converter.setdefault("recent", [])
    converter.setdefault("presets", {})
    converter.setdefault("last_result", "")

    editor = _editor_store(app)
    editor.setdefault("buffer", "")
    editor.setdefault("current_draft", "")
    editor.setdefault("unsaved", False)
    editor.setdefault("drafts", {})
    editor.setdefault("cursor_row", 0)
    editor.setdefault("cursor_col", 0)
    editor.setdefault("goal_col", 0)

    calculator["history"] = _trim_list(
        calculator.get("history", []),
        int(settings.get("calc_history_limit", 30)),
    )
    system["recent_exports"] = _trim_list(
        system.get("recent_exports", []),
        int(settings.get("recent_exports_limit", 12)),
    )


def _current_editor_draft_name(app) -> str:
    return str(_editor_store(app).get("current_draft", "") or "")


def _set_editor_buffer(app, text: str, *, mark_unsaved: bool) -> None:
    editor = _editor_store(app)
    value = str(text or "")
    editor["buffer"] = value
    editor["unsaved"] = mark_unsaved
    lines = value.split("\n") if value else [""]
    row = len(lines) - 1
    col = len(lines[row])
    editor["cursor_row"] = row
    editor["cursor_col"] = col
    editor["goal_col"] = col


def _save_current_draft(app) -> None:
    editor = _editor_store(app)
    drafts = editor.setdefault("drafts", {})
    name = _current_editor_draft_name(app).strip()
    if not name:
        raise ValueError("No draft is currently open.")
    drafts[name] = editor.get("buffer", "")
    editor["current_draft"] = name
    editor["unsaved"] = False
    _record_activity(app, f"Saved draft '{name}'")



__all__ = [
    name for name in globals()
    if name not in {
        '__builtins__', '__cached__', '__doc__', '__file__', '__loader__',
        '__name__', '__package__', '__spec__', '__all__'
    }
]
