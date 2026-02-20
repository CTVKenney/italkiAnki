# italki Latest Importer (Anki Add-on)

This add-on adds a Tools menu action in Anki:

- `Tools -> Import Latest italki Cards`

When clicked, it:
- reads card CSVs from your configured output directory,
- starts Anki CSV imports for available files,
- copies new audio files into Anki's media folder.

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
  "copy_audio": true
}
```
