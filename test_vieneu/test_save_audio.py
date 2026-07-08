from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import soundfile as sf
from vieneu import Vieneu


OUTPUT_DIR = Path(__file__).parent / "audio_samples"
TEXT_TO_SPEAK = "Xin chào, đây là câu test để tạo file audio và lưu ra file wav."
VOICE_NAME = "Trúc Ly"
OUTPUT_NAME = None

PRESET_VOICES = {
    "Trúc Ly",
    "Phạm Tuyên",
    "Thái Sơn",
    "Xuân Vĩnh",
    "Thanh Bình",
    "Minh Đức",
    "Ngọc Linh",
    "Đoan Trang",
    "Mai Anh",
    "Thục Đoan",
}


def load_model() -> tuple[Vieneu, str, int]:
    print("Loading VieNeu-TTS...")
    model = Vieneu()
    sample_rate = getattr(model, "sample_rate", 48000) or 48000

    print("VieNeu-TTS ready")

    return model, "auto", sample_rate


def sanitize_filename(text: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in text)
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned[:48] or "tts"


def next_audio_number(output_dir: Path) -> int:
    pattern = re.compile(r"^audio (\d+)$", re.IGNORECASE)
    highest = 0

    for file_path in output_dir.glob("audio *.wav"):
        match = pattern.match(file_path.stem)
        if not match:
            continue

        highest = max(highest, int(match.group(1)))

    return highest + 1


def synthesize_text(model: Vieneu, text: str, voice: str) -> np.ndarray:
    if voice not in PRESET_VOICES:
        voice = VOICE_NAME

    audio = model.infer(text=text, voice=voice)
    audio = np.asarray(audio, dtype=np.float32)

    if audio.ndim > 1:
        audio = audio.mean(axis=-1)

    return np.clip(audio, -1.0, 1.0)


def main() -> int:
    model, device, sample_rate = load_model()

    text = TEXT_TO_SPEAK.strip()
    if not text:
        raise ValueError("TEXT_TO_SPEAK is empty")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    final_audio = synthesize_text(model, text, VOICE_NAME)

    output_name = OUTPUT_NAME
    if not output_name:
        output_name = f"audio {next_audio_number(OUTPUT_DIR)}"

    output_path = OUTPUT_DIR / f"{output_name}.wav"
    sf.write(output_path, final_audio, sample_rate, format="WAV")

    print(f"Saved: {output_path}")
    print(f"Device: {device}")
    print(f"Voice: {VOICE_NAME}")
    print(f"Sample rate: {sample_rate}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())