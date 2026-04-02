"""Real image display backends for ShellState graphics outputs."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from typing import Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _abs_path(path: str) -> str:
    value = os.path.abspath(os.path.expanduser(str(path or '').strip()))
    if not value:
        raise ValueError('Missing image path.')
    return value


def _can_use_tk_window() -> bool:
    if os.name == 'nt':
        return True
    if sys.platform == 'darwin':
        return True
    return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


def _fit_photo(image, screen_w: int, screen_h: int):
    width = int(image.width())
    height = int(image.height())
    max_w = max(1, int(screen_w * 0.95))
    max_h = max(1, int(screen_h * 0.90))
    if width <= max_w and height <= max_h:
        return image
    step = max(1, max((width + max_w - 1) // max_w, (height + max_h - 1) // max_h))
    return image.subsample(step, step)


def _run_tk_viewer(path: str, title: str, follow: bool) -> bool:
    if not _can_use_tk_window():
        return False
    try:
        import tkinter as tk
    except Exception:
        return False
    try:
        root = tk.Tk()
    except Exception:
        return False
    root.configure(bg='black')
    root.title(title or 'ShellState Image')
    root.bind('<Escape>', lambda event: root.destroy())
    root.bind('q', lambda event: root.destroy())
    root.bind('Q', lambda event: root.destroy())
    holder = tk.Label(root, bg='black', bd=0, highlightthickness=0)
    holder.pack(fill='both', expand=True)
    state = {'mtime': None, 'image': None}

    def load_image() -> None:
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return
        if state['mtime'] == mtime and state['image'] is not None:
            return
        try:
            image = tk.PhotoImage(file=path)
        except Exception:
            return
        fitted = _fit_photo(image, root.winfo_screenwidth(), root.winfo_screenheight())
        state['mtime'] = mtime
        state['image'] = fitted
        holder.configure(image=fitted)
        root.geometry(f"{fitted.width()}x{fitted.height()}")
        try:
            root.minsize(fitted.width(), fitted.height())
        except Exception:
            pass

    def poll() -> None:
        load_image()
        if follow and root.winfo_exists():
            root.after(250, poll)

    load_image()
    poll()
    root.mainloop()
    return True


def _run_external_open(path: str) -> bool:
    path = _abs_path(path)
    commands = []
    if os.environ.get('TERMUX_VERSION'):
        commands.append(['termux-open', path])
    if sys.platform == 'darwin':
        commands.append(['open', path])
    elif os.name == 'nt':
        try:
            os.startfile(path)  # type: ignore[attr-defined]
            return True
        except Exception:
            pass
    else:
        commands.extend((['xdg-open', path], ['gio', 'open', path]))
    for cmd in commands:
        exe = shutil.which(cmd[0])
        if not exe:
            continue
        try:
            kwargs = {'cwd': PROJECT_ROOT}
            if os.name != 'nt':
                kwargs['start_new_session'] = True
            subprocess.Popen([exe, *cmd[1:]], **kwargs)
            return True
        except Exception:
            continue
    return False


def show_image_surface(path: str, title: str = 'ShellState Image', *, follow: bool = True) -> bool:
    path = _abs_path(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    if _run_tk_viewer(path, title, follow):
        return True
    return _run_external_open(path)


def launch_image_surface(path: str, title: str = 'ShellState Image', *, follow: bool = True) -> bool:
    path = _abs_path(path)
    if not os.path.isfile(path):
        return False
    try:
        args = [
            sys.executable,
            '-m',
            'shellstate.graphics.display',
            '--title',
            str(title or 'ShellState Image'),
        ]
        if follow:
            args.append('--follow')
        args.append(path)
        env = dict(os.environ)
        pythonpath = env.get('PYTHONPATH', '')
        env['PYTHONPATH'] = PROJECT_ROOT + (os.pathsep + pythonpath if pythonpath else '')
        kwargs = {'cwd': PROJECT_ROOT, 'env': env}
        if os.name != 'nt':
            kwargs['start_new_session'] = True
        subprocess.Popen(args, **kwargs)
        return True
    except Exception:
        return _run_external_open(path)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='ShellState real image surface viewer')
    parser.add_argument('path')
    parser.add_argument('--title', default='ShellState Image')
    parser.add_argument('--follow', action='store_true')
    args = parser.parse_args(argv)
    try:
        ok = show_image_surface(args.path, args.title, follow=bool(args.follow))
    except Exception:
        ok = False
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
