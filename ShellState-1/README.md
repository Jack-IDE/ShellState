# ShellState

A small zero-dependency Python terminal OS/menu framework demo.

## About

ShellState is a compact terminal-driven shell demo built on a reusable menu framework.
It includes a calculator, a multiline notes tool, and a unit converter, plus a lightweight
memory/snapshot layer for OS-style state experiments.

## Run

From the project root:

```bash
python BOOT.py
```

## Project layout

```text
ShellState/
├─ BOOT.py
├─ README.md
├─ .gitignore
├─ shellstate/
│  ├─ __init__.py
│  ├─ engine.py
│  ├─ tlb_patch.py
│  ├─ runtime_model.py
│  ├─ demo_app.py
│  └─ apps/
│     ├─ __init__.py
│     ├─ calculator.py
│     ├─ notes.py
│     ├─ converter.py
│     ├─ program_maker.py
│     ├─ export_center.py
│     └─ shell_ui.py
└─ runtime/
   ├─ snapshots/
   └─ exports/
```

## Notes

- `BOOT.py` is the simple entry point.
- `shellstate/engine.py` is the shared terminal/UI framework.
- `shellstate/runtime_model.py` holds shared state, save helpers, and app-facing constants.
- `shellstate/apps/` contains the built-in app modules and screen registrations.
- All generated runtime files go into `runtime/`.
- `runtime/snapshots/` holds RAM/swap snapshot files and metadata when generated.
- `runtime/exports/` holds optional exported files when generated.
- `runtime/demo_save.json` is only a bootstrap path used before the memory manager attaches.

## Requirements

- Python 3.10+
- No external dependencies
