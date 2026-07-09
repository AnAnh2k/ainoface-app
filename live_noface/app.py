import os
import time
import json
import threading
import subprocess
import sys

# Load configuration and initialize LLM API base URLs in environment variables
CONFIG_PATH = 'config.json'
DEFAULT_CENTRAL_API_URL = "https://ainoface-backend.onrender.com"
DEFAULT_LLM_URL = "https://luck-tvs-schedules-palace.trycloudflare.com"

if not os.environ.get("LLM_API_BASE_URL") and not os.environ.get("OLLAMA_BASE_URL"):
    llm_url = DEFAULT_LLM_URL
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                llm_url = cfg.get("llm_api_base_url") or cfg.get("ollama_base_url") or DEFAULT_LLM_URL
        except Exception:
            pass
    os.environ["LLM_API_BASE_URL"] = llm_url
    os.environ["OLLAMA_BASE_URL"] = llm_url

from queue import Queue, Empty
from collections import deque
from flask import Flask, render_template, request, jsonify, Response, session, redirect, url_for
try:
    from live_noface.llm import llm_continuous
except ImportError:
    from llm import llm_continuous

try:
    from live_noface.utils.tts import call_tts_service as _call_tts_service, stream_tts_audio
except ImportError:
    try:
        from .utils.tts import call_tts_service as _call_tts_service, stream_tts_audio
    except ImportError:
        from utils.tts import call_tts_service as _call_tts_service, stream_tts_audio


_tts_cache = {}
def call_tts_service(text: str, voice: str = 'Trúc Ly') -> tuple[bytes, str, int]:
    cache_key = (text, voice)
    if cache_key in _tts_cache:
        print(f"[CACHE HIT] Returning cached TTS for: '{text[:20]}...'")
        return _tts_cache[cache_key]
    result = _call_tts_service(text, voice)
    if len(_tts_cache) > 50:
        _tts_cache.pop(next(iter(_tts_cache)))
    _tts_cache[cache_key] = result
    return result

import urllib.error
import urllib.request
import re

def split_text_into_sentences(text: str) -> list[str]:
    if not text:
        return []
    # Tách theo các ký tự .!? hoặc dòng mới đi kèm khoảng trắng ở sau
    raw_sentences = re.split(r'(?<=[.!?\n])\s+', text)
    sentences = []
    for s in raw_sentences:
        trimmed = s.strip()
        if not trimmed:
            continue
        # Nếu câu quá dài (> 100 ký tự), tiếp tục tách ở dấu phẩy hoặc chấm phẩy có khoảng trắng phía sau
        if len(trimmed) > 100:
            sub_parts = re.split(r'(?<=[,;])\s+', trimmed)
            temp = ""
            for part in sub_parts:
                if len(temp + part) > 100:
                    if temp.strip():
                        sentences.append(temp.strip())
                    temp = part
                else:
                    temp += (" " if temp else "") + part
            if temp.strip():
                sentences.append(temp.strip())
        else:
            sentences.append(trimmed)
    return sentences

app = Flask(__name__)

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

CONFIG_PATH = 'config.json'

def load_or_create_config():
    if not os.path.exists(CONFIG_PATH):
        config_data = {
            "central_api_url": "https://ainoface-backend.onrender.com"
        }
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4)
            
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config_data = json.load(f)
        
    if "central_api_url" not in config_data:
        config_data["central_api_url"] = "https://ainoface-backend.onrender.com"
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4)
            
    return config_data

config = load_or_create_config()
app.secret_key = os.urandom(24)

# Cấu hình bảo mật nâng cao cho Session Cookie
app.config.update(
    SESSION_COOKIE_SECURE=True,      # Chỉ gửi cookie qua kết nối HTTPS (localhost được trình duyệt miễn trừ)
    SESSION_COOKIE_HTTPONLY=True,    # Ngăn chặn client-side JavaScript truy cập cookie session
    SESSION_COOKIE_SAMESITE='Lax'    # Hạn chế cookie gửi đi trong request chéo trang (CSRF protection)
)

CENTRAL_API_URL = os.getenv("AINOFACE_CENTRAL_API_URL", config.get("central_api_url", "http://127.0.0.1:5050")).rstrip("/")

