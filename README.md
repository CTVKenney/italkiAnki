# italki-anki

Convert messy italki Chinese lesson chat into Anki-ready CSV files.

The tool:
- takes raw pasted chat text,
- filters obvious noise (metadata, labels, channel names, social sign-offs),
- classifies items into vocab/grammar/sentence cards,
- writes CSV output for Anki import,
- can optionally generate audio with Amazon Polly.

## Easy Start (Idiot-Proof)

Do this exactly:

1. Clone and install once:

```bash
cd ~/Chinese
git clone git@github.com:CTVKenney/italkiAnki.git
cd italkiAnki
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

2. Set your API key once per shell:

```bash
export OPENAI_API_KEY='sk-...'
```

3. Generate cards (this opens your editor to paste lesson text):

```bash
~/Chinese/italkiAnki/.venv/bin/italki-anki --interactive --openai --audio --out-dir ~/Chinese/output --run-mode both
```

4. In Anki: `Tools -> Import Latest italki Cards`

5. In each import dialog, set deck to:

`General::汉语::italki`

## Regenerate After Tone Improvements

If you generated cards before the tone fixes, regenerate and re-import once in overwrite mode:

1. Update repo:

```bash
cd ~/Chinese/italkiAnki
git pull
```

2. In Anki add-on config, temporarily set:

```json
"import_mode": "overwrite",
"overwrite_scope": "collection"
```

3. Regenerate:

```bash
~/Chinese/italkiAnki/.venv/bin/italki-anki --interactive --openai --audio --out-dir ~/Chinese/output --run-mode both
```

4. Import from Anki menu: `Tools -> Import Latest italki Cards`

5. Set add-on config back to:

```json
"import_mode": "add-only",
"overwrite_scope": "tracked-only"
```

## Install

```bash
cd ~/Chinese/italkiAnki
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Validate:

```bash
italki-anki --help
```

## Fastest start (recommended)

If you already have API keys/credentials set up, this is the daily command:

```bash
~/Chinese/italkiAnki/.venv/bin/italki-anki --interactive --openai --audio --out-dir ~/Chinese/output --run-mode both
```

Why this command:
- uses OpenAI classification (`--openai`) to reduce noisy cards,
- generates audio (`--audio`),
- keeps latest files for Anki add-on import,
- archives each run (`--run-mode both`).

## Primary workflow (interactive)

```bash
export EDITOR=nano   # optional; default is vi
italki-anki --interactive --out-dir "$HOME/Chinese/italki-output"
```

What happens:
1. Your editor opens a temporary text buffer.
2. Paste raw lesson/chat text.
3. Save and close.
4. Cards are generated in your output directory.

## Other input modes

From file:

```bash
italki-anki --input lesson.txt --out-dir output
```

From stdin:

```bash
cat lesson.txt | italki-anki --stdin --out-dir output
```

Legacy form is also supported:

```bash
italki-anki build lesson.txt --out-dir output
```

## Output

The tool writes:
- `vocab_cards.csv`
- `cloze_cards.csv`
- `audio/` (only when `--audio` is enabled)

By default (`--run-mode both`) it also archives each run under:
- `runs/<run_id>/...`

and writes a manifest:
- `latest_run.json`

## OpenAI setup (`--openai`)

Required:

```bash
export OPENAI_API_KEY='sk-...'
```

Optional:

```bash
export OPENAI_MODEL='gpt-4o-mini'
export OPENAI_BASE_URL='https://api.openai.com/v1'
export OPENAI_MAX_LINES='20'
```

Run:

```bash
italki-anki --interactive --openai --out-dir output
```

## Polly setup (`--audio`)

Install dependency:

```bash
pip install boto3
```

Configure AWS credentials:

```bash
aws configure
aws sts get-caller-identity
```

IAM permission needed: `polly:SynthesizeSpeech`

Run:

```bash
italki-anki --interactive --audio --out-dir output
```

## OpenAI + Polly together

```bash
italki-anki --interactive --openai --audio --out-dir "$HOME/Chinese/italki-output"
```

## Tone AI Evaluation (High-Accuracy Path)

This project now supports a dedicated tone-evaluation mode using a pluggable backend.

Install optional dependencies for the Hugging Face backend:

```bash
pip install torch transformers
```

Prepare a TSV (or CSV) with labeled samples:

```text
/abs/path/to/audio_001.mp3	3
/abs/path/to/audio_002.wav	4
```

Run evaluation:

```bash
italki-anki \
  --tone-eval-tsv /abs/path/to/samples.tsv \
  --tone-backend hf-wav2vec2-pinyin \
  --tone-model-id snu-nia-12/wav2vec2-large-xlsr-53_nia12_phone-pinyin_chinese \
  --tone-eval-json-out /abs/path/to/tone_eval.json
```

Alternative legacy comparator (tone 3 vs 4 only):

```bash
italki-anki --tone-eval-tsv /abs/path/to/samples.tsv --tone-backend autocorr-3-4
```

