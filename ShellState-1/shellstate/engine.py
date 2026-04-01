import codecs
import contextlib
import inspect
import io
import json
import os
import re
import select
import shutil
import sys
import time

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


FONT = {
    "A": ("▄▀█", "█▀█"),
    "B": ("█▀▄", "█▀▄"),
    "C": ("█▀▀", "█▄▄"),
    "D": ("█▀▄", "█▄▀"),
    "E": ("█▀▀", "██▄"),
    "F": ("█▀▀", "█▀░"),
    "G": ("█▀▀", "█▄█"),
    "H": ("█░█", "█▀█"),
    "I": ("█", "█"),
    "J": ("░░█", "█▄█"),
    "K": ("█▄▀", "█░█"),
    "L": ("█░░", "█▄▄"),
    "M": ("█▄░▄█", "█░▀░█"),
    "N": ("█▄░█", "█░▀█"),
    "O": ("█▀█", "█▄█"),
    "P": ("█▀█", "█▀▀"),
    "Q": ("█▀█", "██▀"),
    "R": ("█▀█", "█▀▄"),
    "S": ("█▀▀", "▄██"),
    "T": ("▀█▀", "░█░"),
    "U": ("█░█", "█▄█"),
    "V": ("█░█", "▀▄▀"),
    "W": ("█░█░█", "▀▄▀▄▀"),
    "X": ("▀▄▀", "█░█"),
    "Y": ("█▄█", "░█░"),
    "Z": ("▀▀█", "█▄▄"),
    "0": ("█▀█", "█▄█"),
    "1": ("░█░", "░█░"),
    "2": ("▀█▀", "█▄▄"),
    "3": ("▀▀█", "▄▄█"),
    "4": ("█▄█", "░░█"),
    "5": ("█▀▀", "▄▄█"),
    "6": ("█▀▀", "█▄█"),
    "7": ("▀▀█", "░░█"),
    "8": ("█▀█", "█▄█"),
    "9": ("█▀█", "▀▀█"),
    "!": ("█", "░"),
    "?": ("▀█▀", "░█░"),
    ".": ("░", "•"),
    "-": ("▀▀▀", "░░░"),
    "_": ("░░░", "▀▀▀"),
    ":": ("•", "•"),
    "/": ("░▄", "▄░"),
    "\\": ("▄░", "░▄"),
    " ": ("", ""),
}


def render_banner(text: str, letter_gap: int = 1, word_gap: int = 3) -> str:
    text = str(text).upper()
    top_parts: List[str] = []
    bot_parts: List[str] = []
    gap = " " * max(0, letter_gap)
    word_sep = " " * max(1, word_gap)

    for ch in text:
        if ch == " ":
            top_parts.append(word_sep.rstrip())
            bot_parts.append(word_sep.rstrip())
            continue
        top, bot = FONT.get(ch, FONT["?"])
        top_parts.append(top)
        bot_parts.append(bot)

    top_line = gap.join(top_parts).rstrip()
    bot_line = gap.join(bot_parts).rstrip()
    return top_line + "\n" + bot_line


class KeyInput:
    def __init__(self):
        self.windows = os.name == "nt"
        self.stdin_tty = bool(getattr(sys.stdin, "isatty", lambda: False)())
        self.stdout_tty = bool(getattr(sys.stdout, "isatty", lambda: False)())
        self.ansi_supported = self._detect_ansi_support()
        if self.windows:
            import msvcrt

            self.msvcrt = msvcrt
        else:
            import termios
            import tty

            self.termios = termios
            self.tty = tty

    def _detect_ansi_support(self) -> bool:
        if not self.stdout_tty:
            return False
        if self.windows:
            return bool(
                os.getenv("WT_SESSION")
                or os.getenv("ANSICON")
                or os.getenv("TERM")
                or os.getenv("ConEmuANSI") == "ON"
            )
        return True

    def _get_key_windows(self) -> str:
        char = self.msvcrt.getwch()
        if char in ("\x00", "\xe0"):
            next_char = self.msvcrt.getwch()
            if next_char == "H":
                return "UP"
            if next_char == "P":
                return "DOWN"
            if next_char == "K":
                return "LEFT"
            if next_char == "M":
                return "RIGHT"
            return ""
        if char == "\r":
            return "ENTER"
        if char == "\x08":
            return "BACKSPACE"
        if char == "\x1b":
            return "ESC"
        if char == "\x03":
            raise KeyboardInterrupt
        return char

    def _read_char_unix(self) -> str:
        decoder = codecs.getincrementaldecoder("utf-8")()
        fd = sys.stdin.fileno()
        while True:
            data = os.read(fd, 1)
            if not data:
                return ""
            try:
                char = decoder.decode(data, final=False)
            except UnicodeDecodeError:
                return ""
            if char:
                return char

    def enter_raw(self) -> None:
        """Enter cbreak mode once for the duration of the TUI session.
        setcbreak (not setraw) is used so OPOST is preserved — meaning \n still
        translates to \r\n and all existing print() calls keep working normally."""
        if not self.stdin_tty:
            raise RuntimeError("Not running in an interactive terminal.")
        if self.windows:
            return
        fd = sys.stdin.fileno()
        self._saved_settings = self.termios.tcgetattr(fd)
        self.tty.setcbreak(fd)

    def exit_raw(self) -> None:
        """Restore terminal settings saved by enter_raw()."""
        if self.windows:
            return
        saved = getattr(self, "_saved_settings", None)
        if saved is not None:
            fd = sys.stdin.fileno()
            self.termios.tcsetattr(fd, self.termios.TCSANOW, saved)
            self._saved_settings = None

    def _get_key_unix(self, timeout: Optional[float] = None) -> str:
        if not self.stdin_tty:
            return ""
        if timeout is not None:
            ready, _, _ = select.select([sys.stdin], [], [], timeout)
            if not ready:
                return ""

        char = self._read_char_unix()
        if char == "\x03":
            raise KeyboardInterrupt
        if char == "\x1b":
            ready, _, _ = select.select([sys.stdin], [], [], 0.03)
            if not ready:
                return "ESC"
            next_char = self._read_char_unix()
            if next_char == "[":
                ready, _, _ = select.select([sys.stdin], [], [], 0.03)
                if ready:
                    last_char = self._read_char_unix()
                    if last_char == "A":
                        return "UP"
                    if last_char == "B":
                        return "DOWN"
                    if last_char == "C":
                        return "RIGHT"
                    if last_char == "D":
                        return "LEFT"
            return "ESC"
        if char in ("\r", "\n"):
            return "ENTER"
        if char in ("\x7f", "\b"):
            return "BACKSPACE"
        return char

    def get_key(self, timeout: Optional[float] = None) -> str:
        if self.windows:
            if timeout is None:
                return self._get_key_windows()
            deadline = time.monotonic() + max(0.0, timeout)
            while time.monotonic() < deadline:
                if self.msvcrt.kbhit():
                    return self._get_key_windows()
                time.sleep(0.01)
            return ""
        return self._get_key_unix(timeout=timeout)

    def get_text(self, prompt: str = "") -> Optional[str]:
        if not self.stdin_tty:
            raise RuntimeError("Text input requires an interactive terminal.")
        # Prompt text is intentionally not printed here. Screen-specific input
        # guidance should live in the app's panels/windows rather than in a
        # transient footer prompt line.
        text = ""
        while True:
            key = self.get_key()
            if key == "ENTER":
                print("")
                return text
            if key == "BACKSPACE":
                if text:
                    text = text[:-1]
                    print(" ", end="", flush=True)
                continue
            if key == "ESC":
                print("")
                return None
            if len(key) == 1 and key.isprintable():
                text += key
                print(key, end="", flush=True)