def call_central_api(endpoint, method='GET', data=None, token=None):
    url = f"{CENTRAL_API_URL}{endpoint}"
    req_data = None
    if data:
        req_data = json.dumps(data).encode('utf-8')
    
    req = urllib.request.Request(url, data=req_data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
        
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = response.read().decode('utf-8')
            return json.loads(res_data), response.status
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8') if hasattr(e, 'read') else str(e)
        try:
            return json.loads(body), e.code
        except:
            return {'success': False, 'error': body or str(e)}, e.code
    except urllib.error.URLError:
        return {
            'success': False,
            'error': 'Không kết nối được server. Vui lòng kiểm tra backend.'
        }, 503
    except TimeoutError:
        return {
            'success': False,
            'error': 'Không kết nối được server. Vui lòng kiểm tra backend.'
        }, 503
    except Exception as e:
        return {'success': False, 'error': str(e)}, 500

# Global queue for audio stream
tts_queue = Queue()
comments_queue = Queue()
live_stats_lock = threading.Lock()
live_stats = {
    'connected': False,
    'username': None,
    'currentViewers': None,
    'commentEvents': deque(),
    'heartEvents': deque(),
    'ordersCount': None,
    'lastEventAt': None,
}
# Process handle for the external live listener
live_process = None


def parse_tiktok_username(value: str) -> str:
    raw = (value or '').strip()
    if not raw:
        return ''
    match = re.search(r'@([A-Za-z0-9_.]+)', raw)
    if match:
        return match.group(1).strip('._')
    raw = raw.split('?', 1)[0].split('#', 1)[0].rstrip('/')
    if '/' in raw:
        raw = raw.rsplit('/', 1)[-1]
    raw = raw.lstrip('@').strip()
    if not re.fullmatch(r'[A-Za-z0-9_.]{2,24}', raw):
        return ''
    return raw.strip('._')


def tiktok_connect_error_response(status_code=500):
    return jsonify({
        'success': False,
        'error': 'Không thể khởi động bộ kết nối TikTok Live. Vui lòng kiểm tra cài đặt hoặc thử lại.'
    }), status_code


def reset_live_stats(username=None, connected=False):
    with live_stats_lock:
        live_stats['connected'] = connected
        live_stats['username'] = username
        live_stats['currentViewers'] = None
        live_stats['commentEvents'].clear()
        live_stats['heartEvents'].clear()
        live_stats['ordersCount'] = None
        live_stats['lastEventAt'] = time.time() if connected else None


def prune_live_stats(now=None):
    now = now or time.time()
    cutoff = now - 60
    while live_stats['commentEvents'] and live_stats['commentEvents'][0] < cutoff:
        live_stats['commentEvents'].popleft()
    while live_stats['heartEvents'] and live_stats['heartEvents'][0][0] < cutoff:
        live_stats['heartEvents'].popleft()


def live_stats_snapshot():
    with live_stats_lock:
        prune_live_stats()
        hearts_per_minute = sum(item[1] for item in live_stats['heartEvents'])
        return {
            'success': True,
            'connected': live_stats['connected'],
            'username': live_stats['username'],
            'currentViewers': live_stats['currentViewers'],
            'commentsPerMinute': len(live_stats['commentEvents']),
            'heartsPerMinute': hearts_per_minute,
            'ordersCount': live_stats['ordersCount'],
            'lastEventAt': live_stats['lastEventAt'],
        }

@app.before_request
def require_login():
    if request.endpoint == 'static':
        return
    if request.path in ('/login', '/logout', '/register'):
        return
    if request.path in ('/human', '/live-event'):
        # Allow TikTok Live local listener process to call /human
        if request.remote_addr in ('127.0.0.1', '::1', 'localhost'):
            return
            
    if not session.get('logged_in'):
        # If it's an API request, return 401 JSON error instead of redirecting
        if request.path.startswith(('/api/', '/stream', '/tts', '/add-tts', '/start-live', '/stop-live', '/comments-stream', '/audio-stream', '/set-unread-count')):
            return jsonify({'success': False, 'error': 'Yêu cầu đăng nhập để tiếp tục.'}), 401
        return redirect(url_for('login'))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/set-unread-count', methods=['POST'])
def set_unread_count():
    import live_noface.llm as llm
    data = request.get_json(silent=True) or {}
    count = int(data.get('count', 0))
    llm.UNREAD_COUNT = count
    return jsonify({'success': True, 'count': count})

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    res_data, status_code = call_central_api('/api/auth/register', method='POST', data=data)
    if status_code == 201 and res_data.get('success') and res_data.get('token'):
        session['logged_in'] = True
        session['auth_token'] = res_data.get('token')
        user_data = res_data.get('user') or {}
        session['username'] = user_data.get('username') or data.get('username', '').strip()
        session.permanent = True
    return jsonify(res_data), status_code

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        # Authenticate via central API
        res_data, status_code = call_central_api('/api/auth/login', method='POST', data={'username': username, 'password': password})
        
        if status_code == 200 and res_data.get('success'):
            session['logged_in'] = True
            session['auth_token'] = res_data.get('token')
            session['username'] = res_data.get('username')
            session.permanent = True
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': res_data.get('error') or 'Tài khoản hoặc mật khẩu không chính xác.'}), status_code
            
    if session.get('logged_in'):
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    # End session on central API if active
    session_id = session.get('session_id')
    auth_token = session.get('auth_token')
    if session_id and auth_token:
        call_central_api('/api/billing/session/end', method='POST', data={'sessionId': session_id}, token=auth_token)
    session.clear()
    return redirect(url_for('login'))

@app.route('/api/session/start', methods=['POST'])
def session_start():
    auth_token = session.get('auth_token')
    if not auth_token:
        return jsonify({'success': False, 'error': 'Yêu cầu đăng nhập.'}), 401
    
    data = request.get_json(silent=True) or {}
    res_data, status_code = call_central_api('/api/billing/session/start', method='POST', data=data, token=auth_token)
    if status_code == 200 and res_data.get('success'):
        session['session_id'] = res_data.get('sessionId')
    return jsonify(res_data), status_code

@app.route('/api/session/heartbeat', methods=['POST'])
def session_heartbeat():
    auth_token = session.get('auth_token')
    if not auth_token:
        return jsonify({'success': False, 'error': 'Yêu cầu đăng nhập.'}), 401
    
    session_id = session.get('session_id')
    if not session_id:
        return jsonify({'success': False, 'error': 'Không tìm thấy phiên làm việc.'}), 400
        
    res_data, status_code = call_central_api('/api/billing/session/heartbeat', method='POST', data={'sessionId': session_id}, token=auth_token)
    # If expired, clear session_id
    if res_data.get('status') in ('expired', 'ended', 'stopped', 'locked') or res_data.get('action') in ('stop_live', 'force_logout'):
        session.pop('session_id', None)
    return jsonify(res_data), status_code

@app.route('/api/session/end', methods=['POST'])
def session_end():
    auth_token = session.get('auth_token')
    if not auth_token:
        return jsonify({'success': False, 'error': 'Yêu cầu đăng nhập.'}), 401
    
    session_id = session.get('session_id')
    if not session_id:
        return jsonify({'success': False, 'error': 'Không tìm thấy phiên làm việc.'}), 400
        
    res_data, status_code = call_central_api('/api/billing/session/end', method='POST', data={'sessionId': session_id}, token=auth_token)
    session.pop('session_id', None)
    return jsonify(res_data), status_code

@app.route('/api/user/profile', methods=['GET'])
def user_profile():
    auth_token = session.get('auth_token')
    if not auth_token:
        return jsonify({'success': False, 'error': 'Yêu cầu đăng nhập.'}), 401
    
    res_data, status_code = call_central_api('/api/user/profile', method='GET', token=auth_token)
    return jsonify(res_data), status_code


@app.route('/api/live/stats', methods=['GET'])
def api_live_stats():
    return jsonify(live_stats_snapshot())

@app.route('/stream')
def stream():
    prompt = request.args.get('prompt', '').strip()
    if not prompt:
        return 'Prompt không được để trống.', 400

    quit_event = threading.Event()
    sentence_queue = Queue()

    def on_sentence(sentence: str):
        sentence_queue.put({"type": "sentence", "text": sentence})

    def run_continuous():
        import requests
        original_post = requests.post
        error_msg = [None]

        def mock_post(*args, **kwargs):
            try:
                resp = original_post(*args, **kwargs)
                orig_raise = resp.raise_for_status
                def mock_raise():
                    try:
                        orig_raise()
                    except Exception as e:
                        if resp.status_code == 404:
                            error_msg[0] = "Sai endpoint API AI hoặc server AI chưa mở route tạo kịch bản."
                        else:
                            error_msg[0] = f"Lỗi HTTP {resp.status_code} từ máy chủ AI tại {args[0]}."
                        raise e
                resp.raise_for_status = mock_raise
                return resp
            except Exception as e:
                error_msg[0] = f"Không thể kết nối tới máy chủ AI tại {args[0]}. Chi tiết: {str(e)}"
                raise e

        requests.post = mock_post
        
        generated_sentences = []
        def local_on_sentence(sentence):
            generated_sentences.append(sentence)
            on_sentence(sentence)

        try:
            # First call with the base prompt
            llm_continuous(prompt, quit_event, on_sentence=local_on_sentence)
            
            # Loop for subsequent script sentences
            for i in range(12):
                if quit_event.is_set():
                    break
                if error_msg[0]:
                    break
                
                time.sleep(0.3)
                cont_prompt = "Hãy nói tiếp câu thoại tiếp theo của kịch bản livestream ở trên, không lặp lại lời chào hỏi."
                llm_continuous(cont_prompt, quit_event, on_sentence=local_on_sentence, history=generated_sentences[-5:])
                
            if error_msg[0]:
                print(f"[AI ERROR] {error_msg[0]}")
                sentence_queue.put({"type": "ai_error", "text": error_msg[0]})
        except Exception as e:
            if not error_msg[0]:
                error_msg[0] = f"Lỗi gọi AI: {str(e)}"
            print(f"[AI ERROR Exception] {error_msg[0]}")
            sentence_queue.put({"type": "ai_error", "text": error_msg[0]})
        finally:
            requests.post = original_post

    thread = threading.Thread(target=run_continuous, daemon=True)
    thread.start()

    def event_stream():
        sent_any = False
        last_activity = time.time()
        timeout_limit = 20.0  # 20 seconds inactivity timeout
        try:
            while not quit_event.is_set():
                if time.time() - last_activity > timeout_limit:
                    yield f"event: ai_error\ndata: Hết thời gian chờ phản hồi từ máy chủ AI (Timeout).\n\n"
                    break

                try:
                    msg = sentence_queue.get(timeout=1)
                    last_activity = time.time()
                    if msg['type'] in ('sentence', 'token'):
                        sent_any = True
                    yield f"event: {msg['type']}\ndata: {msg['text']}\n\n"
                except Empty:
                    if not thread.is_alive():
                        break
            
            # If the stream finished and we never sent anything, send an error to close connection
            if not sent_any and not quit_event.is_set():
                yield f"event: ai_error\ndata: Máy chủ AI không phản hồi hoặc trả về nội dung rỗng.\n\n"

            while not sentence_queue.empty():
                msg = sentence_queue.get_nowait()
                yield f"event: {msg['type']}\ndata: {msg['text']}\n\n"
        finally:
            quit_event.set()

    return Response(event_stream(), mimetype='text/event-stream')

@app.route('/tts-health', methods=['GET'])
def tts_health():
    try:
        req = urllib.request.Request('http://127.0.0.1:8005/', method='GET')
        with urllib.request.urlopen(req, timeout=2) as response:
            data = json.loads(response.read().decode('utf-8'))
            return jsonify({'success': True, 'status': data.get('status'), 'error': data.get('error')})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@app.route('/tts', methods=['POST'])
def tts():
    payload = request.get_json(silent=True) or {}
    text = (payload.get('text') or '').strip()
    voice = (payload.get('voice') or 'Trúc Ly').strip() or 'Trúc Ly'

    if not text:
        return jsonify({'success': False, 'error': 'Text không được để trống.'}), 400

    try:
        audio_data, content_type, status_code = call_tts_service(text, voice)
        return Response(audio_data, mimetype=content_type)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='ignore') if hasattr(exc, 'read') else str(exc)
        return jsonify({'success': False, 'error': body or str(exc)}), exc.code
    except urllib.error.URLError as exc:
        return jsonify({'success': False, 'error': str(exc) or 'Không thể kết nối tới TTS server'}), 502
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500

