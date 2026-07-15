from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, CommentEvent, GiftEvent, LikeEvent, FollowEvent
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
def _get_default_llm_url() -> str:
    if os.path.exists('config.json'):
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                url = cfg.get("llm_api_base_url") or cfg.get("ollama_base_url")
                if url:
                    return url
        except Exception:
            pass
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

OLLAMA_BASE_URL = os.getenv('LLM_API_BASE_URL') or os.getenv('OLLAMA_BASE_URL', _get_default_llm_url())
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

_debug_event_logged = set()


def _event_value(obj, field):
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(field)
    return getattr(obj, field, None)


def _extract_viewer_count(event) -> int | None:
    fields = (
        'viewer_count', 'viewerCount', 'viewers', 'viewerCountTotal',
        'room_user_count', 'roomUserCount', 'total_user_count', 'user_count',
    )
    for field in fields:
        value = _event_value(event, field)
        if isinstance(value, int) and value >= 0:
            return value

    for nested_name in ('room_info', 'roomInfo', 'live_room', 'liveRoom', 'data'):
        nested = _event_value(event, nested_name)
        for field in fields:
            value = _event_value(nested, field)
            if isinstance(value, int) and value >= 0:
                return value
    return None


def _debug_event_payload(kind: str, event) -> None:
    if kind in _debug_event_logged:
        return
    _debug_event_logged.add(kind)
    try:
        keys = sorted([key for key in vars(event).keys() if not key.startswith('_')])
        print(f'[LIVE EVENT SAMPLE] {kind}: fields={keys}')
    except Exception as exc:
        print(f'[LIVE EVENT SAMPLE] {kind}: unable to inspect payload: {exc}')


def post_live_event(event_type: str, **payload) -> None:
    try:
        payload['type'] = event_type
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            LIVE_APP_URL.rstrip('/') + '/live-event',
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=1):
            pass
    except Exception as exc:
        print(f'WARN: Could not post live stats event {event_type}: {exc}')


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


def _enforce_comment_response(user_name: str, llm_response: str, comment_text: str = '') -> str:
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

    cta = 'Bạn inbox để được tư vấn thêm nhé.'
    if intro_core:
        intro_core = intro_core.lstrip(' ,.-:;')
        return f'{greeting}. {intro_core} {cta}'

    return f'{greeting}. {cta}'


