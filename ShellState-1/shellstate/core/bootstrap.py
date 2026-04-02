"""ShellState OS boot/composition module."""

from shellstate.apps.calculator import register_calculator_screen
from shellstate.apps.converter import register_converter_screens
from shellstate.apps.export_center import register_export_center_screens
from shellstate.apps.graphics_lab import register_graphics_lab_screen
from shellstate.apps.home_image import register_home_image_screen
from shellstate.apps.notes import register_notes_screens
from shellstate.apps.program_maker import register_program_maker_screens
from shellstate.core.runtime_model import SNAPSHOT_BASE, _ensure_runtime_dirs, _init_defaults, app
from shellstate.core.tlb_patch import attach_memory_manager
from shellstate.shell.shell_ui import register_shell_ui


def _register_builtin_screens(app) -> None:
    register_calculator_screen(app)
    register_converter_screens(app)
    register_notes_screens(app)
    register_program_maker_screens(app)
    register_export_center_screens(app)
    register_graphics_lab_screen(app)
    register_home_image_screen(app)
    register_shell_ui(app)


def build_app(*, attach_memory: bool = True):
    """Prepare and return the shared ShellState app instance."""
    _ensure_runtime_dirs()
    _init_defaults(app)
    if not getattr(app, '_shellstate_screens_registered', False):
        _register_builtin_screens(app)
        setattr(app, '_shellstate_screens_registered', True)
    if attach_memory and not getattr(app, '_shellstate_memory_attached', False):
        attach_memory_manager(app, snapshot_base=SNAPSHOT_BASE)
        setattr(app, '_shellstate_memory_attached', True)
    return app


def main() -> None:
    build_app()
    app.run()


if __name__ == '__main__':
    main()
