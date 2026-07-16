import os
import sys
import subprocess
import time
import urllib.request
import runpy
import webbrowser

# Force UTF-8 for stdout and stderr to avoid encoding crashes on Windows
if sys.stdout:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if sys.stderr:
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

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
    print("Local model weights detected. Ready for startup.")
else:
    print("Local model weights not found. Online mode active for first-run download.")

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

def check_server_ready(url):
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=1) as response:
            return response.status == 200
    except Exception:
        return False

def initialize_app(window):
    global flask_proc, fastapi_proc, flask_log_file, fastapi_log_file
    print("Starting background Live AI processes...")
    
    # 1. Update status: Starting background services
    window.evaluate_js('updateStatus("Đang khởi động dịch vụ nền...", 10)')
    
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
    window.evaluate_js('updateStatus("Đang khởi chạy cổng dịch vụ Web...", 25)')
    
    fastapi_proc = subprocess.Popen(
        get_subprocess_cmd("--run-fastapi"), 
        env=env,
        stdout=fastapi_log_file, 
        stderr=fastapi_log_file,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform.startswith('win') else 0
    )
    window.evaluate_js('updateStatus("Đang tải mô hình giọng nói AI (Lần đầu khởi động có thể mất 1-2 phút)...", 40)')

    # Poll servers until they are ready
    flask_ready = False
    fastapi_ready = False
    
    # We will poll for up to 180 seconds (3 minutes) to allow downloading model weights on first run
    max_attempts = 360  # 360 * 0.5s = 180s
    progress = 40
    
    for attempt in range(max_attempts):
        # Check if subprocesses crashed
        if flask_proc.poll() is not None:
            window.evaluate_js('showError("Dịch vụ Web (Flask) bị tắt đột ngột. Vui lòng kiểm tra logs/flask.log")')
            return
            
        if fastapi_proc.poll() is not None:
            window.evaluate_js('showError("Dịch vụ Giọng nói AI (FastAPI) bị lỗi. Vui lòng kiểm tra logs/fastapi.log")')
            return

        if not flask_ready:
            flask_ready = check_server_ready('http://127.0.0.1:5000/login')
            if flask_ready:
                progress = max(progress, 55)
                window.evaluate_js(f'updateStatus("Dịch vụ Web đã sẵn sàng. Đang đợi tải mô hình AI...", {progress})')
                
        if not fastapi_ready:
            fastapi_ready = check_server_ready('http://127.0.0.1:8005/')
            if fastapi_ready:
                progress = max(progress, 85)
                window.evaluate_js(f'updateStatus("Mô hình AI đã sẵn sàng!", {progress})')
                
        if flask_ready and fastapi_ready:
            break
            
        # Gradually increase progress to show activity (e.g. from 40 to 90)
        if not fastapi_ready:
            # Slow progress crawl from 40% to 90% over 180 seconds
            progress = min(90, 40 + int((attempt / max_attempts) * 50))
            window.evaluate_js(f'updateStatus("Đang tải mô hình giọng nói AI (Lần đầu chạy có thể mất 1-2 phút)...", {progress})')
            
        time.sleep(0.5)

    if not flask_ready or not fastapi_ready:
        window.evaluate_js('showError("Không thể kết nối các dịch vụ nền sau 3 phút. Vui lòng kiểm tra logs/fastapi.log")')
        return

    print("Services are ready. Finishing progress bar...")
    window.evaluate_js('setComplete()')
    time.sleep(0.6)  # Wait for progress bar animation to complete smoothly
    
    print("Loading main application interface...")
    window.load_url('http://127.0.0.1:5000')

class BrowserFallbackWindow:
    def evaluate_js(self, script):
        print(f"[STARTUP] {script}")

    def load_url(self, url):
        print(f"Opening browser fallback: {url}")
        webbrowser.open(url)


def cleanup_processes():
    print("Terminating background processes...")
    if flask_proc:
        flask_proc.terminate()
    if fastapi_proc:
        fastapi_proc.terminate()

    if flask_log_file:
        flask_log_file.close()
    if fastapi_log_file:
        fastapi_log_file.close()


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
        </script>
    </body>
    </html>
    """

    try:
        import webview
        window = webview.create_window(
            title='Hệ Thống Live AI - S Live',
            html=splash_html,
            width=1280,
            height=850,
            resizable=True
        )

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
        print(f"Webview startup failed, using browser fallback: {exc}")
        initialize_app(BrowserFallbackWindow())
        wait_for_browser_fallback()
    finally:
        cleanup_processes()
