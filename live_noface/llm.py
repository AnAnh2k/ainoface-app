import logging
import os
import json
import time
from typing import Callable, Optional
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Default to Slink LLM API
LLM_API_BASE_URL = os.getenv(
    "LLM_API_BASE_URL",
    os.getenv("OLLAMA_BASE_URL", "http://autolive.slink.ai.vn:8080"),
)

UNREAD_COUNT = 0

def _generate_url(base: str) -> str:
    base = base.rstrip("/")
    if "11434" in base or "api/generate" in base:
        if base.endswith("/api/generate"):
            return base
        return f"{base}/api/generate"
    if base.endswith("/generate"):
        return base
    return f"{base}/generate"

def llm_continuous(
    prompt: str,
    quit_event,
    datainfo: Optional[dict] = None,
    on_token: Optional[Callable[[str], None]] = None,
    on_sentence: Optional[Callable[[str], None]] = None,
    max_iterations: Optional[int] = None,
    interval: int = 1,
) -> None:
    """Proxy tới llm_api /generate hoặc Ollama /api/generate."""
    generate_url = _generate_url(LLM_API_BASE_URL)
    is_ollama = "11434" in generate_url or "api/generate" in generate_url

    if is_ollama:
        # qwen2.5:1.5b là model cân bằng tốt nhất giữa tốc độ trên CPU và chất lượng tiếng Việt chính xác
        model_name = os.getenv("LLM_MODEL", "qwen2.5:1.5b")
        
        system_instruction = (
            "Bạn là một MC kiêm streamer livestream bán hàng và tâm sự trên TikTok, giọng điệu vui vẻ, hoạt ngôn, tự nhiên, gần gũi, sử dụng văn phong nói tiếng Việt. "
            "Hãy viết một kịch bản nói chuyện livestream dài, cuốn hút, chia làm nhiều câu ngắn dễ đọc về chủ đề được yêu cầu. "
            "Tránh viết các ký tự đặc biệt không đọc được. Hãy bắt đầu nói chuyện ngay lập tức, không chào hỏi khuôn mẫu kiểu trợ lý AI.\n"
            "YÊU CẦU QUAN TRỌNG: BẮT BUỘC phải sinh kịch bản bằng TIẾNG VIỆT 100%. Tuyệt đối KHÔNG viết bằng tiếng Anh."
        )
        
        sentence_count = 0
        iteration = 0
        
        # Vòng lặp vô hạn sinh text liên tục để livestream nói liên tục nhiều giờ
        while not quit_event.is_set():
            if iteration > 0:
                time.sleep(1)
                # Thay đổi prompt gợi ý theo từng vòng lặp để mô hình nói tiếp mà không bị trùng lặp nội dung
                if iteration == 1:
                    sub_prompt = f"Hãy tiếp tục kịch bản livestream bằng tiếng Việt về chủ đề '{prompt}'. Kể thêm câu chuyện thực tế hoặc chia sẻ kinh nghiệm thú vị liên quan."
                elif iteration == 2:
                    sub_prompt = f"Hãy tiếp tục chia sẻ bằng tiếng Việt về chủ đề '{prompt}'. Trả lời một vài câu hỏi tưởng tượng từ khán giả trong khung chat về chủ đề này."
                else:
                    sub_prompt = f"Hãy tiếp tục nói thêm bằng tiếng Việt các khía cạnh độc đáo, bài học hoặc mẹo bổ ích khác liên quan đến '{prompt}'."
                
                full_prompt = f"{system_instruction}\n\nYêu cầu nói tiếp: {sub_prompt}\n\n[BẮT BUỘC VIẾT TIẾNG VIỆT] Nói tiếp:"
            else:
                full_prompt = f"{system_instruction}\n\nChủ đề livestream: {prompt}\n\n[BẮT BUỘC VIẾT TIẾNG VIỆT] Bắt đầu nói:"

            payload = {
                "model": model_name,
                "prompt": full_prompt,
                "stream": True
            }

            logger.info("Kết nối Ollama (Vòng %d) tại %s với model %s", iteration + 1, generate_url, model_name)
            
            try:
                with requests.post(
                    generate_url,
                    json=payload,
                    stream=True,
                    timeout=(10, 20),
                ) as resp:
                    if resp.status_code != 200:
                        raise RuntimeError(f"Ollama API error {resp.status_code}: {resp.text}")

                    sentence_buffer = ""
                    for line in resp.iter_lines(decode_unicode=True):
                        if quit_event.is_set():
                            break
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            token = data.get("response", "")
                            
                            # Stream token về giao diện ngay lập tức
                            if token and on_token:
                                on_token(token)
                                
                            sentence_buffer += token
                            
                            # Tách câu khi gặp dấu chấm, chấm hỏi, chấm than hoặc xuống dòng.
                            # Tách thêm ở dấu phẩy, chấm phẩy, hai chấm nếu câu con đã dài hơn 50 ký tự để giảm độ trễ TTS.
                            i = 0
                            while i < len(sentence_buffer):
                                char = sentence_buffer[i]
                                is_split = char in ['.', '?', '!', '\n']
                                if not is_split and char in [',', ';', ':'] and i > 50:
                                    is_split = True
                                # Tách ở khoảng trắng nếu câu quá dài không có dấu câu (> 90 ký tự)
                                if not is_split and char == ' ' and i > 90:
                                    is_split = True
                                    
                                if is_split:
                                    is_decimal = False
                                    if char == '.' and i > 0 and i < len(sentence_buffer) - 1:
                                        if sentence_buffer[i-1].isdigit() and sentence_buffer[i+1].isdigit():
                                            is_decimal = True
                                    
                                    if not is_decimal:
                                        sentence = sentence_buffer[:i+1].strip()
                                        sentence_buffer = sentence_buffer[i+1:]
                                        i = -1
                                        
                                        if sentence:
                                            logger.info("[Ollama Sentence] %s", sentence)
                                            if on_sentence:
                                                on_sentence(sentence)
                                            sentence_count += 1
                                            
                                            # Tạm dừng đọc từ socket nếu số câu chưa đọc trên giao diện >= 35
                                            while UNREAD_COUNT >= 35 and not quit_event.is_set():
                                                time.sleep(0.2)
                                                
                                            if max_iterations is not None and sentence_count >= max_iterations:
                                                break
                                i += 1
                            
                            if max_iterations is not None and sentence_count >= max_iterations:
                                break
                        except Exception as e:
                            logger.error("Error parsing Ollama chunk: %s", e)
                    
                    leftover = sentence_buffer.strip()
                    if leftover and not quit_event.is_set():
                        if max_iterations is None or sentence_count < max_iterations:
                            logger.info("[Ollama Leftover] %s", leftover)
                            if on_sentence:
                                on_sentence(leftover)
                                
            except Exception as e:
                logger.error("Lỗi trong vòng lặp Ollama: %s", e)
                time.sleep(2)
            
            # Đợi hàng đợi trống bớt trước khi bắt đầu vòng lặp sinh câu mới
            while UNREAD_COUNT >= 35 and not quit_event.is_set():
                time.sleep(0.2)
                
            iteration += 1
            if max_iterations is not None and sentence_count >= max_iterations:
                break
    else:
        # API Slink Server cũ
        payload = {"prompt": prompt, "interval": interval}
        logger.info("Kết nối Slink tại %s với payload: %s", generate_url, payload)
        try:
            with requests.post(
                generate_url,
                json=payload,
                stream=True,
                timeout=(10, 20),
            ) as resp:
                if resp.status_code != 200:
                    raise RuntimeError(f"Slink API error {resp.status_code}")

                sentence_count = 0
                for line in resp.iter_lines(decode_unicode=True):
                    if quit_event.is_set():
                        break
                    if not line:
                        continue

                    sentence = line.strip()
                    if not sentence:
                        continue

                    logger.info("[Slink Sentence] %s", sentence)
                    if on_token:
                        on_token(sentence + " ")
                    if on_sentence:
                        on_sentence(sentence)

                    sentence_count += 1
                    if max_iterations is not None and sentence_count >= max_iterations:
                        break
        except Exception as exc:
            logger.error("Lỗi Slink: %s", exc)
        finally:
            logger.info("Kết thúc Slink proxy")
