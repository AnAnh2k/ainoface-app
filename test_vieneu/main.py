
import io
import queue
import threading
from concurrent.futures import Future

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

# Priority Queue Worker for Sequential Model Inference
# Priority order: 0 (TikTok Comment/Gift - High), 1 (Scenario Script - Normal), 2 (Like - Low)
_job_queue = queue.PriorityQueue()
_job_counter = 0
_counter_lock = threading.Lock()

def _tts_worker():
    while True:
        priority, count, text, voice, fut = _job_queue.get()
        try:
            if tts_model is None:
                fut.set_exception(RuntimeError("Mô hình giọng nói AI chưa được tải thành công."))
            else:
                audio = tts_model.infer(text=text, voice=voice)
                fut.set_result(audio)
        except Exception as exc:
            fut.set_exception(exc)
        finally:
            _job_queue.task_done()

_worker_thread = threading.Thread(target=_tts_worker, daemon=True)
_worker_thread.start()

def synthesize(text: str, voice: str, priority: int = 1):
    if tts_model is None:
        raise RuntimeError("Mô hình giọng nói AI chưa được tải thành công.")
    if voice not in PRESET_VOICES:
        voice = DEFAULT_VOICE

    global _job_counter
    with _counter_lock:
        _job_counter += 1
        count = _job_counter

    fut = Future()
    _job_queue.put((priority, count, text, voice, fut))
    audio = fut.result(timeout=60)
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
    priority = int(payload.get("priority", 1))

    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    try:
        audio = synthesize(text, voice, priority=priority)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

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
