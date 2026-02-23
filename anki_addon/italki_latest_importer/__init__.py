from __future__ import annotations

from pathlib import Path

from .shared import (
    AddonConfig,
    append_deleted_keys,
    append_managed_note_ids,
    collect_imported_note_ids_by_key,
    copy_audio_files,
    dedupe_import_rows,
    existing_key_index,
    filter_rows_by_import_mode,
    filter_rows_by_deleted_keys,
    keys_for_note_ids,
    load_deleted_keys,
    managed_key_index,
    read_data_rows,
    remove_managed_note_ids,
    remove_note_ids,
    planned_import_targets,
    resolve_output_paths,
    split_existing_targets,
    write_import_rows,
)

_SUPPRESS_DELETE_TRACKING = 0


def _show_info(message: str) -> None:
    from aqt.utils import showInfo

    showInfo(message)


def _show_warning(message: str) -> None:
    from aqt.utils import showWarning

    showWarning(message)


def _show_status(message: str) -> None:
    try:
        from aqt.utils import tooltip

        tooltip(message)
    except Exception:
        _show_info(message)


def _import_csv(mw, path: Path) -> None:
    import aqt.importing as importing

    if hasattr(importing, "import_file"):
        importing.import_file(mw, str(path))
        return
    if hasattr(importing, "importFile"):
        importing.importFile(mw, str(path))
        return
    raise RuntimeError("Unable to find a compatible Anki CSV import function")


def _tracking_base_dir(mw) -> Path:
    config = AddonConfig.from_dict(mw.addonManager.getConfig(__name__))
    return resolve_output_paths(config).base_dir


def _install_delete_tracking(mw) -> None:
    col = getattr(mw, "col", None)
    if col is None:
        return
    if getattr(col, "_italki_delete_tracking_installed", False):
        return

    installed = False
    for method_name in ("remove_notes", "remNotes"):
        original = getattr(col, method_name, None)
        if not callable(original):
            continue

        def wrapped(note_ids, *args, __original=original, **kwargs):
            global _SUPPRESS_DELETE_TRACKING
            if _SUPPRESS_DELETE_TRACKING > 0:
                return __original(note_ids, *args, **kwargs)
            keys = keys_for_note_ids(col, note_ids)
            result = __original(note_ids, *args, **kwargs)
            if keys["vocab"] or keys["cloze"]:
                base_dir = _tracking_base_dir(mw)
                append_deleted_keys(base_dir, keys)
                remove_managed_note_ids(base_dir, note_ids)
            return result

        setattr(col, method_name, wrapped)
        installed = True

    if installed:
        setattr(col, "_italki_delete_tracking_installed", True)


def _import_latest_cards() -> None:
    from aqt import mw

    if getattr(mw, "col", None) is None:
        _show_warning("Open an Anki profile/collection first.")
        return

    _install_delete_tracking(mw)

    config = AddonConfig.from_dict(mw.addonManager.getConfig(__name__))
    paths = resolve_output_paths(config)
    planned = planned_import_targets(config, paths)
    existing, missing = split_existing_targets(planned)
    deleted_keys = load_deleted_keys(paths.base_dir)

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
    imported_labels: list[str] = []
    skipped_existing_rows = 0
    skipped_deleted_rows = 0
    protected_overwrite_rows = 0
    deduped_rows = 0
    deleted_notes = 0
    skipped_empty_files: list[str] = []
    tracked_new_notes = 0
    for index, (label, path) in enumerate(existing, start=1):
        rows = read_data_rows(path)
        rows, removed_duplicate_rows = dedupe_import_rows(label, rows)
        deduped_rows += removed_duplicate_rows
        rows, removed_deleted_rows = filter_rows_by_deleted_keys(
            label=label,
            rows=rows,
            deleted_keys=deleted_keys.get(label, set()),
        )
        skipped_deleted_rows += removed_deleted_rows

        key_index = existing_key_index(mw.col, label)
        managed_index = None
        if config.import_mode == "overwrite" and config.overwrite_scope == "tracked-only":
            managed_index = managed_key_index(paths.base_dir, label)
        rows, skipped_rows, note_ids_to_remove = filter_rows_by_import_mode(
            label=label,
            rows=rows,
            mode=config.import_mode,
            key_index=key_index,
            managed_note_ids_by_key=managed_index,
        )
        if config.import_mode == "overwrite":
            protected_overwrite_rows += skipped_rows
        else:
            skipped_existing_rows += skipped_rows

        if note_ids_to_remove:
            global _SUPPRESS_DELETE_TRACKING
            _SUPPRESS_DELETE_TRACKING += 1
            try:
                deleted_notes += remove_note_ids(mw.col, note_ids_to_remove)
                remove_managed_note_ids(paths.base_dir, note_ids_to_remove)
            finally:
                _SUPPRESS_DELETE_TRACKING -= 1

        if not rows:
            skipped_empty_files.append(f"{label} ({path.name})")
            continue

        key_index_before_import = existing_key_index(mw.col, label)
        import_path = write_import_rows(path, rows)
        _show_status(f"Import {index}/{len(existing)}: {label} cards ({path.name}) [{config.import_mode}]")
        _import_csv(mw, import_path)
        key_index_after_import = existing_key_index(mw.col, label)
        imported_note_ids_by_key = collect_imported_note_ids_by_key(
            label=label,
            rows=rows,
            key_index_before=key_index_before_import,
            key_index_after=key_index_after_import,
        )
        tracked_new_notes += append_managed_note_ids(
            paths.base_dir,
            label=label,
            note_ids_by_key=imported_note_ids_by_key,
        )
        imported_count += 1
        imported_labels.append(f"{label} ({path.name})")

    details = [f"Started import for {imported_count} file(s)."]
    details.append(f"Import mode: {config.import_mode}.")
    if config.import_mode == "overwrite":
        details.append(f"Overwrite scope: {config.overwrite_scope}.")
    if imported_labels:
        details.append(f"Import order: {', '.join(imported_labels)}.")
    if deduped_rows:
        details.append(f"Dropped {deduped_rows} duplicate CSV row(s) before import.")
    if skipped_existing_rows:
        details.append(f"Skipped {skipped_existing_rows} row(s) already present in collection.")
    if protected_overwrite_rows:
        details.append(
            f"Protected {protected_overwrite_rows} row(s): matching notes were not managed by this add-on."
        )
    if skipped_deleted_rows:
        details.append(f"Skipped {skipped_deleted_rows} row(s) previously deleted in Anki.")
    if deleted_notes:
        details.append(f"Deleted {deleted_notes} existing note(s) before overwrite import.")
    if tracked_new_notes:
        details.append(f"Tracked {tracked_new_notes} imported note id(s) for safe future overwrite.")
    if skipped_empty_files:
        details.append(f"Skipped files with no rows to import: {', '.join(skipped_empty_files)}.")
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
