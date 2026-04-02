# ShellState

ShellState is a state-based shell/runtime with a text-menu control plane and a built-in graphics subsystem.

This update is the first repo pass that includes the graphics engine as a real part of the project instead of a side experiment. The shell stays menu-driven, while graphics lives in its own workspace and CLI.

## What is in this update

- built-in 2D image rendering
- built-in 3D scene rendering
- frame-sequence export for clips
- a Graphics Lab workspace inside the shell
- a HOME-screen image renderer driven by the graphics engine
- a separate `GRAPHICS.py` entry point for direct rendering/export tasks

The boundary is simple:

- `shell/` owns the normal menu UI
- `graphics/` owns rendering, export, and media helpers
- `apps/graphics_lab.py` is the bridge workspace inside the shell

Graphics does not replace the shell UI. It is a parallel subsystem.

## Boot

```
python3 BOOT.py
```

## Graphics CLI

```
python3 GRAPHICS.py selftest
```

The self-test writes preview files under:

```
runtime/exports/graphics/selftest/
```

Useful commands:

```
python3 GRAPHICS.py render-2d --out image2d.ppm
python3 GRAPHICS.py render --width 64 --height 36 --out still3d.ppm
python3 GRAPHICS.py scene-clip --frames 6 --fps 6 --width 48 --height 27 --outdir scene_clip
python3 GRAPHICS.py render-game-frame --out game2d.ppm
python3 GRAPHICS.py game-clip --frames 24 --fps 24 --outdir game_clip
```

## In-shell graphics

Open:

```
Utilities -> Graphics Lab
```

Graphics Lab lets you:

- load a built-in scene preset
- edit scene JSON
- import a scene JSON file
- render a preview image
- open the real image in a separate viewer

The preview render is written to:

```
runtime/exports/graphics/lab/current_lab.ppm
```

## HOME image

Open:

```
Settings -> Home Image
```

This renders a graphics-engine image for the HOME screen and stores it at:

```
runtime/exports/graphics/home/current_home.ppm
```

## Dependencies

Core rendering is stdlib-only Python.

For opening a real image window, ShellState tries:

- `tkinter` when available
- otherwise a platform opener such as `termux-open`, `open`, `xdg-open`, or `gio open`

The shell and graphics export paths do not require third-party Python packages.

## Current scope

Present in this pass:

- stdlib-only 2D raster helpers
- field-based 3D still rendering
- frame-sequence export for sample clips
- minimal game/world snapshot rendering
- HOME-screen graphics integration

## License

Apache-2.0
