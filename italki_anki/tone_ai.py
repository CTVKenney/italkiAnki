from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from .tone_model import classify_second_syllable_tone_3_or_4, decode_audio_to_mono_samples

DEFAULT_TONE_MODEL_ID = "snu-nia-12/wav2vec2-large-xlsr-53_nia12_phone-pinyin_chinese"
_TONE_DIGIT_RE = re.compile(r"(?<!\d)([1-5])(?!\d)")


class ToneAIError(RuntimeError):
    """Raised when tone classification via AI backends cannot complete."""


@dataclass(frozen=True)
class TonePrediction:
    tone: int
    transcript: str


class ToneClassifier(Protocol):
    def classify(self, audio_bytes: bytes, *, audio_format: str = "mp3") -> TonePrediction:
        raise NotImplementedError


@dataclass(frozen=True)
class ToneEvalSample:
    audio_path: Path
    expected_tone: int
    audio_format: str


@dataclass(frozen=True)
class ToneEvalRecord:
    audio_path: Path
    expected_tone: int
    predicted_tone: int | None
    correct: bool
    transcript: str
    error: str | None = None


@dataclass(frozen=True)
class ToneEvalSummary:
    total: int
    predicted: int
    correct: int
    accuracy: float
    per_tone: dict[int, dict[str, float | int]]


@dataclass
class AutocorrelationTone34Classifier:
    """Legacy classifier that only predicts tone 3 vs tone 4."""

    def classify(self, audio_bytes: bytes, *, audio_format: str = "mp3") -> TonePrediction:
        tone = classify_second_syllable_tone_3_or_4(audio_bytes, audio_format=audio_format)
        return TonePrediction(tone=tone, transcript="autocorrelation-f0")


@dataclass
class HFWav2Vec2PinyinToneClassifier:
    """CTC pinyin model classifier that recovers tones from transcript digits."""

    model_id: str = DEFAULT_TONE_MODEL_ID
    device: str = "cpu"
    syllable_index: int = -1
    allow_neutral_tone: bool = True

    # Lazy-loaded members to keep import-time light and testable without torch/transformers.
    _processor: object | None = None
    _model: object | None = None
    _torch: object | None = None

    def _ensure_loaded(self) -> None:
        if self._processor is not None and self._model is not None and self._torch is not None:
            return
        try:
            import torch
            from transformers import AutoModelForCTC, AutoProcessor
        except ImportError as exc:  # pragma: no cover - optional dependency path
            raise ToneAIError(
                "torch and transformers are required for hf-wav2vec2-pinyin tone backend"
            ) from exc

        self._torch = torch
        self._processor = AutoProcessor.from_pretrained(self.model_id)
        self._model = AutoModelForCTC.from_pretrained(self.model_id)
        if self.device:
            self._model = self._model.to(self.device)
        self._model.eval()

    def classify(self, audio_bytes: bytes, *, audio_format: str = "mp3") -> TonePrediction:
        self._ensure_loaded()
        assert self._processor is not None
        assert self._model is not None
        assert self._torch is not None

        samples, sample_rate = decode_audio_to_mono_samples(audio_bytes, audio_format=audio_format)
        inputs = self._processor(samples, sampling_rate=sample_rate, return_tensors="pt")
        input_values = inputs["input_values"]
        if self.device:
            input_values = input_values.to(self.device)
        attention_mask = inputs.get("attention_mask")
        if attention_mask is not None and self.device:
            attention_mask = attention_mask.to(self.device)

        with self._torch.no_grad():
            if attention_mask is None:
                logits = self._model(input_values).logits
            else:
                logits = self._model(input_values, attention_mask=attention_mask).logits
        predicted_ids = self._torch.argmax(logits, dim=-1)
        transcript = self._processor.batch_decode(predicted_ids)[0].strip()
        tone = pick_tone_from_transcript(
            transcript,
            syllable_index=self.syllable_index,
            allow_neutral_tone=self.allow_neutral_tone,
        )
        return TonePrediction(tone=tone, transcript=transcript)


def extract_tone_digits(transcript: str) -> list[int]:
    normalized = transcript.lower().replace("ü", "v")
    return [int(match.group(1)) for match in _TONE_DIGIT_RE.finditer(normalized)]