@app.route('/human', methods=['POST'])
def human():
    """Endpoint for TikTok live listener to send TTS requests."""
    payload = request.get_json(silent=True) or {}
    text = (payload.get('text') or '').strip()
    
    if not text:
        return jsonify({'code': 1, 'error': 'Text không được để trống.'}), 400

    try:
        # Chỉ cần đẩy text vào comments_queue. Client sẽ tự động lấy và gọi /tts để phát.
        # Điều này giúp giảm 50% thời gian xử lý và phản hồi ngay lập tức cho TikTok listener.
        try:
            comments_queue.put(text)
        except Exception:
            pass
        
        return jsonify({'code': 0, 'success': True}), 200
    except urllib.error.HTTPError as exc:
        body = str(exc)
        return jsonify({'code': 1, 'error': body or str(exc)}), exc.code
    except urllib.error.URLError as exc:
        return jsonify({'code': 1, 'error': str(exc) or 'Không thể kết nối tới TTS server'}), 502
    except Exception as exc:
        return jsonify({'code': 1, 'error': str(exc)}), 500


@app.route('/live-event', methods=['POST'])
def live_event():
    """Receive realtime TikTok event stats from live.py."""
    if request.remote_addr not in ('127.0.0.1', '::1', 'localhost'):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    payload = request.get_json(silent=True) or {}
    event_type = (payload.get('type') or '').strip().lower()
    now = time.time()

    with live_stats_lock:
        prune_live_stats(now)
        if event_type == 'connect':
            live_stats['connected'] = True
            live_stats['username'] = payload.get('username') or live_stats['username']
        elif event_type == 'disconnect':
            live_stats['connected'] = False
        elif event_type == 'comment':
            live_stats['connected'] = True
            live_stats['commentEvents'].append(now)
        elif event_type in ('like', 'heart'):
            live_stats['connected'] = True
            try:
                count = int(payload.get('count') or 1)
            except Exception:
                count = 1
            live_stats['heartEvents'].append((now, max(1, count)))

        viewer_count = payload.get('viewerCount')
        if isinstance(viewer_count, int) and viewer_count >= 0:
            live_stats['currentViewers'] = viewer_count
        live_stats['lastEventAt'] = now

    return jsonify({'success': True})


