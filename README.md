# italki-anki

Convert messy italki Chinese lesson chat into Anki-ready CSV files.

The tool:
- takes raw pasted chat text,
- filters obvious noise (metadata, labels, channel names, social sign-offs),
- classifies items into vocab/grammar/sentence cards,
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

## Optional: Anki add-on (one-click latest import)

An add-on is included at:

`anki_addon/italki_latest_importer`

Install by copying that folder to your Anki add-ons directory:

`~/.local/share/Anki2/addons21/italki_latest_importer`

Then restart Anki and use:

`Tools -> Import Latest italki Cards`

Configurable path is in the add-on config (`output_dir`, default `~/Chinese/output`).

## Testing

Pytest:

```bash
.venv/bin/pytest -q
```

Bazel test target:

```bash
.tools/bin/bazel test //:unit_tests
```

## Bazel build

Build CLI target:

```bash
.tools/bin/bazel build //:italki_anki_cli
```

## Behavior notes

- Parser uses deterministic filtering first.
- Teacher-chat sign-offs (for example, thanks/farewell lines) are treated as noise.
- Measure-word examples are randomized with Chinese numerals (`一`..`十`) rather than Arabic digits.
- Cloze pinyin chunking is aligned with Chinese chunk boundaries for better sentence consistency.