class Actions:
    @staticmethod
    def goto(screen: str, *, push_history: bool = True) -> Dict[str, Any]:
        return {"type": "goto", "screen": screen, "push_history": push_history}

    @staticmethod
    def input(
        *,
        prompt: str = "Enter value: ",
        target: str = "last_input",
        return_to: Optional[str] = None,
        allow_empty: bool = True,
        status_template: str = "Saved: {value}",
    ) -> Dict[str, Any]:
        return {
            "type": "input",
            "prompt": prompt,
            "target": target,
            "return_to": return_to,
            "allow_empty": allow_empty,
            "status_template": status_template,
        }

    @staticmethod
    def back() -> Dict[str, Any]:
        return {"type": "back"}

    @staticmethod
    def save() -> Dict[str, Any]:
        return {"type": "save"}

    @staticmethod
    def status(message: str) -> Dict[str, Any]:
        return {"type": "status", "message": message}

    @staticmethod
    def exit() -> Dict[str, Any]:
        return {"type": "exit"}

    @staticmethod
    def call(func: Callable[[Any], Any]) -> Dict[str, Any]:
        return {"type": "function", "callable": func}

    @staticmethod
    def confirm(
        *,
        title: str = "Confirm",
        message: str = "Are you sure?",
        on_yes: Any = None,
        on_no: Any = None,
        yes_label: str = "Yes",
        no_label: str = "No",
    ) -> Dict[str, Any]:
        return {
            "type": "confirm",
            "title": title,
            "message": message,
            "on_yes": on_yes,
            "on_no": on_no,
            "yes_label": yes_label,
            "no_label": no_label,
        }

    @staticmethod
    def form_field(field: str) -> Dict[str, Any]:
        return {"type": "form_field", "field": field}

    @staticmethod
    def set_value(
        key: str,
        value: Any,
        *,
        status_template: str = "{key} set to {value}",
    ) -> Dict[str, Any]:
        return {
            "type": "set_value",
            "key": key,
            "value": value,
            "status_template": status_template,
        }

    @staticmethod
    def chain(*actions: Any) -> Dict[str, Any]:
        return {"type": "chain", "actions": list(actions)}

    @staticmethod
    def noop() -> Dict[str, Any]:
        return {"type": "noop"}


A = Actions


@dataclass
class FormField:
    key: str
    label: str
    prompt: Optional[str] = None
    allow_empty: bool = True
    parser: Optional[Callable[[str], Any]] = None
    validator: Optional[Callable[[Any], Any]] = None
    formatter: Optional[Callable[[Any], str]] = None
    status_template: str = "Saved {label}: {value}"
    placeholder: str = "(empty)"
    empty_value: Any = ""

    def display_value(self, value: Any) -> str:
        if value in (None, ""):
            return self.placeholder
        if callable(self.formatter):
            return str(self.formatter(value))
        return str(value)

    def build_prompt(self) -> str:
        return self.prompt or f"{self.label}: "


Hook = Callable[..., Any]
ScreenDict = Dict[str, Any]
ActionType = Any


