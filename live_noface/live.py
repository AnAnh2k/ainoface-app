from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, CommentEvent, GiftEvent
import os
import sys
import json
import re

# Force sys.stdout and sys.stderr to UTF-8 with character replacement on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import urllib.request
import urllib.error
import requests
from openai import OpenAI

# Configuration
LIVE_APP_URL = os.getenv('LIVE_APP_URL', 'http://127.0.0.1:5000')
OLLAMA_BASE_URL = os.getenv('LLM_API_BASE_URL') or os.getenv('OLLAMA_BASE_URL', 'http://autolive.slink.ai.vn:8080')
OLLAMA_MODEL = 'qwen2.5:3b'

# Create the client
# Allow overriding the TikTok user via environment variable `TIKTOK_USER`
# or via the first command-line argument.
unique_id = (os.getenv('TIKTOK_USER') or (sys.argv[1] if len(sys.argv) > 1 else '@s_live_ai')).strip()

# Extract username if a full URL (containing @username) is provided
if '@' in unique_id:
    match = re.search(r'@([a-zA-Z0-9_.]+)', unique_id)
    if match:
        unique_id = '@' + match.group(1)
else:
    unique_id = '@' + unique_id
client: TikTokLiveClient = TikTokLiveClient(unique_id=unique_id)
client_llm = OpenAI(
    api_key=os.getenv('OLLAMA_API_KEY', 'ollama'),
    base_url=OLLAMA_BASE_URL,
)