def _build_grounded_comment_reply(user_name: str, comment_text: str) -> str:
    text = _sanitize_tts_text(comment_text).lower()

    if any(keyword in text for keyword in ['giá', 'gia', 'bao nhiêu', 'bao nhieu', 'cost', 'price']):
        return (
            f'Chào {user_name}. Sản phẩm của chúng tôi đang có giá rất tốt. '
            'Bạn inbox để được báo giá chi tiết nhé.'
        )

    if any(keyword in text for keyword in ['ưu đãi', 'uu dai', 'khuyến mãi', 'khuyen mai', 'giảm', 'giam', 'sale', 'deal']):
        return (
            f'Chào {user_name}. Hôm nay shop đang có chương trình ưu đãi cực tốt. '
            'Bạn inbox ngay để nhận ưu đãi nhé.'
        )

    if any(keyword in text for keyword in ['chức năng', 'chuc nang', 'làm gì', 'lam gi', 'công dụng', 'cong dung', 'sản phẩm', 'san pham', 'tư vấn', 'tu van']):
        return (
            f'Chào {user_name}. Sản phẩm của shop chất lượng cao, được nhiều khách hàng tin dùng. '
            'Bạn inbox để được tư vấn chi tiết nhé.'
        )

    if any(keyword in text for keyword in ['hello', 'hi', 'xin chào', 'xin chao', 'chào', 'chao', 'alo', 'hey']):
        return (
            f'Chào {user_name}. Cảm ơn bạn đã ghé thăm livestream. '
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
    """Generate a Vietnamese response for TikTok comment or gift."""
    try:
        current_llm_url = os.getenv('LLM_API_BASE_URL') or os.getenv('OLLAMA_BASE_URL', _get_default_llm_url())
        if event_type == 'gift':
            system_prompt = (
                'Bạn là trợ lý bán hàng livestream trên TikTok. '
                'Khi có người tặng quà, hãy cảm ơn ngắn gọn bằng tiếng Việt, ấm áp, tự nhiên, không emoji, không ký tự đặc biệt. '
                'Có thể mời họ xem sản phẩm đang bán trên livestream.'
            )
            user_message = f'Người dùng {user_name} đã tặng: {event_text}. Hãy cảm ơn họ thật ngắn gọn.'
        else:
            system_prompt = (
                'Bạn là trợ lý bán hàng livestream trên TikTok. '
                'Trả lời bình luận bằng tiếng Việt tự nhiên, ngắn gọn dưới 30 từ, thân thiện như đang livestream bán hàng tư vấn. '
                'Nếu người dùng hỏi giá, mời họ inbox để được báo giá chi tiết. '
                'Nếu người dùng hỏi về sản phẩm, trả lời ngắn gọn và mời inbox để tư vấn thêm. '
                'Nếu người dùng chào hỏi, chào lại thân thiện và mời xem sản phẩm. '
                'Không được xin lỗi dưới bất kỳ hình thức nào, không lặp lời chào, không emoji, không ký tự đặc biệt. '
                'Câu trả lời nên có 1 câu chào theo tên người dùng và 1 câu mời inbox hoặc chốt đơn nếu phù hợp.'
            )
            user_message = f'Comment từ {user_name}: {event_text}.'

            grounded_reply = _build_grounded_comment_reply(user_name, event_text)
            if grounded_reply:
                return grounded_reply

        is_slink = "slink" in current_llm_url or "8080" in current_llm_url
        if is_slink:
            generate_url = current_llm_url.rstrip('/')
            if not generate_url.endswith('/generate'):
                generate_url = f"{generate_url}/generate"
            
            # Construct Slink prompt
            if event_type == 'gift':
                prompt_text = f"Người dùng {user_name} đã tặng {event_text}. Hãy viết một câu cảm ơn ngắn gọn, ấm áp bằng tiếng Việt."
            else:
                prompt_text = (
                    f"Bạn là trợ lý bán hàng livestream trên TikTok. "
                    f"Hãy trả lời bình luận bằng tiếng Việt tự nhiên, cực kỳ ngắn gọn dưới 30 từ, thân thiện.\n"
                    f"Nếu người dùng hỏi giá, mời họ inbox để báo giá chi tiết.\n"
                    f"Nếu người dùng hỏi sản phẩm, trả lời ngắn gọn và mời inbox tư vấn.\n\n"
                    f"Bình luận từ {user_name}: {event_text}\n"
                    f"Trả lời:"
                )
            
            payload = {"prompt": prompt_text, "interval": 1}
            with requests.post(generate_url, json=payload, timeout=15) as r:
                if r.status_code != 200:
                    raise RuntimeError(f"Slink API error {r.status_code}")
                
                extracted_tokens = []
                for line in r.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    line_str = line.strip()
                    if line_str.startswith("data:"):
                        line_str = line_str[5:].strip()
                    if not line_str:
                        continue
                    try:
                        data = json.loads(line_str)
                        if isinstance(data, dict):
                            val = data.get("response") or data.get("text") or data.get("content")
                            if val is None and "choices" in data and isinstance(data["choices"], list) and len(data["choices"]) > 0:
                                choice = data["choices"][0]
                                if isinstance(choice, dict):
                                    val = choice.get("text") or (choice.get("delta", {}).get("content") if "delta" in choice else None) or (choice.get("message", {}).get("content") if "message" in choice else None)
                            if val is not None:
                                extracted_tokens.append(str(val))
                            else:
                                extracted_tokens.append(line_str)
                        else:
                            extracted_tokens.append(str(data))
                    except Exception:
                        extracted_tokens.append(line_str)
                
                # Smart join tokens/sentences
                response = ""
                for part in extracted_tokens:
                    if not response:
                        response = part
                    else:
                        if part.startswith(" ") or part.startswith("\n") or response.endswith(" ") or response.endswith("\n"):
                            response += part
                        else:
                            if (response[-1].isalnum() or response[-1] in ['.', ',', '!', '?', ';', ':']) and part[0].isalnum():
                                response += " " + part
                            else:
                                response += part
                response = response.strip()
        else:
            client_llm.base_url = current_llm_url
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
            response = _enforce_comment_response(user_name, response, event_text)

        if not response.startswith('Cảm ơn') and event_type == 'gift':
            response = f'Cảm ơn {user_name}. {response}'
        return response
    except Exception as e:
        print(f'ERROR: LLM generation failed: {e}')
        if event_type == 'comment':
            return (
                f'Chào {user_name}. Cảm ơn bạn đã ghé thăm livestream. '
                'Bạn inbox để được tư vấn sản phẩm nhé.'
            )
        return f'Cảm ơn {user_name} đã ủng hộ livestream của chúng tôi.'


@client.on(ConnectEvent)
async def on_connect(event: ConnectEvent):
    print(f'Connected to @{event.unique_id} (Room ID: {client.room_id})')
    _debug_event_payload('connect', event)
    post_live_event(
        'connect',
        username=str(event.unique_id).lstrip('@'),
        viewerCount=_extract_viewer_count(event)
    )
    # Emit a machine-readable marker so the controller can detect a successful connection
    try:
        print(f'LIVE:CONNECTED:{event.unique_id}')
    except Exception:
        pass


async def on_comment(event: CommentEvent) -> None:
    user_name = event.user.nickname
    comment_text = event.comment
    print(f'COMMENT: {user_name} -> {comment_text}')
    _debug_event_payload('comment', event)
    post_live_event('comment', viewerCount=_extract_viewer_count(event))

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


async def on_like(event: LikeEvent) -> None:
    user_name = event.user.nickname
    like_count = event.count
    print(f'LIKE: {user_name} liked x{like_count}')
    _debug_event_payload('like', event)
    post_live_event('like', count=like_count, viewerCount=_extract_viewer_count(event))

    tts_text = f'Cảm ơn {user_name} đã thả {like_count} tim cho chúng tôi.'
    if send_to_tts(tts_text, event=True, priority=1):
        print('[OK] Like TTS sent')
    else:
        print('[ERR] Like TTS failed')


client.add_listener(LikeEvent, on_like)


async def on_follow(event: FollowEvent) -> None:
    user_name = event.user.nickname
    print(f'FOLLOW: {user_name} followed')

    tts_text = f'Chào mừng {user_name} đã theo dõi kênh. Cảm ơn bạn rất nhiều nhé.'
    if send_to_tts(tts_text, event=True, priority=0):
        print('[OK] Follow TTS sent')
    else:
        print('[ERR] Follow TTS failed')


client.add_listener(FollowEvent, on_follow)


if __name__ == '__main__':
    print('Starting TikTok Live listener...')
    print(f'   Sending TTS to: {LIVE_APP_URL}')
    print(f'   LLM Model: {OLLAMA_MODEL}')
    client.run()