Notes:
- `hf-wav2vec2-pinyin` supports tones 1-5 (tone digits parsed from model transcript).
- `autocorr-3-4` is the legacy deterministic fallback and only predicts tones 3/4.
- Main card generation workflow is unchanged.

## Multi-run behavior

Use `--run-mode` to control output lifecycle:

- `both` (default): write a timestamped archive run and publish root files for one-click Anki import.
- `latest`: only write/overwrite root files.
- `archive`: only write timestamped run files (no root CSV overwrite).

Examples:

```bash
# default behavior (best for Anki add-on + history)
italki-anki --interactive --out-dir "$HOME/Chinese/output" --run-mode both

# only overwrite latest files
italki-anki --interactive --out-dir "$HOME/Chinese/output" --run-mode latest

# only archive
italki-anki --interactive --out-dir "$HOME/Chinese/output" --run-mode archive
```

## CLI flags reference

Input source (choose one):
- `--interactive`: open `$EDITOR` and paste text.
- `--stdin`: read text from standard input.
- `--input PATH`: read text from a file.

Core output/lifecycle:
- `--out-dir PATH`: output root directory (default: `output`).
- `--run-mode latest|archive|both`: output lifecycle mode (default: `both`).

Classification:
- `--openai`: use OpenAI classifier (recommended).
- no `--openai`: use offline stub heuristic classifier (fast, noisier).
- `--seed INT`: deterministic randomness for measure-word number selection and repeatability.

Card generation:
- `--audio`: generate audio via Amazon Polly.
- `--max-cloze-len INT`: soft chunk size for cloze splitting (default: `8`).

## Optional: Anki add-on (one-click latest import)

An add-on is included at:

`anki_addon/italki_latest_importer`

Install by copying that folder to your Anki add-ons directory:

`~/.local/share/Anki2/addons21/italki_latest_importer`

Or, for active development, symlink it so edits are picked up immediately:

```bash
mkdir -p ~/.local/share/Anki2/addons21
ln -sfn ~/Chinese/italkiAnki/anki_addon/italki_latest_importer ~/.local/share/Anki2/addons21/italki_latest_importer
```

Then restart Anki and use:

`Tools -> Import Latest italki Cards`

Configurable path is in the add-on config (`output_dir`, default `~/Chinese/output`).
Import behavior mode is configurable with `import_mode`:
- `add-only` (default): skip incoming rows that already exist in your collection.
- `overwrite`: replace existing notes before import.

Overwrite safety scope is configurable with `overwrite_scope`:
- `tracked-only` (default): only overwrite notes tracked as imported by this add-on.
- `collection`: overwrite all matching notes in the collection (legacy, destructive; use only if that keyspace is dedicated to italki imports).

Import behavior notes:
- If both CSVs exist, Anki opens two import dialogs: first vocab, then cloze.
- The add-on shows a status toast (`Import 1/2: vocab ...`, `Import 2/2: cloze ...`) so it is clear which file is being imported.
- Known CSV header rows are stripped before import, so header labels are not imported as notes.
- Incoming CSV rows are deduplicated before import (`Simplified` key for vocab, `Text` key for cloze).
- User-deleted cards are remembered and skipped on future imports via `<output_dir>/.anki_deleted_keys.json`.
- Imported note IDs are tracked in `<output_dir>/.anki_managed_notes.json` for safe overwrite behavior.
- Each import appends a summary line to `<output_dir>/.anki_import_history.jsonl` (including estimated new cards).

## Testing

Primary test workflow (Bazel):

```bash
.tools/bin/bazel test //:all_tests
```

Equivalent direct target:

```bash
.tools/bin/bazel test //:unit_tests
```

Direct `pytest` invocation is intentionally blocked. Run tests only through Bazel.

Optional live Polly pronunciation integration test (off by default):

```bash
export ITALKI_RUN_POLLY_PRONUNCIATION_TEST=1
# optional; defaults to us-east-1
export AWS_DEFAULT_REGION='us-east-1'
.tools/bin/bazel test //:unit_tests --test_env=ITALKI_RUN_POLLY_PRONUNCIATION_TEST=1 --test_env=AWS_DEFAULT_REGION --test_env=HOME
```

Notes:
- This test makes live API calls to AWS Polly only.
- Tone verification is done locally via pitch-contour analysis (autocorrelation F0 model), not via an LLM.
- It is skipped unless `ITALKI_RUN_POLLY_PRONUNCIATION_TEST=1` is set.

## Bazel build

Build CLI target:

```bash
.tools/bin/bazel build //:italki_anki_cli
```

Run CLI via Bazel:

```bash
.tools/bin/bazel run //:italki_anki_cli -- --interactive --openai --audio --out-dir "$HOME/Chinese/output" --run-mode both
```

## Behavior notes

- Parser uses deterministic filtering first.
- Teacher-chat sign-offs (for example, thanks/farewell lines) are treated as noise.
- Basic small-talk greetings (for example, `你好` / `hello`) are filtered.
- Measure-word examples are randomized with Chinese numerals (`一`..`十`) rather than Arabic digits.
- Cloze pinyin chunking is aligned with Chinese chunk boundaries for better sentence consistency.
