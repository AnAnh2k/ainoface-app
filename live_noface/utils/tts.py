import json
import urllib.request
import urllib.error

def call_tts_service(text: str, voice: str = 'Trúc Ly') -> tuple[bytes, str, int]:
    """
    Calls the local FastAPI TTS service to synthesize speech.
    Returns:
        tuple[bytes, str, int]: (audio_data, content_type, status_code)
    """
    url = "http://127.0.0.1:8005/v1/audio/speech"
    payload = {
        "input": text,
        "voice": voice
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        
        with urllib.request.urlopen(req, timeout=15) as response:
            audio_bytes = response.read()
            content_type = response.getheader("Content-Type") or "audio/wav"
            return audio_bytes, content_type, response.status
    except urllib.error.HTTPError as e:
        try:
            error_msg = e.read().decode("utf-8", errors="ignore")
        except Exception:
            error_msg = str(e)
        return json.dumps({"success": False, "error": error_msg}).encode("utf-8"), "application/json", e.code
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}).encode("utf-8"), "application/json", 500

def stream_tts_audio(*args, **kwargs):
    """
    Placeholder for stream_tts_audio if needed by any other part of the system.
    """
    pass
