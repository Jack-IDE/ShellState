"""Shell navigation normalization and screen typing."""

from shellstate.core.engine import A


def _configure_settings_screen(app) -> None:
    screen = app.screens.get("settings")
    if not screen:
        return
    screen["options"] = ["Speed Dials", "Home Image", "Export Center", "System", "Exit", "Back"]
    screen["actions"] = ["speed_dials", "home_image", "saves", "system", A.exit(), "back"]
    screen.setdefault("hotkeys", {})
    screen["hotkeys"].update({"d": "speed_dials", "m": "home_image", "v": "saves", "i": "system", "q": A.exit()})



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
        hotkeys = screen.setdefault("hotkeys", {})
        if name == "graphics_lab":
            screen["nav_options"] = []
            screen["nav_actions"] = []
            hotkeys.setdefault("b", "back")
            continue
        screen["nav_options"] = ["Home", "Back"]
        screen["nav_actions"] = ["home", "back"]
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
        if name != "graphics_lab":
            for key in ("title_style", "title_align", "menu_layout", "menu_align", "show_utility_bar"):
                if key in screen:
                    screen[key] = None

        if name == "calculator":
            for key in ("panel_mode", "info_panel_ratio", "panel_min_height"):
                if key in screen:
                    screen[key] = None
