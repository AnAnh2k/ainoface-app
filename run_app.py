import os
import sys
import subprocess
import time
import urllib.request
import runpy
import webbrowser
import json
import shutil
import threading
import tempfile

# Force UTF-8 mode as early as possible. The UI still uses Vietnamese text,
# but fallback logging must never crash on Windows cp1252 consoles.
os.environ.setdefault('PYTHONUTF8', '1')
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

def configure_utf8_stream(stream):
    if not stream:
        return stream
    try:
        stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    except Exception:
        pass
    return stream

configure_utf8_stream(sys.stdout)
configure_utf8_stream(sys.stderr)

def safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        safe_args = [
            str(arg).encode('utf-8', errors='backslashreplace').decode('ascii', errors='backslashreplace')
            for arg in args
        ]
        print(*safe_args, **kwargs)

# Setup local Model caching directory on the client machine
if getattr(sys, 'frozen', False):
    app_dir = os.path.dirname(sys.executable)
else:
    app_dir = os.path.dirname(os.path.abspath(__file__))

# Point HF cache directory to the local folder inside our app directory
cache_dir = os.path.join(app_dir, "tts_model_cache")
os.environ["HF_HOME"] = cache_dir
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Hybrid Offline Check: If model weights are already cached, force offline mode to skip online update checks
model_exists = False
hub_dir = os.path.join(cache_dir, "hub", "models--pnnbao-ump--VieNeu-TTS-v3-Turbo")
if os.path.exists(hub_dir):
    snapshots_dir = os.path.join(hub_dir, "snapshots")
    if os.path.exists(snapshots_dir) and os.path.isdir(snapshots_dir):
        try:
            if len(os.listdir(snapshots_dir)) > 0:
                model_exists = True
        except Exception:
            pass

if model_exists:
    safe_print("Local model weights detected. Ready for startup.")
else:
    safe_print("Local model weights not found. Online mode active for first-run download.")