@app.route('/comments-stream')
def comments_stream():
    """SSE stream cung cấp comments đến web UI."""
    def event_stream():
        try:
            while True:
                try:
                    comment = comments_queue.get(timeout=1)
                    yield f"data: {comment}\n\n"
                except Empty:
                    continue
        finally:
            pass

    return Response(event_stream(), mimetype='text/event-stream')

@app.route('/audio-stream')
def audio_stream():
    """Stream audio chunks từ queue chung."""
    def generate():
        try:
            while True:
                try:
                    msg_type, data = tts_queue.get(timeout=0.5)
                    if msg_type == 'audio':
                        yield data
                    elif msg_type == 'audio_end':
                        break
                except Exception:
                    break
        except Exception:
            pass
    
    return Response(generate(), mimetype='audio/wav')

@app.route('/add-tts', methods=['POST'])
def add_tts():
    """Get audio từ web prompt và ghi vào queue chung."""
    payload = request.get_json(silent=True) or {}
    text = (payload.get('text') or '').strip()
    voice = (payload.get('voice') or 'Trúc Ly').strip() or 'Trúc Ly'
    
    if not text:
        return jsonify({'success': False, 'error': 'Text không được để trống.'}), 400

    try:
        audio_data, _, _ = call_tts_service(text, voice)
        
        print(f'[WEB TTS] Received audio: {len(audio_data)} bytes')
        
        # Stream audio chunks into shared queue
        chunk_size = 4096
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i+chunk_size]
            tts_queue.put(('audio', chunk))
        
        # End of stream marker
        tts_queue.put(('audio_end', None))
        
        return jsonify({'success': True}), 200
    except urllib.error.HTTPError as exc:
        body = str(exc)
        return jsonify({'success': False, 'error': body or str(exc)}), exc.code
    except urllib.error.URLError as exc:
        return jsonify({'success': False, 'error': str(exc) or 'Không thể kết nối tới TTS server'}), 502
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500
@app.route('/start-live', methods=['POST'])
def start_live():
    """Start the `live.py` listener as a subprocess with TIKTOK_USER env var.
    Expects JSON: {"room": "s_live_ai"} or {"username": "s_live_ai"}.
    """
    global live_process
    if live_process is not None and live_process.poll() is None:
        return jsonify({'success': False, 'error': 'Live listener already running.'}), 400

    payload = request.get_json(silent=True) or {}
    room = parse_tiktok_username(payload.get('room') or payload.get('username') or '')
    if not room:
        return jsonify({'success': False, 'error': 'Không kết nối được TikTok Live. Vui lòng kiểm tra username hoặc link live.'}), 400
    reset_live_stats(username=room, connected=False)

    env = os.environ.copy()
    env['TIKTOK_USER'] = room
    # Ensure subprocess uses UTF-8 stdout/stderr on Windows to avoid
    # UnicodeEncodeError when child prints emoji characters.
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    env['PYTHONUNBUFFERED'] = '1'

    try:
        # Determine launch command based on PyInstaller frozen status
        if getattr(sys, 'frozen', False):
            # Reuse the bundled launcher executable; no separate live_client.exe is produced by the spec.
            cmd = [sys.executable, '--run-live']
        else:
            # When in development, run live.py using system python
            app_dir = os.path.dirname(os.path.abspath(__file__))
            live_script = os.path.join(app_dir, 'live.py')
            if not os.path.exists(live_script):
                print(f"[LIVE ERROR] Missing TikTok connector script: {live_script}")
                return tiktok_connect_error_response()
            cmd = [sys.executable, live_script]

        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
        )
        live_process = proc
    except FileNotFoundError as e:
        print(f"[LIVE ERROR] TikTok connector command not found: {e}")
        return tiktok_connect_error_response()
    except Exception as e:
        print(f"[LIVE ERROR] Failed to start TikTok connector: {e}")
        return tiktok_connect_error_response()

    # Wait for a live-ready marker from stdout
    start_t = time.time()
    marker = f'LIVE:CONNECTED:'
    stdout_lines = []
    stderr_lines = []
    timeout = 10.0
    try:
        while time.time() - start_t < timeout:
            # Read a line if available
            line = ''
            try:
                line = proc.stdout.readline()
            except Exception:
                line = ''
            if line:
                stdout_lines.append(line.strip())
                if marker in line:
                    with live_stats_lock:
                        live_stats['connected'] = True
                        live_stats['username'] = room
                        live_stats['lastEventAt'] = time.time()
                    return jsonify({'success': True}), 200
            else:
                # no new stdout; check stderr
                try:
                    err_line = proc.stderr.readline()
                except Exception:
                    err_line = ''
                if err_line:
                    stderr_lines.append(err_line.strip())
                if proc.poll() is not None:
                    break
                time.sleep(0.1)
    except Exception:
        pass

    # If we get here, marker not found; collect any remaining output and return error
    try:
        out_rem = proc.stdout.read()
        err_rem = proc.stderr.read()
        if out_rem:
            stdout_lines.append(out_rem.strip())
        if err_rem:
            stderr_lines.append(err_rem.strip())
    except Exception:
        pass

    msg = '\n'.join(stderr_lines or stdout_lines) or 'No live connection marker received.'
    print(f"[LIVE ERROR] {msg}")
    friendly_msg = "Không thể kết nối với phiên live TikTok. Vui lòng kiểm tra lại Username TikTok hoặc kết nối mạng của bạn."
    return jsonify({'success': False, 'error': friendly_msg}), 500


@app.route('/stop-live', methods=['POST'])
def stop_live():
    """Stop the running live.py subprocess if any."""
    global live_process
    if live_process is None or live_process.poll() is not None:
        live_process = None
        return jsonify({'success': False, 'error': 'No live listener running.'}), 400
    try:
        live_process.terminate()
        try:
            live_process.wait(timeout=5)
        except Exception:
            live_process.kill()
        live_process = None
        reset_live_stats()
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
