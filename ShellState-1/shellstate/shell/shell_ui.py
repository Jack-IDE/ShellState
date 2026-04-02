"""Shared shell hubs, speed dials, and home screen wiring."""

from shellstate.apps.speed_dials import register_speed_dials_screen
from shellstate.shell.home import _configure_home_screen
from shellstate.shell.navigation import _apply_screen_types, _configure_settings_screen, _normalize_navigation
from shellstate.shell.screens import register_shell_screens


def _finalize_shell_ui(app) -> None:
    _configure_settings_screen(app)
    _configure_home_screen(app)
    _normalize_navigation(app)
    _apply_screen_types(app)


def register_shell_ui(app) -> None:
    register_shell_screens(app)
    register_speed_dials_screen(app)
    _finalize_shell_ui(app)