def _sanitize_tts_text(text: str) -> str:
    """Remove emojis and collapse whitespace so TTS stays clean and stable."""
    text = text.replace('\n', ' ').replace('\r', ' ')
    text = re.sub(r'[\U0001F300-\U0001FAFF\u2600-\u27BF]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _first_sentence(text: str) -> str:
    """Keep only the first sentence to force concise livestream replies."""
    text = _sanitize_tts_text(text)
    parts = re.split(r'(?<=[.!?])\s+', text)
    first = parts[0].strip() if parts else text
    return first.rstrip('.!?') + '.' if first else ''


def _clean_comment_reply(text: str, user_name: str) -> str:
    """Remove apology/self-intro phrases and repeated greetings from model output."""
    text = _sanitize_tts_text(text)
    text = text.replace('```', ' ')
    name_parts = [part for part in re.split(r'\s+|[-–—]+', user_name) if part]
    name_parts = name_parts[:3]
    if name_parts:
        for size in range(len(name_parts), 0, -1):
            fragment = ' '.join(name_parts[:size])
            text = re.sub(r'^' + re.escape(fragment) + r'\b[,.:!?-]?\s*', '', text, flags=re.IGNORECASE).strip()
    if name_parts:
        for part in name_parts:
            text = re.sub(r'\b' + re.escape(part) + r'\b[,.:!?-]?\s*', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'\b(xin lỗi|xin loi|tôi xin lỗi|toi xin loi|rất xin lỗi|rat xin loi)\b[^,.:!?]*[,.:!?]?\s*', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'^(chào|hello|hi)\s+' + re.escape(user_name) + r'\s*[,.:!?]?\s*', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'^(chào|hello|hi)\b\s*(chào|hello|hi)?\b\s*', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'\b(chào|hello|hi)\b[,.:!?]?\s*', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'\b(tôi là|toi la|mình là|minh la|của tôi|cua toi|của mình|cua minh)\b[^,.:!?]*[,.:!?]?\s*', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'`+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _enforce_ivy_comment_response(user_name: str, llm_response: str, comment_text: str = '') -> str:
    """Keep replies concise, on-brand, and ready for TTS."""
    cleaned = _clean_comment_reply(llm_response, user_name)
    greeting = f'Chào {user_name}'

    intro_core = _first_sentence(cleaned)
    intro_core = re.sub(r'^(chào|hello|hi)\b[^,]*,?\s*', '', intro_core, flags=re.IGNORECASE).strip()
    intro_lower = intro_core.lower()

    name_parts = [part for part in re.split(r'\s+|[-–—]+', user_name) if part]
    if name_parts:
        first_name_fragment = name_parts[0].lower()
        if intro_lower == first_name_fragment or intro_lower.startswith(first_name_fragment + ' '):
            intro_core = ''

    cta = 'Bạn inbox để được tư vấn cho bé nhé.'
    if intro_core:
        intro_core = intro_core.lstrip(' ,.-:;')
        return f'{greeting}. {intro_core} {cta}'

    return f'{greeting}. {cta}'


def _build_grounded_comment_reply(user_name: str, comment_text: str) -> str:
    text = _sanitize_tts_text(comment_text).lower()

    if any(keyword in text for keyword in ['giá', 'gia', 'bao nhiêu', 'bao nhieu', 'cost', 'price']):
        return (
            f'Chào {user_name}. Bộ Bát Đĩa của chúng tôi mua lẻ từ 10 đến 15 nghìn một món. '
            'Bộ Combo 6 món chỉ 30 nghìn, tiết kiệm hơn so với mua lẻ. '
            'Hôm nay giảm thêm 10% cho 50 khách đầu tiên chốt đơn. Bạn inbox để được tư vấn nhé.'
        )

    if any(keyword in text for keyword in ['ưu đãi', 'uu dai', 'khuyến mãi', 'khuyen mai', 'giảm', 'giam', 'sale', 'deal']):
        return (
            f'Chào {user_name}. Hôm nay Bộ Bát Đĩa có ưu đãi cực tốt. '
            'Giảm ngay 10% cho 50 khách đầu tiên chốt đơn, hỗ trợ phí ship lên đến 30 nghìn, cam kết 1 đổi 1 hoặc hoàn tiền 100% nếu bị bể vỡ trong vận chuyển. '
            'Bạn inbox để giữ ưu đãi nhé.'
        )

    if any(keyword in text for keyword in ['chức năng', 'chuc nang', 'làm gì', 'lam gi', 'công dụng', 'cong dung', 'sản phẩm', 'san pham', 'bát', 'đĩa', 'tư vấn', 'tu van']):
        return (
            f'Chào {user_name}. Bộ Bát Đĩa tối giản sang trọng. '
            'Sứ an toàn nung 1000 độ, khử sạch chì, chống trầy xước, chịu lò vi sóng lò nướng máy rửa bát. '
            'Ngoài ra còn lớp men nano chống bám dầu mỡ, rửa vô cùng nhanh và sạch, nâng tầm không gian bàn ăn. '
            'Bạn inbox để được tư vấn nhé.'
        )

    if any(keyword in text for keyword in ['hello', 'hi', 'xin chào', 'xin chao', 'chào', 'chao', 'alo', 'hey']):
        return (
            f'Chào {user_name}. Chúng tôi bán Bộ Bát Đĩa chất lượng cao, giá tốt nhất. '
            'Bạn inbox để được tư vấn nhé.'
        )

    return ''


def send_to_tts(text: str, sessionid: str = 'current', event: bool = False, priority: int | bool = None) -> bool:
    """Send text to LiveTalking app via /human endpoint for TTS."""
    try:
        url = LIVE_APP_URL.rstrip('/') + '/human'
        payload_data = {
            'type': 'echo',
            'text': text,
            'sessionid': sessionid,
            'interrupt': False
        }
        if event:
            payload_data['event'] = False
        if priority is not None:
            payload_data['priority'] = priority
        payload = json.dumps(payload_data).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            success = data.get('code') == 0
            if not success:
                print(f'ERROR: Live TTS endpoint returned error: {data}')
            return success
    except urllib.error.URLError as e:
        print(f'ERROR: Could not reach LiveTalking app at {LIVE_APP_URL}: {e}')
    except Exception as e:
        print(f'ERROR: Error sending text to TTS: {e}')
    return False


def generate_live_response(user_name: str, event_text: str, event_type: str = 'comment') -> str:
    """Generate a Vietnamese response for TikTok comment or gift using gemma3:1b."""
    try:
        if event_type == 'gift':
            system_prompt = (
                'Bạn là Robot Ivy, robot trợ lý ảo hỗ trợ học tập thông minh. '
                'Khi có người tặng quà, hãy cảm ơn ngắn gọn bằng tiếng Việt, ấm áp, tự nhiên, không emoji, không ký tự đặc biệt. '
                'Có thể nhắc rất ngắn gọn rằng Ivy là người bạn gia sư công nghệ đồng hành cùng học sinh, sinh viên.'
            )
            user_message = f'Người dùng {user_name} đã tặng: {event_text}. Hãy cảm ơn họ thật ngắn gọn.'
        else:
            system_prompt = (
                'Bạn là Robot Ivy, robot trợ lý ảo hỗ trợ học tập thông minh, nhỏ gọn và đáng yêu. '
                'Ivy là người bạn gia sư công nghệ cho học sinh, sinh viên. '
                'Trả lời bình luận bằng tiếng Việt tự nhiên, ngắn gọn, đúng ý người dùng, thân thiện như đang livestream bán hàng tư vấn. '
                'Phải luôn bám các thông tin sản phẩm sau: '
                'Robot Ivy giải đáp kiến thức 24/7 các môn Toán, Lý, Hóa, Văn, Anh... từ cơ bản đến nâng cao. '
                'Ivy luyện giao tiếp ngoại ngữ, nói chuyện bằng tiếng Anh hoặc ngôn ngữ khác, có thể sửa lỗi phát âm trực tiếp. '
                'Ivy hỗ trợ quản lý thời gian, nhắc nhở học tập, lập thời khóa biểu, Pomodoro, và hạn chế nghiện điện thoại. '
                'Ivy có thể tự tạo quiz nhanh để kiểm tra và ôn tập sau giờ học. '
                'Giá robot vật lý là 499.000đ mua đứt trọn đời. Phí dịch vụ AI là 99.000đ mỗi tháng để duy trì bộ não AI. '
                'Khi cần học nhiều có thể đóng tiền dùng, lúc nghỉ hè hoặc không dùng nữa thì ngừng đóng, không ràng buộc, không phát sinh chi phí ẩn. '
                'Ưu đãi hôm nay: giảm ngay 10% cho 50 khách hàng đầu tiên bấm vào giỏ hàng chốt đơn Robot Ivy, và miễn phí dùng thử full tính năng nâng cao trong 3 ngày đầu tiên. '
                'Nếu người dùng hỏi giá, phải nêu rõ 499.000đ cho robot và 99.000đ/tháng cho dịch vụ AI. '
                'Nếu người dùng hỏi công dụng, ưu tiên trả lời về học tập, ngoại ngữ, nhắc lịch, Pomodoro và quiz. '
                'Không được xin lỗi dưới bất kỳ hình thức nào, không nói mình là ai ngoài Robot Ivy, không lặp lời chào, không emoji, không ký tự đặc biệt. '
                'Câu trả lời nên có 1 câu chào theo tên người dùng và 1 câu mời inbox hoặc chốt đơn nếu phù hợp.'
            )
            user_message = f'Comment từ {user_name}: {event_text}.'

            grounded_reply = _build_grounded_comment_reply(user_name, event_text)
            if grounded_reply:
                return grounded_reply

        is_slink = "slink" in OLLAMA_BASE_URL or "8080" in OLLAMA_BASE_URL
        if is_slink:
            generate_url = OLLAMA_BASE_URL.rstrip('/')
            if not generate_url.endswith('/generate'):
                generate_url = f"{generate_url}/generate"
            
            # Construct Slink prompt
            if event_type == 'gift':
                prompt_text = f"Người dùng {user_name} đã tặng {event_text}. Hãy viết một câu cảm ơn ngắn gọn, ấm áp bằng tiếng Việt."
            else:
                prompt_text = (
                    f"Bạn là Robot Ivy, robot trợ lý học tập cho học sinh, sinh viên. "
                    f"Hãy trả lời bình luận bằng tiếng Việt tự nhiên, cực kỳ ngắn gọn dưới 30 từ, thân thiện.\n"
                    f"Thông tin sản phẩm:\n"
                    f"- Giá robot: 499.000đ mua đứt trọn đời, phí AI: 99.000đ/tháng.\n"
                    f"- Công dụng: giải đáp học tập 24/7 (Toán, Lý, Hóa, Văn, Anh...), luyện tiếng Anh, Pomodoro.\n"
                    f"- Ưu đãi hôm nay: giảm 10% cho 50 khách đầu tiên, dùng thử full tính năng 3 ngày.\n\n"
                    f"Bình luận từ {user_name}: {event_text}\n"
                    f"Trả lời:"
                )
            
            payload = {"prompt": prompt_text, "interval": 1}
            with requests.post(generate_url, json=payload, timeout=15) as r:
                if r.status_code != 200:
                    raise RuntimeError(f"Slink API error {r.status_code}")
                lines = []
                for line in r.iter_lines(decode_unicode=True):
                    if line:
                        lines.append(line.strip())
                response = " ".join(lines).strip()
        else:
            completion = client_llm.chat.completions.create(
                model=OLLAMA_MODEL,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_message},
                ],
                max_tokens=48,
                temperature=0.3,
                extra_body={
                    'keep_alive': '10m',
                    'options': {
                        'num_predict': 48,
                    },
                },
            )
            response = completion.choices[0].message.content.strip()
        if not response:
            raise ValueError('Empty response from LLM')

        if event_type == 'comment':
            response = _enforce_ivy_comment_response(user_name, response, event_text)

        if not response.startswith('Cảm ơn') and event_type == 'gift':
            response = f'Cảm ơn {user_name}. {response}'
        return response
    except Exception as e:
        print(f'ERROR: LLM generation failed: {e}')
        if event_type == 'comment':
            return (
                f'Chào {user_name}. Robot Ivy giá 499.000đ mua đứt trọn đời, phí AI 99.000đ mỗi tháng. '
                'Hôm nay giảm ngay 10% cho 50 khách đầu tiên và miễn phí dùng thử full tính năng 3 ngày đầu tiên. Bạn inbox để được tư vấn nhé.'
            )
        return f'Cảm ơn {user_name}. Robot Ivy đồng hành cùng bạn học tập thông minh mỗi ngày.'


