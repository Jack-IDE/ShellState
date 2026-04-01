"""ShellState OS boot/composition module."""

from shellstate.runtime_model import app, _ensure_runtime_dirs, _init_defaults, SNAPSHOT_BASE
from shellstate.tlb_patch import attach_memory_manager

# Import built-in app modules for screen registration side effects.
from shellstate.apps import calculator  # noqa: F401
from shellstate.apps import notes  # noqa: F401
from shellstate.apps import converter  # noqa: F401
from shellstate.apps import program_maker  # noqa: F401
from shellstate.apps import export_center  # noqa: F401
from shellstate.apps import shell_ui  # noqa: F401


def main() -> None:
    _ensure_runtime_dirs()
    _init_defaults(app)
    attach_memory_manager(app, snapshot_base=SNAPSHOT_BASE)
    app.run()


if __name__ == "__main__":
    main()
