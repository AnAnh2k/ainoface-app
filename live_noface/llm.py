import json
import logging
import os
import sys
from typing import Callable, Optional

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = 10
READ_TIMEOUT_SECONDS = 55
DEFAULT_LLM_URL = "https://luck-tvs-schedules-palace.trycloudflare.com"


class LLMError(Exception):
    def __init__(self, kind: str, message: str, detail: str = ""):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.detail = detail

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "message": self.message,
            "detail": self.detail,
        }


def _runtime_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def _get_default_llm_url() -> str:
    config_paths = [
        os.path.join(_runtime_base_dir(), "config.json"),
        os.path.abspath("config.json"),
        os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "config.json")),
    ]
    for config_path in dict.fromkeys(config_paths):
        if not os.path.exists(config_path):
            continue
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            url = cfg.get("llm_api_base_url") or cfg.get("ollama_base_url")
            if url:
                return str(url).strip()
        except Exception as exc:
            logger.warning("Could not read LLM config %s: %s", config_path, exc)
    return DEFAULT_LLM_URL


LLM_API_BASE_URL = os.getenv(
    "LLM_API_BASE_URL",
    os.getenv("OLLAMA_BASE_URL", _get_default_llm_url()),
)


def _generate_url(base: str) -> str:
    base = (base or "").strip().rstrip("/")
    if base.endswith("/generate"):
        return base
    return f"{base}/generate"


def resolve_llm_generate_url() -> str:
    current_llm_url = os.getenv("LLM_API_BASE_URL") or os.getenv("OLLAMA_BASE_URL", _get_default_llm_url())
    return _generate_url(current_llm_url)


def _to_llm_error(exc: Exception, generate_url: str) -> LLMError:
    if isinstance(exc, LLMError):
        return exc
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return LLMError(
            "connect_timeout",
            "Không kết nối được máy chủ tạo nội dung, ứng dụng sẽ tiếp tục thử lại.",
            str(exc),
        )
    if isinstance(exc, requests.exceptions.ReadTimeout):
        return LLMError(
            "read_timeout",
            "Máy chủ AI phản hồi chậm, ứng dụng sẽ tiếp tục thử lại.",
            str(exc),
        )
    if isinstance(exc, requests.exceptions.HTTPError):
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code == 404:
            return LLMError(
                "endpoint_404",
                "Sai endpoint API AI hoặc server AI chưa mở route tạo kịch bản.",
                generate_url,
            )
        return LLMError(
            "http_error",
            f"Lỗi HTTP {status_code or ''} từ máy chủ AI.".strip(),
            str(exc),
        )
    if isinstance(exc, requests.exceptions.RequestException):
        return LLMError(
            "request_error",
            "Không kết nối được máy chủ tạo nội dung, ứng dụng sẽ tiếp tục thử lại.",
            str(exc),
        )
    return LLMError("unknown", f"Lỗi gọi AI: {exc}", str(exc))


def llm_continuous(
    prompt: str,
    quit_event,
    datainfo: Optional[dict] = None,
    on_sentence: Optional[Callable[[str], None]] = None,
    max_iterations: Optional[int] = None,
    history: Optional[list[str]] = None,
    max_sentences: Optional[int] = 10,
    on_error: Optional[Callable[[dict], None]] = None,
    timeout: tuple[int, int] = (CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
) -> None:
    """Stream sentences from llm_api POST /generate with finite timeouts."""
    generate_url = resolve_llm_generate_url()
    payload = {
        "prompt": prompt,
        "history": history or [],
        "max_sentences": max_sentences,
    }

    logger.info("Kết nối llm_api tại %s với prompt: %s", generate_url, prompt)

    response = None
    sentence_count = 0
    try:
        response = requests.post(
            generate_url,
            json=payload,
            stream=True,
            timeout=timeout,
        )
        response.raise_for_status()

        for line in response.iter_lines(decode_unicode=True):
            if quit_event.is_set():
                return
            if not line:
                continue

            sentence = line.strip()
            if not sentence:
                continue

            logger.info("[LLM] %s", sentence)
            if on_sentence:
                on_sentence(sentence)

            sentence_count += 1
            if max_iterations is not None and sentence_count >= max_iterations:
                break

        if sentence_count == 0 and not quit_event.is_set():
            raise LLMError(
                "empty_response",
                "Máy chủ AI không phản hồi hoặc trả về nội dung rỗng.",
                generate_url,
            )
    except Exception as exc:
        error = _to_llm_error(exc, generate_url)
        logger.error("Không thể hoàn tất llm_api [%s]: %s", error.kind, error.detail or error.message)
        if on_error:
            on_error(error.to_dict())
        raise error from exc
    finally:
        if response is not None:
            response.close()
        logger.info("Kết thúc proxy llm_api")