def pick_tone_from_transcript(
    transcript: str,
    *,
    syllable_index: int = -1,
    allow_neutral_tone: bool = True,
) -> int:
    tones = extract_tone_digits(transcript)
    if not tones:
        raise ToneAIError(f"no tone digits found in model transcript: {transcript!r}")
    try:
        tone = tones[syllable_index]
    except IndexError as exc:
        raise ToneAIError(
            f"syllable index {syllable_index} out of range for transcript tones {tones}"
        ) from exc
    if tone == 5 and not allow_neutral_tone:
        raise ToneAIError("neutral tone (5) detected but --tone-allow-neutral is disabled")
    return tone


def load_tone_eval_samples(path: str | Path) -> list[ToneEvalSample]:
    file_path = Path(path)
    base_dir = file_path.parent
    samples: list[ToneEvalSample] = []
    for line_no, raw in enumerate(file_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "\t" in line:
            columns = line.split("\t")
        else:
            columns = line.split(",")
        if len(columns) < 2:
            raise ToneAIError(f"invalid eval line {line_no}: expected '<audio_path><tab><tone>'")
        raw_audio_path = columns[0].strip()
        raw_tone = columns[1].strip()
        if not raw_audio_path:
            raise ToneAIError(f"invalid eval line {line_no}: empty audio path")
        try:
            expected_tone = int(raw_tone)
        except ValueError as exc:
            raise ToneAIError(f"invalid eval line {line_no}: tone must be integer 1-5") from exc
        if expected_tone < 1 or expected_tone > 5:
            raise ToneAIError(f"invalid eval line {line_no}: tone must be in range 1-5")
        audio_path = Path(raw_audio_path)
        if not audio_path.is_absolute():
            audio_path = (base_dir / audio_path).resolve()
        suffix = audio_path.suffix.lower().lstrip(".")
        audio_format = suffix if suffix else "mp3"
        samples.append(
            ToneEvalSample(
                audio_path=audio_path,
                expected_tone=expected_tone,
                audio_format=audio_format,
            )
        )
    if not samples:
        raise ToneAIError(f"no evaluation samples found in {file_path}")
    return samples


def evaluate_tone_classifier(
    classifier: ToneClassifier,
    samples: Sequence[ToneEvalSample],
) -> tuple[ToneEvalSummary, list[ToneEvalRecord]]:
    records: list[ToneEvalRecord] = []
    for sample in samples:
        try:
            audio_bytes = sample.audio_path.read_bytes()
            prediction = classifier.classify(audio_bytes, audio_format=sample.audio_format)
            correct = prediction.tone == sample.expected_tone
            records.append(
                ToneEvalRecord(
                    audio_path=sample.audio_path,
                    expected_tone=sample.expected_tone,
                    predicted_tone=prediction.tone,
                    correct=correct,
                    transcript=prediction.transcript,
                )
            )
        except Exception as exc:
            records.append(
                ToneEvalRecord(
                    audio_path=sample.audio_path,
                    expected_tone=sample.expected_tone,
                    predicted_tone=None,
                    correct=False,
                    transcript="",
                    error=str(exc),
                )
            )

    predicted_records = [record for record in records if record.predicted_tone is not None]
    predicted = len(predicted_records)
    correct = sum(1 for record in predicted_records if record.correct)
    accuracy = (correct / predicted) if predicted else 0.0

    per_tone: dict[int, dict[str, float | int]] = {}
    for tone in range(1, 6):
        tone_records = [record for record in predicted_records if record.expected_tone == tone]
        tone_total = len(tone_records)
        tone_correct = sum(1 for record in tone_records if record.correct)
        per_tone[tone] = {
            "n": tone_total,
            "correct": tone_correct,
            "accuracy": (tone_correct / tone_total) if tone_total else 0.0,
        }

    summary = ToneEvalSummary(
        total=len(records),
        predicted=predicted,
        correct=correct,
        accuracy=accuracy,
        per_tone=per_tone,
    )
    return summary, records


def serialize_tone_eval(summary: ToneEvalSummary, records: Sequence[ToneEvalRecord]) -> dict:
    return {
        "summary": {
            "total": summary.total,
            "predicted": summary.predicted,
            "correct": summary.correct,
            "accuracy": summary.accuracy,
            "per_tone": summary.per_tone,
        },
        "records": [
            {
                "audio_path": str(record.audio_path),
                "expected_tone": record.expected_tone,
                "predicted_tone": record.predicted_tone,
                "correct": record.correct,
                "transcript": record.transcript,
                "error": record.error,
            }
            for record in records
        ],
    }


def write_tone_eval_json(
    path: str | Path,
    summary: ToneEvalSummary,
    records: Sequence[ToneEvalRecord],
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = serialize_tone_eval(summary, records)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path

