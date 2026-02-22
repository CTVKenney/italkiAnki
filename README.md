# italki-anki

Convert messy italki Chinese lesson chat into Anki-ready CSV files.

The tool:
- takes raw pasted chat text,
- filters obvious noise (metadata, labels, channel names, social sign-offs),
- classifies items into vocab/grammar/sentence cards,
- excludes terms listed in the default known-terms list,
- writes CSV output for Anki import,
- can optionally generate audio with Amazon Polly.

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

## Known Terms (default-on filtering)

The tool loads `italki_anki/known_terms.txt` automatically on every run and excludes matching vocab entries by default.

Default seeded examples include:
- `大学`
- `现在`
- `没关系`

To customize, edit that file (one term per line, `#` for comments).

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

Import behavior notes:
- If both CSVs exist, Anki opens two import dialogs: first vocab, then cloze.
- The add-on shows a status toast (`Import 1/2: vocab ...`, `Import 2/2: cloze ...`) so it is clear which file is being imported.
- Known CSV header rows are stripped before import, so header labels are not imported as notes.

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
export OPENAI_API_KEY='sk-...'
# optional; defaults to us-east-1
export AWS_DEFAULT_REGION='us-east-1'
# optional override; default is gpt-4o-audio-preview
export OPENAI_AUDIO_EVAL_MODEL='gpt-4o-audio-preview'
.tools/bin/bazel test //:unit_tests --test_env=ITALKI_RUN_POLLY_PRONUNCIATION_TEST=1 --test_env=OPENAI_API_KEY --test_env=OPENAI_AUDIO_EVAL_MODEL --test_env=AWS_DEFAULT_REGION --test_env=HOME
```

Notes:
- This test makes live API calls to both AWS Polly and OpenAI.
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
- Vocab in `italki_anki/known_terms.txt` is excluded by default.
- Measure-word examples are randomized with Chinese numerals (`一`..`十`) rather than Arabic digits.
- Cloze pinyin chunking is aligned with Chinese chunk boundaries for better sentence consistency.