class TerminalApp:
    def __init__(self, data_file: str = "app_data.json"):
        self.input_handler = KeyInput()
        self.screens: Dict[str, ScreenDict] = {}
        self.current_screen = "main"
        self.selected_index = 0
        self.running = True
        self.data_file = data_file
        self.app_data: Dict[str, Any] = {}
        self.status_msg = ""
        self.screen_stack: List[str] = []
        self.selection_memory: Dict[str, int] = {}
        self.last_key = ""
        self.last_action: Any = None
        self._temp_screen_counter = 0
        self._interactive_stdout = self.input_handler.stdout_tty
        self._ansi_enabled = self.input_handler.ansi_supported
        self._needs_render = True
        self._last_frame = ""
        self._input_session: Optional[Dict[str, Any]] = None
        self.default_title_style = "banner"
        self.default_title_align = "center"
        self.default_menu_layout = "vertical"
        self.default_menu_align = "center"
        self.default_screen_type = "menu"
        self.layout_profiles: Dict[str, Dict[str, Any]] = {
            "menu": {
                "title_style": "banner",
                "title_align": "center",
                "menu_layout": "vertical",
                "menu_align": "center",
                "show_utility_bar": True,
                "panel_mode": "auto",
            },
            "home": {
                "title_style": "banner",
                "title_align": "center",
                "menu_layout": "horizontal",
                "menu_align": "center",
                "show_utility_bar": True,
                "panel_mode": "auto",
            },
            "hub": {
                "title_style": "banner",
                "title_align": "center",
                "menu_layout": "horizontal",
                "menu_align": "center",
                "show_utility_bar": True,
                "panel_mode": "auto",
            },
            "detail": {
                "title_style": "banner",
                "title_align": "center",
                "menu_layout": "vertical",
                "menu_align": "center",
                "show_utility_bar": True,
                "panel_mode": "auto",
            },
            "workspace_split": {
                "title_style": "banner",
                "title_align": "center",
                "menu_layout": "vertical",
                "menu_align": "center",
                "show_utility_bar": True,
                "panel_mode": "split",
                "info_panel_ratio": 0.28,
                "panel_min_height": 8,
            },
            "workspace_full": {
                "title_style": "banner",
                "title_align": "center",
                "menu_layout": "vertical",
                "menu_align": "center",
                "show_utility_bar": True,
                "panel_mode": "main_full",
                "main_panel_full": True,
                "panel_min_height": 10,
            },
        }
        self.load_data()

    def add_screen(
        self,
        name: str,
        title: str,
        options: List[Any],
        actions: List[ActionType],
        *,
        on_render: Optional[Hook] = None,
        on_enter: Optional[Hook] = None,
        on_exit: Optional[Hook] = None,
        on_action: Optional[Hook] = None,
        on_input: Optional[Hook] = None,
        on_tick: Optional[Hook] = None,
        tick_interval: Optional[float] = None,
        hotkeys: Optional[Dict[str, ActionType]] = None,
        form_fields: Optional[Dict[str, FormField]] = None,
        screen_type: Optional[str] = None,
        title_style: Optional[str] = None,
        title_align: Optional[str] = None,
        menu_layout: Optional[str] = None,
        menu_align: Optional[str] = None,
        info_panel: Optional[Hook] = None,
        main_panel: Optional[Hook] = None,
        info_title: Optional[str] = None,
        main_title: Optional[str] = None,
        info_panel_width: Optional[int] = None,
        info_panel_ratio: Optional[float] = None,
        panel_mode: Optional[str] = None,
        panel_height: Optional[int] = None,
        panel_min_height: Optional[int] = None,
        panel_max_height: Optional[int] = None,
        main_panel_full: bool = False,
        panel_gap: int = 4,
    ) -> None:
        if not name or not isinstance(name, str):
            raise ValueError("Screen name must be a non-empty string.")
        if len(options) != len(actions):
            raise ValueError(
                f"Screen '{name}' has {len(options)} options but {len(actions)} actions."
            )
        if name in self.screens:
            raise ValueError(f"Screen '{name}' is already registered.")
        if tick_interval is not None and tick_interval <= 0:
            raise ValueError("tick_interval must be greater than 0.")
        layout_overrides: Dict[str, Any] = {}
        if title_style is not None:
            layout_overrides["title_style"] = title_style
        if title_align is not None:
            layout_overrides["title_align"] = title_align
        if menu_layout is not None:
            layout_overrides["menu_layout"] = menu_layout
        if menu_align is not None:
            layout_overrides["menu_align"] = menu_align
        if info_panel_width is not None:
            layout_overrides["info_panel_width"] = info_panel_width
        if info_panel_ratio is not None:
            layout_overrides["info_panel_ratio"] = info_panel_ratio
        if panel_mode not in (None, "", "auto"):
            layout_overrides["panel_mode"] = panel_mode
        if panel_height is not None:
            layout_overrides["panel_height"] = panel_height
        if panel_min_height is not None:
            layout_overrides["panel_min_height"] = panel_min_height
        if panel_max_height is not None:
            layout_overrides["panel_max_height"] = panel_max_height
        if main_panel_full:
            layout_overrides["main_panel_full"] = True
        if panel_gap != 4:
            layout_overrides["panel_gap"] = panel_gap

        self.screens[name] = {
            "title": title,
            "options": list(options),
            "actions": list(actions),
            "on_render": on_render,
            "on_enter": on_enter,
            "on_exit": on_exit,
            "on_action": on_action,
            "on_input": on_input,
            "on_tick": on_tick,
            "tick_interval": tick_interval,
            "hotkeys": {str(k): v for k, v in (hotkeys or {}).items()},
            "form_fields": dict(form_fields or {}),
            "screen_type": (screen_type or self.default_screen_type),
            "layout_overrides": layout_overrides,
            "info_panel": info_panel,
            "main_panel": main_panel,
            "info_title": info_title,
            "main_title": main_title,
        }

    def add_form_screen(
        self,
        name: str,
        title: str,
        fields: List[FormField],
        *,
        done_label: Optional[str] = "Done",
        done_action: ActionType = "back",
        include_save: bool = False,
        extra_options: Optional[List[tuple[str, ActionType]]] = None,
        on_render: Optional[Hook] = None,
        on_enter: Optional[Hook] = None,
        on_exit: Optional[Hook] = None,
        on_action: Optional[Hook] = None,
        on_input: Optional[Hook] = None,
        on_tick: Optional[Hook] = None,
        tick_interval: Optional[float] = None,
        hotkeys: Optional[Dict[str, ActionType]] = None,
        screen_type: Optional[str] = None,
        title_style: Optional[str] = None,
        title_align: Optional[str] = None,
        menu_layout: Optional[str] = None,
        menu_align: Optional[str] = None,
        info_panel: Optional[Hook] = None,
        main_panel: Optional[Hook] = None,
        info_title: Optional[str] = None,
        main_title: Optional[str] = None,
        info_panel_width: Optional[int] = None,
        info_panel_ratio: Optional[float] = None,
        panel_mode: Optional[str] = None,
        panel_height: Optional[int] = None,
        panel_min_height: Optional[int] = None,
        panel_max_height: Optional[int] = None,
        main_panel_full: bool = False,
        panel_gap: int = 4,
    ) -> None:
        field_map: Dict[str, FormField] = {}
        for field in fields:
            if field.key in field_map:
                raise ValueError(f"Duplicate form field key: {field.key}")
            field_map[field.key] = field

        options: List[Any] = []
        actions: List[ActionType] = []
        for field in fields:
            options.append(lambda app, screen_name=name, field_key=field.key: app.get_form_field_label(screen_name, field_key))
            actions.append(A.form_field(field.key))

        if include_save:
            options.append("Save Now")
            actions.append(A.save())

        for label, action in extra_options or []:
            options.append(label)
            actions.append(action)

        if done_label is not None:
            options.append(done_label)
            actions.append(done_action)

        self.add_screen(
            name=name,
            title=title,
            options=options,
            actions=actions,
            on_render=on_render,
            on_enter=on_enter,
            on_exit=on_exit,
            on_action=on_action,
            on_input=on_input,
            on_tick=on_tick,
            tick_interval=tick_interval,
            hotkeys=hotkeys,
            form_fields=field_map,
            screen_type=screen_type,
            title_style=title_style,
            title_align=title_align,
            menu_layout=menu_layout,
            menu_align=menu_align,
            info_panel=info_panel,
            main_panel=main_panel,
            info_title=info_title,
            main_title=main_title,
            info_panel_width=info_panel_width,
            info_panel_ratio=info_panel_ratio,
            panel_mode=panel_mode,
            panel_height=panel_height,
            panel_min_height=panel_min_height,
            panel_max_height=panel_max_height,
            main_panel_full=main_panel_full,
            panel_gap=panel_gap,
        )

    def clear(self) -> None:
        if not self._interactive_stdout:
            return
        if self._ansi_enabled:
            sys.stdout.write("[H[J")
            sys.stdout.flush()
            return
        command = "cls" if os.name == "nt" else "clear"
        if os.system(command) != 0:
            print("\n" * 3)

    def _box_lines(self, text: str, *, selected: bool = False) -> List[str]:
        text = str(text)
        border = "┌" + "─" * (len(text) + 2) + "┐"
        middle = "│ " + text + " │"
        bottom = "└" + "─" * (len(text) + 2) + "┘"
        if selected and self._ansi_enabled:
            return [
                f"[7m{border}[0m",
                f"[7m{middle}[0m",
                f"[7m{bottom}[0m",
            ]
        return [border, middle, bottom]

    def _visible_len(self, text: str) -> int:
        return len(ANSI_RE.sub("", str(text)))


    def _screen_type(self, screen: ScreenDict) -> str:
        screen_type = str(screen.get("screen_type") or self.default_screen_type or "menu").lower()
        return screen_type if screen_type in self.layout_profiles else "menu"

    def _screen_profile(self, screen: ScreenDict) -> Dict[str, Any]:
        return dict(self.layout_profiles.get(self._screen_type(screen), self.layout_profiles["menu"]))

    def _screen_value(self, screen: ScreenDict, key: str, fallback: Any = None) -> Any:
        overrides = screen.get("layout_overrides") or {}
        if key in overrides:
            return overrides[key]
        value = screen.get(key)
        if value not in (None, "", "auto"):
            return value
        profile = self._screen_profile(screen)
        if key in profile:
            return profile[key]
        return fallback

    def _interaction_mode(self, screen: ScreenDict) -> str:
        mode = str(screen.get("interaction_mode") or "menu").lower()
        return mode if mode in {"menu", "typing", "editor", "input", "text"} else "menu"

    def _dispatch_screen_key(self, screen: ScreenDict, key: str) -> Any:
        handler = screen.get("on_key")
        if not callable(handler):
            return None
        result = self._call_hook(handler, key, hook_name="Key Hook Error")
        if result not in (None, True, False):
            self.handle_action(result)
            self._needs_render = True
            return True
        return result

    def _menu_layout(self, screen: ScreenDict) -> str:
        layout = str(self._screen_value(screen, "menu_layout", self.default_menu_layout or "vertical")).lower()
        return layout if layout in {"vertical", "horizontal"} else "vertical"

    def _menu_align(self, screen: ScreenDict) -> str:
        align = str(self._screen_value(screen, "menu_align", self.default_menu_align or "center")).lower()
        return align if align in {"left", "center", "right"} else "center"

    def _terminal_width(self) -> int:
        try:
            return max(40, shutil.get_terminal_size((80, 24)).columns)
        except Exception:
            return 80

    def _terminal_height(self) -> int:
        try:
            return max(18, shutil.get_terminal_size((80, 24)).lines)
        except Exception:
            return 24

    def _align_line(self, line: str, width: int, align: str = "center") -> str:
        line = str(line)
        align = (align or "center").lower()
        visible = self._visible_len(line)
        if visible >= width:
            return line
        if align == "left":
            return line
        if align == "right":
            return " " * max(0, width - visible) + line
        left = max(0, (width - visible) // 2)
        return " " * left + line

    def _render_title_block(self, screen: ScreenDict) -> List[str]:
        title = str(screen.get("title", ""))
        style = str(self._screen_value(screen, "title_style", self.default_title_style or "banner")).lower()
        align = str(self._screen_value(screen, "title_align", self.default_title_align or "center")).lower()
        width = self._terminal_width()

        if not title:
            return []

        if style == "banner":
            banner_lines = render_banner(title).splitlines()
            max_len = max((len(line) for line in banner_lines), default=0)
            if max_len <= max(12, width - 4):
                return [self._align_line(line, width, align) for line in banner_lines]
            style = "rule"

        if style == "boxed":
            inner = f" {title} "
            border = "┌" + "─" * len(inner) + "┐"
            middle = "│" + inner + "│"
            bottom = "└" + "─" * len(inner) + "┘"
            return [
                self._align_line(border, width, align),
                self._align_line(middle, width, align),
                self._align_line(bottom, width, align),
            ]

        if style == "plain":
            return [self._align_line(title, width, align)]

        rule_len = min(max(8, len(title)), max(8, width - 4))
        return [
            self._align_line(title, width, align),
            self._align_line("─" * rule_len, width, align),
        ]

    def _render_utility_bar(self, screen: ScreenDict) -> List[str]:
        if self._screen_value(screen, "show_utility_bar", True) is False:
            return []
        width = self._terminal_width()
        utility = screen.get("utility_bar")
        if utility is None:
            text = time.strftime("%Y-%m-%d  %I:%M %p")
        else:
            try:
                value = self._call_option_callable(utility) if callable(utility) else utility
            except Exception as exc:
                self._set_error_status("Utility Bar Error", exc)
                value = ""
            if isinstance(value, (list, tuple)):
                text = "  |  ".join(str(v) for v in value if str(v).strip())
            else:
                text = str(value)
        text = text.strip()
        return [self._align_line(text, width, "center")] if text else []

    def _header_divider_line(self, width: int) -> str:
        # Keep the chrome dividers compact and matched across the screen.
        divider_len = min(24, max(16, width // 3))
        return self._align_line("." * divider_len, width, "center")

    def _capture_render_lines(self, spec: Any) -> List[str]:
        if spec is None:
            return []
        try:
            if callable(spec):
                capture = io.StringIO()
                with contextlib.redirect_stdout(capture):
                    spec(self)
                value = capture.getvalue()
            elif isinstance(spec, (list, tuple)):
                value = "\n".join(str(v) for v in spec)
            else:
                value = str(spec)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            self._set_error_status("Panel Render Error", exc)
            return []
        value = value.rstrip("\n")
        return value.splitlines() if value else []

    def _slice_visible(self, text: str, width: int) -> str:
        text = str(text)
        if width <= 0:
            return ""
        out: List[str] = []
        visible = 0
        i = 0
        while i < len(text) and visible < width:
            if text[i] == "":
                match = ANSI_RE.match(text, i)
                if match:
                    out.append(match.group(0))
                    i = match.end()
                    continue
            out.append(text[i])
            visible += 1
            i += 1
        return "".join(out)

    def _fit_panel_line(self, text: str, width: int) -> str:
        text = str(text)
        if width <= 0:
            return ""
        visible = self._visible_len(text)
        if visible <= width:
            return text + (" " * max(0, width - visible))
        if width <= 1:
            return self._slice_visible(text, width)
        return self._slice_visible(text, max(0, width - 1)) + "…"

    def _panel_box(self, lines: List[str], width: int, height: int, title: Optional[str] = None) -> List[str]:
        inner_w = max(4, width - 4)
        inner_h = max(1, height - 2)
        title_text = str(title).strip() if title else ""
        if title_text:
            shown = self._fit_panel_line(title_text, max(1, inner_w - 1)).rstrip()
            top = f"┌─ {shown}"
            fill = max(0, width - len(top) - 1)
            top = top + ("─" * fill) + "┐"
        else:
            top = "┌" + ("─" * (width - 2)) + "┐"
        out = [top]
        padded = list(lines[:inner_h]) + [""] * max(0, inner_h - len(lines))
        for line in padded:
            out.append("│ " + self._fit_panel_line(line, inner_w) + " │")
        out.append("└" + ("─" * (width - 2)) + "┘")
        return out

    def _render_canvas_panels(self, screen: ScreenDict, available_height: Optional[int] = None) -> List[str]:
        info_spec = screen.get("info_panel")
        main_spec = screen.get("main_panel")
        if info_spec is None and main_spec is None:
            return []

        width = self._terminal_width()
        gap = max(2, int(self._screen_value(screen, "panel_gap", 4) or 4))
        info_lines = self._capture_render_lines(info_spec)
        main_lines = self._capture_render_lines(main_spec)
        info_title = screen.get("info_title")
        main_title = screen.get("main_title")
        panel_mode = str(self._screen_value(screen, "panel_mode", "auto")).lower()
        if panel_mode not in {"auto", "split", "stack", "main_full", "info_full"}:
            panel_mode = "auto"

        panel_min_height = max(5, int(self._screen_value(screen, "panel_min_height", 6) or 6))
        panel_max_height = self._screen_value(screen, "panel_max_height", None)
        try:
            panel_max_height = int(panel_max_height) if panel_max_height is not None else None
        except Exception:
            panel_max_height = None
        explicit_panel_height = self._screen_value(screen, "panel_height", None)
        try:
            explicit_panel_height = int(explicit_panel_height) if explicit_panel_height is not None else None
        except Exception:
            explicit_panel_height = None
        available_height = max(panel_min_height, int(available_height)) if available_height else None

        def _final_height(content_lines: List[str], *, min_floor: int = panel_min_height, fill: bool = False) -> int:
            height = explicit_panel_height if explicit_panel_height is not None else max(min_floor, len(content_lines) + 2)
            if fill and available_height is not None:
                height = max(height, available_height)
            elif available_height is not None:
                height = min(height, available_height)
            if panel_max_height is not None:
                height = min(height, panel_max_height)
            return max(min_floor, height)

        if (bool(self._screen_value(screen, "main_panel_full", False)) and main_spec is not None) or panel_mode == "main_full":
            panel_width = max(24, width - 2)
            box = self._panel_box(main_lines, panel_width, _final_height(main_lines, min_floor=8, fill=True), main_title)
            return box

        if panel_mode == "info_full" and info_spec is not None:
            panel_width = max(24, width - 2)
            box = self._panel_box(info_lines, panel_width, _final_height(info_lines, min_floor=8, fill=True), info_title)
            return box

        if info_spec is not None and main_spec is not None:
            if panel_mode == "stack":
                panel_width = max(24, width - 2)
                info_box = self._panel_box(info_lines, panel_width, _final_height(info_lines), info_title)
                main_fill = explicit_panel_height is None and available_height is not None
                main_box = self._panel_box(main_lines, panel_width, _final_height(main_lines, min_floor=8, fill=main_fill), main_title)
                return info_box + [""] + main_box

            total_width = max(28, width - 2)
            info_width = self._screen_value(screen, "info_panel_width", None)
            if info_width is None:
                ratio = self._screen_value(screen, "info_panel_ratio", None)
                try:
                    ratio = float(ratio) if ratio is not None else 0.34
                except Exception:
                    ratio = 0.34
                ratio = min(0.7, max(0.2, ratio))
                info_width = int((total_width - gap) * ratio)
            info_width = max(22, min(int(info_width), max(22, total_width - 28)))
            main_width = total_width - gap - info_width

            if panel_mode == "auto" and main_width < 28:
                panel_width = max(24, width - 2)
                info_box = self._panel_box(info_lines, panel_width, _final_height(info_lines), info_title)
                main_box = self._panel_box(main_lines, panel_width, _final_height(main_lines, min_floor=8), main_title)
                return info_box + [""] + main_box

            panel_height = max(_final_height(info_lines), _final_height(main_lines, min_floor=8))
            left_box = self._panel_box(info_lines, info_width, panel_height, info_title)
            right_box = self._panel_box(main_lines, main_width, panel_height, main_title)
            return [left + (" " * gap) + right for left, right in zip(left_box, right_box)]

        only_lines = info_lines if info_spec is not None else main_lines
        only_title = info_title if info_spec is not None else main_title
        fill = bool(self._screen_value(screen, "main_panel_full", False)) or panel_mode in {"main_full", "info_full"}
        if fill:
            panel_width = max(24, width - 2)
        else:
            preferred_single_width = None
            if info_spec is not None and main_spec is None:
                preferred_single_width = self._screen_value(screen, "info_panel_width", None)
                if preferred_single_width is None:
                    preferred_ratio = self._screen_value(screen, "info_panel_ratio", None)
                    try:
                        preferred_ratio = float(preferred_ratio) if preferred_ratio is not None else None
                    except Exception:
                        preferred_ratio = None
                    if preferred_ratio is not None:
                        preferred_ratio = min(0.9, max(0.2, preferred_ratio))
                        preferred_single_width = int((width - 2) * preferred_ratio)
            elif main_spec is not None and info_spec is None:
                preferred_single_width = self._screen_value(screen, "main_panel_width", None)
            try:
                panel_width = int(preferred_single_width) if preferred_single_width is not None else None
            except Exception:
                panel_width = None
            if panel_width is None:
                panel_width = min(max(32, width - 8), width - 2)
            else:
                panel_width = max(24, min(panel_width, width - 2))
        box = self._panel_box(only_lines, panel_width, _final_height(only_lines, min_floor=8 if main_spec is not None else panel_min_height, fill=fill), only_title)
        if panel_width >= width - 2:
            return box
        pad = " " * max(0, (width - panel_width) // 2)
        return [pad + line for line in box]

    def _render_footer_hints(self, screen: ScreenDict) -> str:
        footer = screen.get("footer_text")
        if footer is not None:
            try:
                value = self._call_option_callable(footer) if callable(footer) else footer
            except Exception as exc:
                self._set_error_status("Footer Error", exc)
                value = ""
            return self._align_line(str(value), self._terminal_width(), "center")
        hints = ["[Arrows] Navigate", "[Enter] Select"]
        if screen["hotkeys"]:
            hints.append("[Hotkeys] Active")
        if self.current_screen != "main":
            hints.append("[H] Home")
        if self.screen_stack:
            hints.append("[Esc] Back")
        if screen.get("tick_interval"):
            hints.append(f"[Tick] {screen['tick_interval']}s")
        return self._align_line("  ".join(hints), self._terminal_width(), "center")

    def _main_options(self, screen: ScreenDict) -> List[Any]:
        return list(screen.get("options", []))

    def _main_actions(self, screen: ScreenDict) -> List[Any]:
        return list(screen.get("actions", []))

    def _shortcut_options(self, screen: ScreenDict) -> List[Any]:
        return list(screen.get("shortcut_options", []))

    def _shortcut_actions(self, screen: ScreenDict) -> List[Any]:
        return list(screen.get("shortcut_actions", []))

    def _nav_options(self, screen: ScreenDict) -> List[Any]:
        return list(screen.get("nav_options", []))

    def _nav_actions(self, screen: ScreenDict) -> List[Any]:
        return list(screen.get("nav_actions", []))

    def _option_records(self, screen: ScreenDict) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        for group, options, actions in (
            ("main", self._main_options(screen), self._main_actions(screen)),
            ("shortcut", self._shortcut_options(screen), self._shortcut_actions(screen)),
            ("nav", self._nav_options(screen), self._nav_actions(screen)),
        ):
            for option, action in zip(options, actions):
                records.append({"group": group, "option": option, "action": action})
        return records

    def _menu_rows(self, screen: ScreenDict) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        layout = self._menu_layout(screen)
        index = 0

        main_count = min(len(self._main_options(screen)), len(self._main_actions(screen)))
        if main_count:
            main_columns = int(screen.get("main_columns", 1) or 1)
            main_columns = max(1, main_columns)
            if layout == "horizontal":
                rows.append({"group": "main", "indices": list(range(index, index + main_count))})
            elif main_columns > 1:
                for start in range(0, main_count, main_columns):
                    row_indices = list(range(index + start, min(index + start + main_columns, index + main_count)))
                    rows.append({"group": "main", "indices": row_indices})
            else:
                for i in range(main_count):
                    rows.append({"group": "main", "indices": [index + i]})
        index += main_count

        shortcut_count = min(len(self._shortcut_options(screen)), len(self._shortcut_actions(screen)))
        if shortcut_count:
            rows.append({"group": "shortcut", "indices": list(range(index, index + shortcut_count))})
        index += shortcut_count

        nav_count = min(len(self._nav_options(screen)), len(self._nav_actions(screen)))
        if nav_count:
            rows.append({"group": "nav", "indices": list(range(index, index + nav_count))})
        return rows

    def _total_option_count(self, screen: ScreenDict) -> int:
        return len(self._option_records(screen))

    def _action_for_selected_index(self, screen: ScreenDict, index: int) -> Any:
        records = self._option_records(screen)
        if 0 <= index < len(records):
            return records[index]["action"]
        raise IndexError("Selected index out of range")

    def _render_menu_rows(self, screen: ScreenDict) -> List[str]:
        width = self._terminal_width()
        align = self._menu_align(screen)
        records = self._option_records(screen)
        rows = self._menu_rows(screen)
        lines: List[str] = []
        try:
            gap = int(screen.get("menu_box_gap", 4) or 4)
        except Exception:
            gap = 4
        gap = max(1, gap)
        try:
            row_gap = int(screen.get("menu_row_gap", 1) or 0)
        except Exception:
            row_gap = 1
        row_gap = max(0, row_gap)

        for row_num, row in enumerate(rows):
            indices = row["indices"]
            group = row["group"]
            title_value = screen.get(f"{group}_menu_title")
            if title_value is None:
                if group == "main":
                    title_value = screen.get("main_options_title")
                else:
                    title_value = screen.get(f"{group}_title")
            if title_value:
                try:
                    title_text = self._call_option_callable(title_value) if callable(title_value) else title_value
                except Exception as exc:
                    self._set_error_status("Title Error", exc)
                    title_text = ""
                if title_text:
                    lines.append(self._align_line(str(title_text), width, "center"))
            boxes: List[List[str]] = []
            for idx in indices:
                option_text = self._resolve_option_text(records[idx]["option"])
                boxes.append(self._box_lines(option_text, selected=(idx == self.selected_index)))

            use_center_seam = bool(screen.get("menu_center_seam", False))
            if use_center_seam and group == "main" and len(boxes) == 2:
                left_visible = self._visible_len(boxes[0][0])
                right_visible = self._visible_len(boxes[1][0])
                center = width // 2
                left_end = center - ((gap + 1) // 2)
                right_start = center + (gap // 2)
                left_pad = max(0, left_end - left_visible)
                between = max(1, right_start - (left_pad + left_visible))
                for line_index in range(3):
                    lines.append((" " * left_pad) + boxes[0][line_index] + (" " * between) + boxes[1][line_index])
            else:
                visible_row_width = sum(self._visible_len(box[0]) for box in boxes) + gap * max(0, len(boxes) - 1)
                row_align = "center" if group in {"shortcut", "nav"} else align
                if row_align == "center":
                    left_pad = max(0, (width - visible_row_width) // 2)
                elif row_align == "right":
                    left_pad = max(0, width - visible_row_width)
                else:
                    left_pad = 0
                pad = " " * left_pad

                for line_index in range(3):
                    joined = (" " * gap).join(box[line_index] for box in boxes)
                    lines.append(pad + joined)

            if row_num != len(rows) - 1:
                for _ in range(row_gap):
                    lines.append("")
        return lines

    def _selection_position(self, rows: List[Dict[str, Any]], index: int) -> tuple[int, int]:
        for row_idx, row in enumerate(rows):
            indices = row["indices"]
            if index in indices:
                return row_idx, indices.index(index)
        return 0, 0
    def set_status(self, message: str) -> None:
        self.status_msg = str(message)
        self._needs_render = True

    def save_data(self) -> None:
        directory = os.path.dirname(os.path.abspath(self.data_file))
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
        temp_path = f"{self.data_file}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as handle:
                json.dump(self.app_data, handle, indent=4, ensure_ascii=False)
            os.replace(temp_path, self.data_file)
            self.status_msg = "Saved."
            self._needs_render = True
        except Exception as exc:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass
            self.status_msg = f"Save Error: {exc}"
            self._needs_render = True

    def load_data(self) -> None:
        if not os.path.exists(self.data_file):
            self.app_data = {}
            self.status_msg = ""
            self._needs_render = True
            return
        try:
            with open(self.data_file, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            self.app_data = loaded if isinstance(loaded, dict) else {}
            self.status_msg = ""
            self._needs_render = True
        except Exception as exc:
            self.app_data = {}
            self.status_msg = f"Data reset: {exc}"
            self._needs_render = True

    def get_screen(self, name: Optional[str] = None) -> Optional[ScreenDict]:
        screen = self.screens.get(name or self.current_screen)
        if screen is None:
            return None
        screen.setdefault("screen_type", self.default_screen_type)
        return screen

    def _set_error_status(self, prefix: str, exc: Exception) -> None:
        self.set_status(f"{prefix}: {type(exc).__name__}: {exc}")

    def _call_hook(self, hook: Optional[Hook], *args: Any, hook_name: str = "Hook Error") -> Any:
        if not callable(hook):
            return None
        try:
            return hook(self, *args)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            self._set_error_status(hook_name, exc)
            return None

    def _call_option_callable(self, option: Callable[..., Any]) -> Any:
        try:
            signature = inspect.signature(option)
        except (TypeError, ValueError):
            return option(self)

        params = list(signature.parameters.values())
        has_varargs = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in params)
        positional = [
            p for p in params
            if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        required = [p for p in positional if p.default is inspect.Parameter.empty]
        if has_varargs or required:
            return option(self)
        return option()

    def _resolve_option_text(self, option: Any) -> str:
        if callable(option):
            try:
                return str(self._call_option_callable(option))
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                self._set_error_status("Option Render Error", exc)
                return "<option error>"
        return str(option)

    def set_screen(
        self,
        target: str,
        *,
        push_history: bool = True,
        reset_selection: bool = True,
    ) -> None:
        if target not in self.screens:
            self.set_status(f"Unknown screen: {target}")
            return

        previous = self.current_screen
        if previous == target:
            self._needs_render = True
            return
        if previous in self.screens:
            self.selection_memory[previous] = self.selected_index
            self._call_hook(self.screens[previous].get("on_exit"), target, hook_name="Screen Exit Error")
        if push_history and previous != target:
            self.screen_stack.append(previous)

        self.current_screen = target
        if reset_selection:
            remembered = self.selection_memory.get(target, 0)
            option_count = self._total_option_count(self.screens[target])
            self.selected_index = max(0, min(remembered, option_count - 1)) if option_count else 0

        self._call_hook(self.screens[target].get("on_enter"), previous, hook_name="Screen Enter Error")
        self._needs_render = True

    def go_back(self) -> None:
        if not self.screen_stack:
            self.set_status("No previous screen.")
            return
        previous = self.screen_stack.pop()
        self.set_screen(previous, push_history=False)
        self._needs_render = True

    def get_form_field(self, screen_name: Optional[str], field_key: str) -> Optional[FormField]:
        screen = self.get_screen(screen_name)
        if not screen:
            return None
        return screen.get("form_fields", {}).get(field_key)

    def get_form_field_label(self, screen_name: str, field_key: str) -> str:
        field = self.get_form_field(screen_name, field_key)
        if not field:
            return f"Missing field: {field_key}"
        value = self.app_data.get(field.key)
        return f"{field.label}: {field.display_value(value)}"

    def edit_form_field(self, field_key: str, *, screen_name: Optional[str] = None) -> Optional[Any]:
        field = self.get_form_field(screen_name, field_key)
        if not field:
            self.set_status(f"Unknown form field: {field_key}")
            return None

        raw_value = self.prompt_text(field.build_prompt(), title=field.label, allow_empty=field.allow_empty)
        if raw_value is None:
            self.set_status("Input canceled.")
            return None
        if raw_value == "" and not field.allow_empty:
            self.set_status(f"{field.label} cannot be empty.")
            return None

        parsed_value: Any = field.empty_value if raw_value == "" else raw_value
        if raw_value != "" and callable(field.parser):
            try:
                parsed_value = field.parser(raw_value)
            except Exception as exc:
                self.set_status(f"Invalid {field.label}: {exc}")
                return None

        if callable(field.validator):
            verdict = field.validator(parsed_value)
            if verdict is False:
                self.set_status(f"Invalid {field.label}.")
                return None
            if isinstance(verdict, str):
                self.set_status(verdict)
                return None

        self.app_data[field.key] = parsed_value
        self.status_msg = field.status_template.format(
            value=parsed_value,
            key=field.key,
            label=field.label,
        )

        screen = self.get_screen(screen_name)
        if screen:
            self._call_hook(screen.get("on_input"), parsed_value, field.key, hook_name="Input Hook Error")
        self._needs_render = True
        return parsed_value

    def _input_visible_text(self, text: str, cursor: int, width: int) -> str:
        text = str(text)
        cursor = max(0, min(int(cursor), len(text)))
        width = max(8, int(width))
        max_visible = max(1, width - 1)
        start = 0
        if len(text) > max_visible:
            start = max(0, cursor - max_visible + 1)
        visible = text[start:start + max_visible]
        cursor_in_visible = cursor - start
        if self._ansi_enabled:
            if cursor_in_visible < len(visible):
                ch = visible[cursor_in_visible]
                visible = visible[:cursor_in_visible] + "[7m" + ch + "[0m" + visible[cursor_in_visible + 1:]
            else:
                visible = visible + "[7m [0m"
        else:
            if cursor_in_visible < len(visible):
                visible = visible[:cursor_in_visible] + "_" + visible[cursor_in_visible:]
            else:
                visible = visible + "_"
        return visible

    def _multiline_wrap_cursor(self, col: int, width: int) -> tuple[int, int]:
        width = max(1, int(width))
        col = max(0, int(col))
        if col == 0:
            return 0, 0
        if col % width == 0:
            return max(0, (col // width) - 1), width
        return col // width, col % width

    def _multiline_hard_wrap(
        self,
        lines: List[str],
        row: int,
        col: int,
        width: int,
        *,
        cursor_wrap_at_boundary: bool = False,
    ) -> tuple[List[str], int, int]:
        width = max(1, int(width))
        source_lines = [str(line) for line in (lines or [""])]
        if not source_lines:
            source_lines = [""]

        row = max(0, min(int(row), len(source_lines) - 1))
        col = max(0, min(int(col), len(source_lines[row])))

        wrapped: List[str] = []
        new_row = 0
        new_col = 0

        for src_index, line in enumerate(source_lines):
            chunks = [line[i:i + width] for i in range(0, len(line), width)] or [""]
            if src_index == row:
                if cursor_wrap_at_boundary and col > 0 and col % width == 0:
                    row_offset = col // width
                    col_value = 0
                else:
                    row_offset, col_value = self._multiline_wrap_cursor(col, width)
                if row_offset >= len(chunks):
                    chunks.extend([""] * (row_offset - len(chunks) + 1))
                base_index = len(wrapped)
                wrapped.extend(chunks)
                row_offset = max(0, min(row_offset, len(chunks) - 1))
                new_row = base_index + row_offset
                new_col = max(0, min(col_value, len(wrapped[new_row])))
            else:
                wrapped.extend(chunks)

        if not wrapped:
            wrapped = [""]
            new_row = 0
            new_col = 0

        return wrapped, new_row, new_col

    def _render_input_overlay(self, width: int) -> List[str]:
        session = self._input_session
        if not session:
            return []
        prompt = str(session.get("prompt") or "")
        title = str(session.get("title") or "INPUT")
        text = str(session.get("text") or "")
        cursor = int(session.get("cursor") or 0)
        max_box = max(24, min(max(24, width // 2), 40))
        max_box = min(max_box, max(24, width - 4))
        inner = max(12, max_box - 4)
        prompt_lines = [prompt[i:i + inner] for i in range(0, len(prompt), inner)] or [""]
        prompt_lines = prompt_lines[:2]
        value_line = self._input_visible_text(text, cursor, inner)
        helper = "Enter=OK  Esc=Cancel"
        box_lines = prompt_lines + [value_line, helper]
        box_height = len(box_lines) + 2
        box = self._panel_box(box_lines, max_box, box_height, title=title)
        rendered: List[str] = []
        for line in box:
            pad = max(0, (width - self._visible_len(line)) // 2)
            rendered.append((" " * pad) + line)
        return rendered

    def _run_input_session(self) -> Optional[str]:
        self._needs_render = True
        while self.running and self._input_session is not None:
            self.render()
            key = self.input_handler.get_key()
            if not key:
                continue
            session = self._input_session
            if session is None:
                break
            text = str(session.get("text") or "")
            cursor = max(0, min(int(session.get("cursor") or 0), len(text)))
            if key == "ESC":
                self._input_session = None
                self._needs_render = True
                return None
            if key == "ENTER":
                result = text
                self._input_session = None
                self._needs_render = True
                return result
            if key == "BACKSPACE":
                if cursor > 0:
                    text = text[:cursor - 1] + text[cursor:]
                    cursor -= 1
            elif key == "LEFT":
                cursor = max(0, cursor - 1)
            elif key == "RIGHT":
                cursor = min(len(text), cursor + 1)
            elif key in {"UP", "DOWN"}:
                continue
            elif isinstance(key, str) and len(key) == 1 and key >= " ":
                max_length = session.get("max_length")
                if not isinstance(max_length, int) or max_length < 0 or len(text) < max_length:
                    text = text[:cursor] + key + text[cursor:]
                    cursor += 1
            session["text"] = text
            session["cursor"] = cursor
            self._needs_render = True
        return None

    def prompt_text(
        self,
        prompt: str,
        *,
        title: str = "INPUT",
        initial: str = "",
        allow_empty: bool = True,
        max_length: Optional[int] = None,
    ) -> Optional[str]:
        initial_text = str(initial or "")
        if isinstance(max_length, int) and max_length >= 0:
            initial_text = initial_text[:max_length]
        self._input_session = {
            "title": title,
            "prompt": prompt,
            "text": initial_text,
            "cursor": len(initial_text),
            "max_length": max_length,
        }
        self._needs_render = True
        result = self._run_input_session()
        if result is None:
            self.status_msg = "Input canceled."
            return None
        if result == "" and not allow_empty:
            self.status_msg = "Input canceled."
            return None
        return result

    def prompt_input(
        self,
        *,
        prompt: str = "Enter value: ",
        target_key: str = "last_input",
        return_to: Optional[str] = None,
        allow_empty: bool = True,
        status_template: str = "Saved: {value}",
    ) -> Optional[str]:
        value = self.prompt_text(prompt, title="INPUT", allow_empty=allow_empty)
        if value is None:
            self.status_msg = "Input canceled."
        elif value or allow_empty:
            self.app_data[target_key] = value
            self.status_msg = status_template.format(value=value, key=target_key)
            screen = self.get_screen()
            if screen:
                self._call_hook(screen.get("on_input"), value, target_key, hook_name="Input Hook Error")
        else:
            self.status_msg = "Input canceled."
        if return_to:
            self.set_screen(return_to, push_history=False)
        self._needs_render = True
        return value

    def open_confirm_dialog(
        self,
        *,
        title: str = "Confirm",
        message: str = "Are you sure?",
        on_yes: Any = None,
        on_no: Any = None,
        yes_label: str = "Yes",
        no_label: str = "No",
    ) -> str:
        self._temp_screen_counter += 1
        name = f"__confirm_{self._temp_screen_counter}"

        def render_confirm(app: "TerminalApp") -> None:
            width = app._terminal_width()
            for line in str(message).splitlines() or [""]:
                print(app._align_line(line, width, "center"))

        def cleanup_temp_screen(app: "TerminalApp", target: str) -> None:
            if target != name:
                app.screens.pop(name, None)

        def finish(choice_action: Any) -> Hook:
            def _finish(app: "TerminalApp") -> Any:
                if app.current_screen == name:
                    app.go_back()
                return choice_action

            return _finish

        yes_action = finish(on_yes)
        no_action = finish(on_no)
        self.add_screen(
            name=name,
            title=title,
            options=[yes_label, no_label],
            actions=[yes_action, no_action],
            on_render=render_confirm,
            on_exit=cleanup_temp_screen,
            hotkeys={"y": yes_action, "n": no_action},
            title_style="rule",
            screen_type="hub",
            menu_layout="horizontal",
            menu_align="center",
        )
        self.set_screen(name)
        return name

    def _render_vertical_menu(self, screen: ScreenDict) -> List[str]:
        return self._render_menu_rows(screen)

    def _render_horizontal_menu(self, screen: ScreenDict) -> List[str]:
        return self._render_menu_rows(screen)
    def _build_frame(self) -> str:
        screen = self.get_screen()
        if not screen:
            self.running = False
            return "Error: Screen not found\n"

        width = self._terminal_width()
        height = self._terminal_height()
        lines: List[str] = []

        # Top chrome: breathing room + centered dotted divider above the title.
        lines.append("")
        lines.append(self._header_divider_line(width))
        lines.append("")

        title_lines = self._render_title_block(screen)
        if title_lines:
            lines.extend(title_lines)

        utility_lines = self._render_utility_bar(screen)
        if utility_lines:
            if lines:
                lines.append("")
            lines.extend(utility_lines)

        # Matched bottom chrome divider under the title/utility block on every page.
        if lines:
            lines.append("")
            lines.append(self._header_divider_line(width))

        footer_status_line = ""
        if self.status_msg and bool(screen.get("status_near_footer", False)):
            status_text = str(self.status_msg).strip().splitlines()[0]
            if status_text:
                if self._visible_len(status_text) > max(8, width - 4):
                    status_text = self._trim_visible(status_text, max(8, width - 4))
                footer_status_line = self._align_line(status_text, width, "center")

        hide_menu = bool(screen.get("hide_menu")) or self._interaction_mode(screen) in {"typing", "editor", "input", "text"}
        if hide_menu:
            menu_lines = []
        elif self._total_option_count(screen) == 0:
            menu_lines = [self._align_line("(No options on this screen)", width, "center")]
        else:
            layout = self._menu_layout(screen)
            if layout == "horizontal":
                menu_lines = self._render_horizontal_menu(screen)
            else:
                menu_lines = self._render_vertical_menu(screen)

        footer = self._render_footer_hints(screen)
        reserved = len(lines)
        if lines:
            reserved += 1
        if menu_lines:
            reserved += len(menu_lines) + 1
        if footer:
            reserved += 1
        available_panel_height = max(6, height - reserved - 1)

        panel_lines = self._render_canvas_panels(screen, available_height=available_panel_height)
        if panel_lines:
            if lines:
                lines.append("")
            lines.extend(panel_lines)
        elif callable(screen.get("on_render")):
            if lines:
                lines.append("")
            capture = io.StringIO()
            with contextlib.redirect_stdout(capture):
                screen["on_render"](self)
            hook_output = capture.getvalue().rstrip("\n")
            if hook_output:
                lines.extend(hook_output.splitlines())

        if lines:
            lines.append("")
        lines.extend(menu_lines)

        overlay_lines = self._render_input_overlay(width)
        content_limit = max(1, height - (1 if footer else 0))
        if overlay_lines:
            while len(lines) < content_limit:
                lines.append("")
            overlay_top = max(0, content_limit - len(overlay_lines))
            for idx, overlay_line in enumerate(overlay_lines):
                line_index = overlay_top + idx
                if 0 <= line_index < content_limit:
                    lines[line_index] = overlay_line

        lines = lines[:content_limit]
        if footer_status_line:
            while len(lines) < content_limit:
                lines.append("")
            if content_limit > 0:
                lines[content_limit - 1] = footer_status_line
        if footer:
            while len(lines) < max(0, height - 1):
                lines.append("")
            lines.append(footer)
        return "\n".join(lines) + "\n"

    def render(self) -> None:
        if not self._needs_render and self._interactive_stdout:
            return

        frame = self._build_frame()
        if frame == self._last_frame:
            self._needs_render = False
            return
        if not self._interactive_stdout:
            print(frame, end="")
            self._last_frame = frame
            self._needs_render = False
            return
        if self._ansi_enabled:
            sys.stdout.write("[H[J")
            sys.stdout.write(frame)
            sys.stdout.flush()
        else:
            self.clear()
            print(frame, end="")
        self._last_frame = frame
        self._needs_render = False

    def _handle_action_dict(self, action: Dict[str, Any]) -> Any:
        action_type = action.get("type")
        if action_type == "goto":
            target = action.get("screen")
            if not target:
                self.set_status("Goto action missing screen.")
                return None
            self.set_screen(str(target), push_history=action.get("push_history", True))
            return None
        if action_type == "input":
            return self.prompt_input(
                prompt=action.get("prompt", "Enter value: "),
                target_key=action.get("target", "last_input"),
                return_to=action.get("return_to"),
                allow_empty=action.get("allow_empty", True),
                status_template=action.get("status_template", "Saved: {value}"),
            )
        if action_type == "form_field":
            field_key = action.get("field")
            if not field_key:
                self.set_status("Form field action missing field key.")
                return None
            return self.edit_form_field(str(field_key))
        if action_type == "confirm":
            self.open_confirm_dialog(
                title=action.get("title", "Confirm"),
                message=action.get("message", "Are you sure?"),
                on_yes=action.get("on_yes"),
                on_no=action.get("on_no"),
                yes_label=action.get("yes_label", "Yes"),
                no_label=action.get("no_label", "No"),
            )
            return None
        if action_type == "chain":
            for sub_action in action.get("actions", []):
                self.handle_action(sub_action)
                if not self.running:
                    break
            return None
        if action_type == "set_value":
            key = action.get("key")
            if key is None:
                self.set_status("Set-value action missing key.")
                return None
            value = action.get("value")
            self.app_data[str(key)] = value
            self.set_status(action.get("status_template", "{key} set to {value}").format(key=key, value=value))
            return value
        if action_type == "back":
            self.go_back()
            return None
        if action_type == "save":
            self.save_data()
            return None
        if action_type == "status":
            self.set_status(action.get("message", ""))
            return None
        if action_type == "exit":
            self.save_data()
            self.running = False
            return None
        if action_type == "function":
            func = action.get("callable")
            if not callable(func):
                self.set_status("Function action missing callable.")
                return None
            return func(self)
        if action_type == "noop":
            return None
        self.set_status(f"Unknown action type: {action_type}")
        return None

    def handle_action(self, action: ActionType) -> None:
        screen = self.get_screen()
        if screen:
            self._call_hook(screen.get("on_action"), action, hook_name="Action Hook Error")
        self.last_action = action

        if action == "exit":
            self.save_data()
            self.running = False
            return
        if action == "back":
            self.go_back()
            return
        if action == "save":
            self.save_data()
            return
        if isinstance(action, dict):
            try:
                result = self._handle_action_dict(action)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                self._set_error_status("Action Error", exc)
                return
            if result is not None and result is not action:
                self.handle_action(result)
            return
        if isinstance(action, str):
            if action == "input_mode":
                self.prompt_input(return_to=self.current_screen)
                return
            if action == "home":
                self.set_screen("main", push_history=False)
                return
            if action in self.screens:
                self.set_screen(action)
                return
            self.set_status(f"Invalid Action: {action}")
            return
        if callable(action):
            try:
                result = action(self)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                self._set_error_status("Action Error", exc)
                return
            if result is not None and result is not action:
                self.handle_action(result)
            return
        self.set_status("Invalid Action")

    def handle_key(self, key: str) -> None:
        self.last_key = key
        if self._input_session is not None:
            return
        screen = self.get_screen()
        if not screen:
            self.running = False
            return

        interaction_mode = self._interaction_mode(screen)
        if interaction_mode in {"typing", "editor", "input", "text"}:
            handled = self._dispatch_screen_key(screen, key)
            if handled is not False:
                self._needs_render = True
                return
            if key == "ESC" and self.screen_stack:
                self.go_back()
                self._needs_render = True
            return

        handled = self._dispatch_screen_key(screen, key)
        if handled:
            self._needs_render = True
            return

        hotkey_action = screen["hotkeys"].get(key)
        if hotkey_action is not None:
            self.handle_action(hotkey_action)
            self._needs_render = True
            return

        if key == "ESC" and self.screen_stack:
            self.go_back()
            self._needs_render = True
            return

        option_count = self._total_option_count(screen)
        if option_count == 0:
            return

        self.selected_index = max(0, min(self.selected_index, option_count - 1))
        rows = self._menu_rows(screen)
        if not rows:
            return

        row_idx, col_idx = self._selection_position(rows, self.selected_index)

        if key == "LEFT":
            current = rows[row_idx]["indices"]
            if len(current) > 1:
                col_idx = (col_idx - 1) % len(current)
                self.selected_index = current[col_idx]
                self._needs_render = True
            return

        if key == "RIGHT":
            current = rows[row_idx]["indices"]
            if len(current) > 1:
                col_idx = (col_idx + 1) % len(current)
                self.selected_index = current[col_idx]
                self._needs_render = True
            return

        if key == "UP":
            row_idx = (row_idx - 1) % len(rows)
            target = rows[row_idx]["indices"]
            self.selected_index = target[min(col_idx, len(target) - 1)]
            self._needs_render = True
            return

        if key == "DOWN":
            row_idx = (row_idx + 1) % len(rows)
            target = rows[row_idx]["indices"]
            self.selected_index = target[min(col_idx, len(target) - 1)]
            self._needs_render = True
            return

        if key == "ENTER":
            action = self._action_for_selected_index(screen, self.selected_index)
            self.handle_action(action)
            self._needs_render = True
    def run(self) -> None:
        if self.current_screen in self.screens:
            self._call_hook(self.screens[self.current_screen].get("on_enter"), None, hook_name="Screen Enter Error")
        try:
            self.input_handler.enter_raw()
        except RuntimeError as exc:
            self.set_status(str(exc))
            self.render()
            print("App Closed.")
            return
        try:
            while self.running:
                self.render()
                screen = self.get_screen()
                if not screen:
                    self.running = False
                    break
                interval = screen.get("tick_interval")
                key = self.input_handler.get_key(timeout=interval if interval is not None else None)
                if key:
                    self.handle_key(key)
                    continue
                if interval is not None and self.running:
                    result = self._call_hook(screen.get("on_tick"), interval, hook_name="Tick Hook Error")
                    if result is not None:
                        self.handle_action(result)
        except KeyboardInterrupt:
            self.save_data()
        finally:
            self.input_handler.exit_raw()
            self.clear()
            print("App Closed.")
