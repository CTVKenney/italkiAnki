# italki Latest Importer (Anki Add-on)

This add-on adds a Tools menu action in Anki:

- `Tools -> Import Latest italki Cards`

When clicked, it:
- reads card CSVs from your configured output directory,
- deduplicates incoming rows by card key (`Simplified` for vocab, `Text` for cloze),
- applies import mode (`add-only` or `overwrite`) against existing notes,
- starts Anki CSV imports for remaining rows (one dialog per file, with `vocab`/`cloze` status toasts),
- copies new audio files into Anki's media folder.

The add-on strips the known CSV header rows before invoking Anki import, so header labels are not imported as notes.

## Install

1. Copy this folder into your Anki add-ons directory:

`~/.local/share/Anki2/addons21/italki_latest_importer`

2. Restart Anki.

## Configure

In Anki:

1. `Tools -> Add-ons`
2. Select `italki_latest_importer`
3. Click `Config`
4. Edit `output_dir` (example: `~/Chinese/output`)

Default config:

```json
{
  "output_dir": "~/Chinese/output",
  "vocab_filename": "vocab_cards.csv",
  "cloze_filename": "cloze_cards.csv",
  "audio_subdir": "audio",
  "import_vocab": true,
  "import_cloze": true,
  "copy_audio": true,
  "import_mode": "add-only",
  "overwrite_scope": "tracked-only"
}
```

`import_mode` behavior:
- `add-only`: skip rows whose card key already exists in your collection.
- `overwrite`: replace existing notes only when matches are managed by this add-on (safe default), then import new rows.

`overwrite_scope` behavior (used when `import_mode` is `overwrite`):
- `tracked-only` (default): only delete notes previously tracked as imported by this add-on.
- `collection`: legacy behavior; delete all matching notes in the collection by key.

Deleted-card memory:
- When you delete a supported italki card in Anki, the add-on records its key.
- Future imports skip rows with keys previously deleted by you.
- Stored at `<output_dir>/.anki_deleted_keys.json`.

Managed-note tracking:
- Imported note IDs are tracked for safer overwrite matching.
- Stored at `<output_dir>/.anki_managed_notes.json`.
