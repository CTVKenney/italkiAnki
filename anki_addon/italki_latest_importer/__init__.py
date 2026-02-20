from __future__ import annotations

from pathlib import Path

from .shared import AddonConfig, copy_audio_files, planned_import_targets, resolve_output_paths, split_existing_targets


def _show_info(message: str) -> None:
    from aqt.utils import showInfo

    showInfo(message)


def _show_warning(message: str) -> None:
    from aqt.utils import showWarning

    showWarning(message)


def _import_csv(mw, path: Path) -> None:
    import aqt.importing as importing

    if hasattr(importing, "import_file"):
        importing.import_file(mw, str(path))
        return
    if hasattr(importing, "importFile"):
        importing.importFile(mw, str(path))
        return
    raise RuntimeError("Unable to find a compatible Anki CSV import function")


def _import_latest_cards() -> None:
    from aqt import mw

    if getattr(mw, "col", None) is None:
        _show_warning("Open an Anki profile/collection first.")
        return

    config = AddonConfig.from_dict(mw.addonManager.getConfig(__name__))
    paths = resolve_output_paths(config)
    planned = planned_import_targets(config, paths)
    existing, missing = split_existing_targets(planned)

    copied_audio = 0
    if config.copy_audio:
        media_dir = Path(mw.col.media.dir())
        copied_audio = copy_audio_files(paths.audio_dir, media_dir)

    if not existing:
        details = [f"No importable CSV files found in {paths.base_dir}."]
        if missing:
            details.extend(f"- missing {label}: {path.name}" for label, path in missing)
        if config.copy_audio:
            details.append(f"Copied {copied_audio} audio file(s).")
        _show_warning("\n".join(details))
        return

    imported_count = 0
    for _, path in existing:
        _import_csv(mw, path)
        imported_count += 1

    details = [f"Started import for {imported_count} file(s)."]
    if copied_audio:
        details.append(f"Copied {copied_audio} audio file(s) into Anki media.")
    if missing:
        details.extend(f"Skipped missing {label}: {path.name}" for label, path in missing)
    _show_info("\n".join(details))


def _register_menu_action() -> None:
    from aqt import mw
    from aqt.qt import QAction

    action = QAction("Import Latest italki Cards", mw)
    action.triggered.connect(_import_latest_cards)
    mw.form.menuTools.addAction(action)


try:
    _register_menu_action()
except Exception:
    # Allows importing helper modules in non-Anki environments (tests/tooling).
    pass