@client.on(ConnectEvent)
async def on_connect(event: ConnectEvent):
    print(f'Connected to @{event.unique_id} (Room ID: {client.room_id})')
    # Emit a machine-readable marker so the controller can detect a successful connection
    try:
        print(f'LIVE:CONNECTED:{event.unique_id}')
    except Exception:
        pass


async def on_comment(event: CommentEvent) -> None:
    user_name = event.user.nickname
    comment_text = event.comment
    print(f'COMMENT: {user_name} -> {comment_text}')

    ai_response = generate_live_response(user_name, comment_text, event_type='comment')
    print(f'AI Response: {ai_response}')

    if send_to_tts(ai_response, event=True, priority=0):
        print('[OK] Sent to TTS')
    else:
        print('[ERR] Failed to send to TTS')


client.add_listener(CommentEvent, on_comment)


async def on_gift(event: GiftEvent) -> None:
    user_name = event.user.nickname
    gift_name = event.gift.name
    repeat_count = event.repeat_count
    gift_text = f'{gift_name} x{repeat_count}'
    print(f'GIFT: {user_name} sent {gift_text}')

    ai_response = generate_live_response(user_name, gift_text, event_type='gift')
    print(f'AI Response: {ai_response}')

    if send_to_tts(ai_response, event=True, priority=0):
        print('✓ Sent to TTS')
    else:
        print('✗ Failed to send to TTS')


client.add_listener(GiftEvent, on_gift)


if __name__ == '__main__':
    print('Starting TikTok Live listener...')
    print(f'   Sending TTS to: {LIVE_APP_URL}')
    print(f'   LLM Model: {OLLAMA_MODEL}')
    client.run()