# Handle subprocess execution for Flask and FastAPI
if len(sys.argv) > 1:
    arg = sys.argv[1]
    if arg == "--run-flask":
        # Add subdirectory paths so Flask can find modules
        sys.path.append(os.path.abspath(os.path.join(app_dir, 'live_noface')))
        from live_noface.app import app as flask_app
        flask_app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False, threaded=True)
        sys.exit(0)
    elif arg == "--run-fastapi":
        # Add subdirectory paths so FastAPI can find modules
        sys.path.append(os.path.abspath(os.path.join(app_dir, 'test_vieneu')))
        from test_vieneu.main import app as fastapi_app
        import uvicorn
        uvicorn.run(fastapi_app, host='127.0.0.1', port=8005, loop="asyncio", log_level="warning")
        sys.exit(0)
    elif arg == "--run-live":
        sys.path.append(os.path.abspath(os.path.join(app_dir, 'live_noface')))
        runpy.run_module('live_noface.live', run_name='__main__')
        sys.exit(0)
    elif arg == "--run-updater":
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('--pid', type=int, required=True)
        parser.add_argument('--package', default='')
        parser.add_argument('--installer', default='')
        parser.add_argument('--restart', required=True)
        args = parser.parse_args(sys.argv[2:])
        update_package = args.package or args.installer

        def read_updater_json_file(path, default=None):
            try:
                with open(path, 'r', encoding='utf-8-sig') as f:
                    return json.load(f)
            except Exception:
                return default if default is not None else {}

        def updater_state_path():
            base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
            state_dir = os.path.join(base, 'SLiveAI')
            os.makedirs(state_dir, exist_ok=True)
            return os.path.join(state_dir, 'update_state.json')

        def pid_exists(pid):
            if pid <= 0:
                return False
            if sys.platform.startswith('win'):
                result = subprocess.run(
                    ['tasklist', '/FI', f'PID eq {pid}'],
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                return str(pid) in result.stdout
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False

        def find_update_source_dir(extract_dir):
            candidates = []
            for root, dirs, files in os.walk(extract_dir):
                if 'Live_AI_SLive.exe' in files:
                    candidates.append(root)

            if not candidates:
                raise RuntimeError('Update package does not contain Live_AI_SLive.exe.')

            candidates.sort(key=lambda item: (0 if os.path.basename(item).lower() == 'live_ai_slive' else 1, len(item)))
            return candidates[0]

        def copy_update_tree(source_dir, target_dir):
            if not os.path.exists(os.path.join(source_dir, 'version.json')):
                raise RuntimeError('Update package is missing version.json.')

            for name in os.listdir(source_dir):
                src = os.path.join(source_dir, name)
                dst = os.path.join(target_dir, name)
                if os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)

        deadline = time.time() + 60
        while time.time() < deadline and pid_exists(args.pid):
            time.sleep(0.5)

        try:
            package_lower = update_package.lower()
            if package_lower.endswith('.zip'):
                target_dir = os.path.dirname(args.restart)
                extract_dir = tempfile.mkdtemp(prefix='slive_update_', dir=os.path.dirname(update_package))
                shutil.unpack_archive(update_package, extract_dir, 'zip')
                source_dir = find_update_source_dir(extract_dir)
                copy_update_tree(source_dir, target_dir)
                installed_version = read_updater_json_file(os.path.join(source_dir, 'version.json'), {}).get('version')
                if installed_version:
                    state = {
                        'installedVersion': str(installed_version),
                        'installedAt': time.strftime('%Y-%m-%dT%H:%M:%S')
                    }
                    with open(updater_state_path(), 'w', encoding='utf-8') as f:
                        json.dump(state, f, ensure_ascii=False, indent=2)
            else:
                installer_cmd = [update_package, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART']
                subprocess.run(installer_cmd, check=False)

            if os.path.exists(args.restart):
                subprocess.Popen([args.restart], close_fds=True)
        finally:
            try:
                if update_package and os.path.exists(update_package):
                    os.remove(update_package)
            except Exception:
                pass
            try:
                if 'extract_dir' in locals() and os.path.exists(extract_dir):
                    shutil.rmtree(extract_dir, ignore_errors=True)
            except Exception:
                pass
        sys.exit(0)

# Main launcher process logic below
def get_subprocess_cmd(arg):
    if getattr(sys, 'frozen', False):
        return [sys.executable, arg]
    else:
        return [sys.executable, os.path.abspath(__file__), arg]

flask_proc = None
fastapi_proc = None
flask_log_file = None
fastapi_log_file = None
main_window = None
update_api = None
shutting_down = False

def check_server_ready(url):
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=1) as response:
            return response.status == 200
    except Exception:
        return False


def read_json_file(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def local_state_dir():
    base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    state_dir = os.path.join(base, 'SLiveAI')
    os.makedirs(state_dir, exist_ok=True)
    return state_dir


def update_state_path():
    return os.path.join(local_state_dir(), 'update_state.json')


def version_file_candidates():
    candidates = [
        os.path.join(app_dir, 'version.json'),
        os.path.join(app_dir, '_internal', 'version.json'),
        os.path.join(os.getcwd(), 'version.json')
    ]
    bundle_dir = getattr(sys, '_MEIPASS', '')
    if bundle_dir:
        candidates.append(os.path.join(bundle_dir, 'version.json'))
    return candidates


def read_current_version():
    versions = []
    for path in version_file_candidates():
        version_data = read_json_file(path, {})
        version = str(version_data.get('version') or '')
        if version:
            versions.append(version)

    state_data = read_json_file(update_state_path(), {})
    installed_version = str(state_data.get('installedVersion') or '')
    if installed_version:
        versions.append(installed_version)

    if not versions:
        return '1.0.0'
    return max(versions, key=parse_semver)
def parse_semver(version):
    parts = str(version or '0.0.0').strip().split('.')
    numbers = []
    for part in parts[:3]:
        digits = ''.join(ch for ch in part if ch.isdigit())
        numbers.append(int(digits or 0))
    while len(numbers) < 3:
        numbers.append(0)
    return tuple(numbers)


def is_newer_version(latest, current):
    return parse_semver(latest) > parse_semver(current)


def read_central_api_url():
    cfg = read_json_file(os.path.join(app_dir, 'config.json'), {})
    return str(cfg.get('central_api_url') or 'http://127.0.0.1:5050').rstrip('/')


def check_for_update():
    try:
        current_version = read_current_version()
        latest_url = read_central_api_url() + '/api/desktop/latest'
        req = urllib.request.Request(latest_url, method='GET')
        with urllib.request.urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode('utf-8'))
        latest_version = str(data.get('version') or '')
        download_url = str(data.get('downloadUrl') or '')
        if not latest_version or not download_url:
            return None
        if not is_newer_version(latest_version, current_version):
            return None
        return {
            'currentVersion': current_version,
            'version': latest_version,
            'required': bool(data.get('required')),
            'downloadUrl': download_url,
            'releaseNotes': data.get('releaseNotes') or ''
        }
    except Exception as exc:
        safe_print(f"Update check skipped: {exc}")
        return None


