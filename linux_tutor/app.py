"""Application entry point (GUI)."""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import sys

from . import APP_NAME, __version__, paths


def setup_logging(verbose: bool = False) -> None:
    paths.ensure_user_dirs()
    handlers: list[logging.Handler] = [logging.handlers.RotatingFileHandler(
        paths.log_file(), maxBytes=1_000_000, backupCount=3)]
    if verbose:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="linux-tutor", description=f"{APP_NAME} - learn Linux hands-on")
    ap.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    ap.add_argument("--profile", help="open this profile (username) directly")
    ap.add_argument("--verbose", action="store_true", help="log to the console as well")
    ap.add_argument("--check", action="store_true",
                    help="check the installation (curriculum, database, podman, lab image) and exit")
    args = ap.parse_args(argv)
    setup_logging(args.verbose)

    if args.check:
        from .cli import check_installation
        return check_installation()

    from .ui.qt import QApplication, QMessageBox

    from .config import Config
    from .curriculum.loader import CurriculumError, load_curriculum
    from .assessment.checks import load_plugins
    from .progress.store import ProgressStore
    from .ui.dialogs import ProfileDialog
    from .ui.main_window import MainWindow
    from .ui.theme import apply_theme

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("linux-tutor")
    config = Config()
    apply_theme(app, config.get("ui.theme"), int(config.get("ui.font_size")))

    try:
        cur_dir = paths.curriculum_dir()
        load_plugins([paths.user_data_dir() / "plugins", cur_dir / "plugins"])
        cur = load_curriculum(cur_dir)
    except (CurriculumError, FileNotFoundError) as exc:
        QMessageBox.critical(None, APP_NAME, f"The curriculum could not be loaded:\n\n{exc}")
        return 1

    store = ProgressStore(paths.database_file())
    profile = None
    if args.profile:
        profile = next((p for p in store.profiles() if p.username == args.profile), None)
    while True:
        if profile is None:
            dlg = ProfileDialog(store)
            if not dlg.exec() or not dlg.selected:
                return 0
            profile = dlg.selected
        win = MainWindow(config, cur, store, profile)
        win.show()
        app.exec()
        nxt = getattr(win, "_switch_to", None)
        restore = getattr(win, "_restore_from", None)
        win.deleteLater()
        if restore:
            store.close()
            ProgressStore.restore(restore, paths.database_file())
            return 0
        if not nxt:
            store.close()
            return 0
        profile = nxt


if __name__ == "__main__":
    sys.exit(main())
