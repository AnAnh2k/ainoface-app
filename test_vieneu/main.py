
import io

import numpy as np
import soundfile as sf
from fastapi import FastAPI, Body, HTTPException
from fastapi.responses import StreamingResponse

from vieneu import Vieneu

app = FastAPI()

# VieNeu model may expose its sample rate; default to 48000
SAMPLE_RATE = None

DEFAULT_VOICE = "Trúc Ly"

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

print("Loading VieNeu-TTS...")
try:
    tts_model = Vieneu()
    print("VieNeu-TTS ready")
except Exception as e:
    print(f"Error loading VieNeu-TTS model: {e}")
    tts_model = None

# Use sample rate reported by the model when available
SAMPLE_RATE = getattr(tts_model, "sample_rate", None) or 48000


def synthesize(text: str, voice: str):
    if tts_model is None:
        raise RuntimeError("Mô hình giọng nói AI chưa được tải thành công.")
    if voice not in PRESET_VOICES:
        voice = DEFAULT_VOICE
    # Delegate chunking, phonemization and joining to the model for
    # best quality and performance.
    audio = tts_model.infer(text=text, voice=voice)
    return np.asarray(audio, dtype=np.float32)


@app.post("/v1/audio/speech")
def tts(payload: dict = Body(...)):
    if tts_model is None:
        raise HTTPException(
            status_code=500,
            detail="Mô hình giọng nói AI chưa được tải thành công. Vui lòng kết nối Internet ổn định và khởi động lại ứng dụng."
        )
    text = payload.get("input", "").strip()
    voice = payload.get("voice", DEFAULT_VOICE)

    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    # Let the model handle chunking and joining.
    audio = synthesize(text, voice)
    if audio.ndim > 1:
        audio = audio.mean(axis=-1)
    final_audio = np.clip(audio, -1.0, 1.0)

    buffer = io.BytesIO()

    sf.write(
        buffer,
        final_audio,
        SAMPLE_RATE,
        format="WAV"
    )

    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="audio/wav"
    )


@app.get("/v1/voices")
def voices():
    return {
        "voices": sorted(PRESET_VOICES)
    }

    
@app.get("/")
def health():
    return {
        "status": "ready" if tts_model is not None else "error",
        "error": None if tts_model is not None else "Mô hình giọng nói AI chưa được tải thành công. Vui lòng kết nối Internet ổn định và khởi động lại ứng dụng.",
        "default_voice": DEFAULT_VOICE
    }