def js_call(window, script):
    if not window:
        return
    try:
        window.evaluate_js(script)
    except Exception as exc:
        safe_print(f"WARN: Could not update WebView UI: {exc}")


def navigate_window(window, url):
    if not window:
        return
    try:
        window.load_url(url)
    except Exception as exc:
        safe_print(f"WARN: Could not navigate WebView: {exc}")


def get_main_window():
    return main_window


def js_string(value):
    return json.dumps(str(value or ''))


def local_updates_dir():
    base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    updates = os.path.join(base, 'SLiveAI', 'updates')
    os.makedirs(updates, exist_ok=True)
    return updates




def prepare_updater_executable():
    updates_dir = local_updates_dir()
    updater_dir = tempfile.mkdtemp(prefix='updater_runtime_', dir=updates_dir)
    updater_path = os.path.join(updater_dir, 'SLiveAIUpdater.exe')
    shutil.copy2(sys.executable, updater_path)

    internal_src = os.path.join(os.path.dirname(sys.executable), '_internal')
    internal_dst = os.path.join(updater_dir, '_internal')
    if os.path.isdir(internal_src):
        shutil.copytree(internal_src, internal_dst)

    return updater_path


def download_update(window, info):
    try:
        if not getattr(sys, 'frozen', False):
            js_call(window, 'setUpdateError("Cập nhật chỉ chạy trên bản exe đã build.")')
            return

        url = info.get('downloadUrl') or ''
        filename = os.path.basename(url.split('?', 1)[0]) or f"Live_AI_SLive_Update_{info.get('version')}.zip"
        package_path = os.path.join(local_updates_dir(), filename)
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=30) as response:
            total = int(response.headers.get('Content-Length') or 0)
            downloaded = 0
            with open(package_path, 'wb') as f:
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    percent = int((downloaded / total) * 100) if total else 0
                    js_call(window, f'setUpdateProgress({percent}, {downloaded}, {total})')

        js_call(window, 'setUpdateStatus("Đã tải xong. Đang khởi động trình cập nhật...")')
        updater_path = prepare_updater_executable()
        subprocess.Popen([
            updater_path,
            '--run-updater',
            '--pid', str(os.getpid()),
            '--package', package_path,
            '--restart', sys.executable
        ], close_fds=True)
        time.sleep(0.5)
        shutdown_app(exit_app=True)
    except Exception as exc:
        js_call(window, f'setUpdateError({js_string(str(exc))})')


class UpdateApi:
    def __init__(self):
        self.info = None
        self.started = False

    def get_version_info(self):
        update_info = check_for_update()
        if update_info:
            self.info = update_info
        return {
            'success': True,
            'currentVersion': read_current_version(),
            'update': update_info
        }

    def start_update(self, info=None):
        if info:
            self.info = info
        if not self.info:
            self.info = check_for_update()
        if not self.info:
            return {'success': False, 'error': 'Không có bản cập nhật mới.'}
        self.started = True
        threading.Thread(target=download_update, args=(get_main_window(), self.info), daemon=True).start()
        return {'success': True}

    def skip_update(self):
        navigate_window(get_main_window(), 'http://127.0.0.1:5000')
        return {'success': True}

