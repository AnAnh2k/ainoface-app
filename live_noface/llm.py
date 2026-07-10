import logging
import os
from typing import Callable, Optional

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

import json

def _get_default_llm_url() -> str:
    # Thử đọc từ config.json ở thư mục làm việc hiện tại
    if os.path.exists('config.json'):
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                url = cfg.get("llm_api_base_url") or cfg.get("ollama_base_url")
                if url:
                    return url
        except Exception:
            pass
    # Thử đọc từ thư mục cha (trường hợp chạy từ bên trong live_noface)
    elif os.path.exists('../config.json'):
        try:
            with open('../config.json', 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                url = cfg.get("llm_api_base_url") or cfg.get("ollama_base_url")
                if url:
                    return url
        except Exception:
            pass
    return "https://luck-tvs-schedules-palace.trycloudflare.com"

LLM_API_BASE_URL = os.getenv(
    "LLM_API_BASE_URL",
    os.getenv("OLLAMA_BASE_URL", _get_default_llm_url()),
)


def _generate_url(base: str) -> str:
    base = base.rstrip("/")
    if base.endswith("/generate"):
        return base
    return f"{base}/generate"


def llm_continuous(
    prompt: str,
    quit_event,
    datainfo: Optional[dict] = None,
    on_sentence: Optional[Callable[[str], None]] = None,
    max_iterations: Optional[int] = None,
    history: Optional[list[str]] = None,
) -> None:
    """Proxy mỏng tới llm_api POST /generate; câu đã được llm_api tách sẵn."""
    generate_url = _generate_url(LLM_API_BASE_URL)
    payload = {
        "prompt": prompt,
        "history": history or []
    }

    logger.info("Kết nối llm_api tại %s với prompt: %s", generate_url, prompt)

    try:
        with requests.post(
            generate_url,
            json=payload,
            stream=True,
            timeout=(10, None),
        ) as resp:
            resp.raise_for_status()

            sentence_count = 0
            for line in resp.iter_lines(decode_unicode=True):
                if quit_event.is_set():
                    break
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

    except requests.exceptions.RequestException as exc:
        logger.error("Không thể kết nối llm_api: %s", exc)
    except Exception:
        logger.exception("llm_continuous exception:")
    finally:
        logger.info("Kết thúc proxy llm_api")