def initialize_app(window):
    global flask_proc, fastapi_proc, flask_log_file, fastapi_log_file
    safe_print("Starting background Live AI processes...")
    
    # 1. Update status: Starting background services
    js_call(window, 'updateStatus("Đang khởi động dịch vụ nền...", 10)')
    
    # Create logs directory inside the app folder
    log_dir = os.path.join(app_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    flask_log_file = open(os.path.join(log_dir, "flask.log"), "w", encoding="utf-8")
    fastapi_log_file = open(os.path.join(log_dir, "fastapi.log"), "w", encoding="utf-8")

    # Start Flask and FastAPI as separate OS subprocesses with UTF-8 environment
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'

    flask_proc = subprocess.Popen(
        get_subprocess_cmd("--run-flask"), 
        env=env,
        stdout=flask_log_file, 
        stderr=flask_log_file,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform.startswith('win') else 0
    )
    js_call(window, 'updateStatus("Đang khởi chạy dịch vụ Web...", 25)')
    
    fastapi_proc = subprocess.Popen(
        get_subprocess_cmd("--run-fastapi"), 
        env=env,
        stdout=fastapi_log_file, 
        stderr=fastapi_log_file,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform.startswith('win') else 0
    )
    js_call(window, 'updateStatus("Đang tải mô hình giọng nói AI (Lần đầu khởi động có thể mất 1-2 phút)...", 40)')

    # Poll servers until they are ready
    flask_ready = False
    fastapi_ready = False
    
    # We will poll for up to 180 seconds (3 minutes) to allow downloading model weights on first run
    max_attempts = 360  # 360 * 0.5s = 180s
    progress = 40
    
    for attempt in range(max_attempts):
        # Check if subprocesses crashed
        if flask_proc.poll() is not None:
            js_call(window, 'showError("Dịch vụ Web (Flask) bị tắt đột ngột. Vui lòng kiểm tra logs/flask.log")')
            return
            
        if fastapi_proc.poll() is not None:
            js_call(window, 'showError("Dịch vụ Giọng nói AI (FastAPI) bị lỗi. Vui lòng kiểm tra logs/fastapi.log")')
            return

        if not flask_ready:
            flask_ready = check_server_ready('http://127.0.0.1:5000/login')
            if flask_ready:
                progress = max(progress, 55)
                js_call(window, f'updateStatus("Dịch vụ Web đã sẵn sàng. Đang đợi tải mô hình AI...", {progress})')
                
        if not fastapi_ready:
            fastapi_ready = check_server_ready('http://127.0.0.1:8005/')
            if fastapi_ready:
                progress = max(progress, 85)
                js_call(window, f'updateStatus("Mô hình AI đã sẵn sàng!", {progress})')
                
        if flask_ready and fastapi_ready:
            break
            
        # Gradually increase progress to show activity (e.g. from 40 to 90)
        if not fastapi_ready:
            # Slow progress crawl from 40% to 90% over 180 seconds
            progress = min(90, 40 + int((attempt / max_attempts) * 50))
            js_call(window, f'updateStatus("Đang tải mô hình giọng nói AI (Lần đầu chạy có thể mất 1-2 phút)...", {progress})')
            
        time.sleep(0.5)

    if not flask_ready or not fastapi_ready:
        js_call(window, 'showError("Không thể kết nối các dịch vụ nền sau 3 phút. Vui lòng kiểm tra logs/fastapi.log")')
        return

    safe_print("Services are ready. Finishing progress bar...")
    js_call(window, 'setComplete()')
    time.sleep(0.6)  # Wait for progress bar animation to complete smoothly
    
    update_info = check_for_update()
    if update_info and update_api:
        update_api.info = update_info
        js_call(window, f'showUpdateModal({json.dumps(update_info, ensure_ascii=False)})')
        return

    safe_print("Loading main application interface...")
    navigate_window(window, 'http://127.0.0.1:5000')


def terminate_process(proc, name):
    if not proc or proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            if sys.platform.startswith('win'):
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                proc.kill()
        except Exception as exc:
            safe_print(f"WARN: Could not kill {name}: {exc}")


def shutdown_app(exit_app=False):
    global shutting_down
    if shutting_down:
        return
    shutting_down = True
    safe_print("Shutting down Live AI processes...")

    try:
        req = urllib.request.Request('http://127.0.0.1:5000/internal/shutdown-live', data=b'{}', method='POST')
        req.add_header('Content-Type', 'application/json')
        urllib.request.urlopen(req, timeout=2).read()
    except Exception:
        pass

    terminate_process(flask_proc, 'Flask')
    terminate_process(fastapi_proc, 'FastAPI')

    for log_file in (flask_log_file, fastapi_log_file):
        try:
            if log_file:
                log_file.close()
        except Exception:
            pass

    if exit_app:
        os._exit(0)


class BrowserFallbackWindow:
    def evaluate_js(self, script):
        safe_print(f"[STARTUP] {script}")

    def load_url(self, url):
        safe_print(f"Opening browser fallback: {url}")
        webbrowser.open(url)


def cleanup_processes():
    shutdown_app(exit_app=False)


def wait_for_browser_fallback():
    try:
        while True:
            if flask_proc and flask_proc.poll() is not None:
                break
            if fastapi_proc and fastapi_proc.poll() is not None:
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    splash_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {
                margin: 0;
                padding: 0;
                background-color: #0f172a;
                color: #f1f5f9;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                height: 100vh;
                overflow: hidden;
            }
            .container {
                text-align: center;
                width: 80%;
                max-width: 450px;
            }
            h1 {
                font-size: 26px;
                font-weight: 700;
                margin-bottom: 8px;
                letter-spacing: 0.5px;
                background: linear-gradient(135deg, #3b82f6, #06b6d4);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            p {
                color: #94a3b8;
                font-size: 14px;
                margin-bottom: 28px;
            }
            .progress-container {
                background-color: #1e293b;
                border-radius: 9999px;
                height: 8px;
                width: 100%;
                overflow: hidden;
                position: relative;
                margin-bottom: 12px;
            }
            .progress-bar {
                background: linear-gradient(90deg, #3b82f6, #06b6d4);
                height: 100%;
                width: 0%;
                border-radius: 9999px;
                transition: width 0.4s ease-out;
            }
            .percentage {
                color: #3b82f6;
                font-size: 14px;
                font-weight: 600;
            }
            .error-text {
                color: #ef4444 !important;
                font-weight: 600;
            }
            .update-modal {
                position: fixed;
                inset: 0;
                display: none;
                align-items: center;
                justify-content: center;
                background: rgba(2, 6, 23, 0.78);
                padding: 24px;
            }
            .update-card {
                width: min(520px, 100%);
                background: #111827;
                border: 1px solid #334155;
                border-radius: 18px;
                box-shadow: 0 24px 80px rgba(0, 0, 0, 0.45);
                padding: 24px;
                text-align: left;
            }
            .update-card h2 {
                margin: 0 0 12px;
                font-size: 22px;
                color: #22d3ee;
            }
            .update-card p {
                margin: 6px 0;
                color: #cbd5e1;
                line-height: 1.5;
            }
            .update-notes {
                margin-top: 12px;
                padding: 12px;
                background: #0f172a;
                border-radius: 10px;
                white-space: pre-wrap;
                color: #e2e8f0;
            }
            .update-actions {
                display: flex;
                gap: 12px;
                justify-content: flex-end;
                margin-top: 18px;
            }
            .update-actions button {
                border: 0;
                border-radius: 10px;
                padding: 11px 16px;
                font-weight: 700;
                cursor: pointer;
            }
            .update-primary {
                background: #06b6d4;
                color: #06121a;
            }
            .update-secondary {
                background: #1e293b;
                color: #e2e8f0;
            }
            .download-box {
                display: none;
                margin-top: 16px;
            }
            .download-bar {
                height: 10px;
                background: #1e293b;
                border-radius: 999px;
                overflow: hidden;
            }
            .download-fill {
                width: 0%;
                height: 100%;
                background: linear-gradient(90deg, #22d3ee, #3b82f6);
                transition: width 0.2s ease;
            }
            .download-meta {
                margin-top: 8px;
                color: #94a3b8;
                font-size: 13px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>HỆ THỐNG LIVE AI - S LIVE</h1>
            <p id="status-text">Đang khởi động dịch vụ nền...</p>
            <div class="progress-container">
                <div class="progress-bar" id="progress-bar"></div>
            </div>
            <div class="percentage" id="percentage">0%</div>
        </div>

        <script>
            let bar = document.getElementById('progress-bar');
            let text = document.getElementById('percentage');
            let statusLabel = document.getElementById('status-text');

            function updateStatus(statusText, percentage) {
                statusLabel.textContent = statusText;
                bar.style.width = percentage + '%';
                text.textContent = percentage + '%';
            }

            function showError(errorText) {
                statusLabel.textContent = errorText;
                statusLabel.classList.add('error-text');
                bar.style.background = '#ef4444';
                bar.style.width = '100%';
                text.textContent = 'LỖI';
                text.style.color = '#ef4444';
            }

            function setComplete() {
                statusLabel.textContent = "Khởi động hoàn tất!";
                bar.style.width = '100%';
                text.textContent = '100%';
            }

            function formatBytes(bytes) {
                if (!bytes) return '0 MB';
                const mb = bytes / 1024 / 1024;
                return mb.toFixed(mb >= 10 ? 1 : 2) + ' MB';
            }

            function showUpdateModal(info) {
                window.updateInfo = info;
                document.getElementById('update-modal').style.display = 'flex';
                document.getElementById('update-title').textContent = 'Đã có phiên bản mới ' + info.version;
                document.getElementById('update-version').textContent = 'Phiên bản hiện tại: ' + info.currentVersion + ' - Phiên bản mới: ' + info.version;
                document.getElementById('update-notes').textContent = info.releaseNotes || 'Bản cập nhật mới đã sẵn sàng.';
                document.getElementById('later-btn').style.display = info.required ? 'none' : 'inline-block';
                updateStatus('Đang chờ xác nhận cập nhật...', 100);
            }

            function startUpdate() {
                document.getElementById('download-box').style.display = 'block';
                document.getElementById('update-btn').disabled = true;
                document.getElementById('later-btn').disabled = true;
                setUpdateStatus('Đang tải bản cập nhật...');
                window.pywebview.api.start_update();
            }

            function skipUpdate() {
                document.getElementById('update-modal').style.display = 'none';
                window.pywebview.api.skip_update();
            }

            function setUpdateProgress(percent, downloaded, total) {
                const safePercent = Math.max(0, Math.min(100, percent || 0));
                document.getElementById('download-fill').style.width = safePercent + '%';
                const totalText = total ? ' / ' + formatBytes(total) : '';
                document.getElementById('download-meta').textContent = 'Đang tải: ' + safePercent + '% - ' + formatBytes(downloaded) + totalText;
            }

            function setUpdateStatus(message) {
                document.getElementById('download-meta').textContent = message;
            }

            function setUpdateError(message) {
                document.getElementById('update-btn').disabled = false;
                document.getElementById('later-btn').disabled = false;
                document.getElementById('update-btn').textContent = 'Thử lại';
                document.getElementById('download-meta').textContent = 'Lỗi cập nhật: ' + message;
            }
        </script>
        <div class="update-modal" id="update-modal">
            <div class="update-card">
                <h2 id="update-title">Đã có phiên bản mới</h2>
                <p id="update-version"></p>
                <div class="update-notes" id="update-notes"></div>
                <div class="download-box" id="download-box">
                    <div class="download-bar"><div class="download-fill" id="download-fill"></div></div>
                    <div class="download-meta" id="download-meta">Đang tải bản cập nhật...</div>
                </div>
                <div class="update-actions">
                    <button class="update-secondary" id="later-btn" onclick="skipUpdate()">Để sau</button>
                    <button class="update-primary" id="update-btn" onclick="startUpdate()">Cập nhật ngay</button>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

    try:
        import webview
        update_api = UpdateApi()
        window = webview.create_window(
            title='Hệ thống Live AI - S Live',
            html=splash_html,
            width=1280,
            height=850,
            resizable=True,
            js_api=update_api
        )
        main_window = window

        # Locate icon file for window
        icon_path = None
        if getattr(sys, 'frozen', False):
            possible_paths = [
                os.path.join(app_dir, "_internal", "live_noface", "static", "favicon.ico"),
                os.path.join(app_dir, "live_noface", "static", "favicon.ico"),
            ]
            for p in possible_paths:
                if os.path.exists(p):
                    icon_path = p
                    break
        else:
            icon_path = os.path.join(app_dir, "icon.ico")
            if not os.path.exists(icon_path):
                icon_path = os.path.join(app_dir, "live_noface", "static", "favicon.ico")

        # Run webview start without debug=True to prevent opening devtools automatically
        webview.start(initialize_app, window, icon=icon_path)
    except Exception as exc:
        safe_print(f"Webview startup failed, using browser fallback: {exc}")
        initialize_app(BrowserFallbackWindow())
        wait_for_browser_fallback()
    finally:
        cleanup_processes()
