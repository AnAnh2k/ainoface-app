# Live AI Desktop

Ứng dụng desktop Python cho khách hàng dùng Live AI: giao diện Flask, tiến trình TikTok Live client, dịch vụ TTS FastAPI/VieNeu và cửa sổ desktop bằng PyWebView.

## Yêu cầu môi trường

- Git
- Python 3.13.x, đang kiểm tra trên `Python 3.13.13`
- pip
- Internet trong lần chạy đầu để tải model VieNeu TTS nếu chưa có cache
- Backend `liveai-backend` nếu chạy theo môi trường local

## Clone project

```powershell
git clone https://github.com/vulevanslink/liveai-desktop.git
cd liveai-desktop
```

## Tạo môi trường ảo

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

Nếu PowerShell chặn kích hoạt venv:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.\.venv\Scripts\activate
```

## Cài thư viện

```powershell
pip install -r live_noface\requirements.txt
pip install -r test_vieneu\requirements.txt
pip install pywebview pyinstaller
```

`pywebview` dùng để mở app dưới dạng cửa sổ desktop. Nếu PyWebView lỗi, launcher có cơ chế fallback mở bằng trình duyệt.

## Cấu hình backend và LLM

App dùng file `config.json` ở thư mục gốc. Nếu chưa có, app sẽ tự tạo file mặc định.

Ví dụ cấu hình local:

```json
{
  "central_api_url": "http://127.0.0.1:5050",
  "llm_api_base_url": "https://your-llm-api.example.com",
  "desktop_device_id": "auto-generated"
}
```

Có thể override backend bằng biến môi trường:

```powershell
$env:AINOFACE_CENTRAL_API_URL="http://127.0.0.1:5050"
```

Có thể override LLM bằng:

```powershell
$env:LLM_API_BASE_URL="https://your-llm-api.example.com"
$env:LIVE_LLM_API_KEY="your_api_key"
```

## Chạy development

Chạy launcher chính:

```powershell
python run_app.py
```

Launcher sẽ tự khởi động:

- Flask web app: `http://127.0.0.1:5000`
- FastAPI TTS service: `http://127.0.0.1:8005`
- Cửa sổ desktop PyWebView hoặc browser fallback

Log runtime nằm trong:

```text
logs/flask.log
logs/fastapi.log
```

## Chạy từng service riêng để debug

```powershell
python run_app.py --run-flask
python run_app.py --run-fastapi
python run_app.py --run-live
```

## Build app desktop

Repo có sẵn spec:

- `Live_AI_SLive.spec`
- `live_client.spec`

Có thể build bằng script:

```powershell
python build.py
```

Hoặc chạy PyInstaller thủ công theo spec nếu cần debug build:

```powershell
pyinstaller --clean --noconfirm Live_AI_SLive.spec
pyinstaller --clean --noconfirm live_client.spec
```

Thư mục build thường nằm ở:

```text
dist/
build/
```

## Cache model TTS

Model VieNeu được cache trong:

```text
tts_model_cache/
```

Nếu cache đã có model, app ưu tiên chạy nhanh hơn ở lần sau. Thư mục này không nên commit lên Git vì dung lượng lớn.

## Phiên bản thư viện đang dùng

Theo `live_noface/requirements.txt`:

- `requests`: `>=2.0`
- `Flask`: `>=3.1.3`
- `TikTokLive`: `>=6.6.5`
- `openai`: `>=2.44.0`

Theo `test_vieneu/requirements.txt`:

- `vieneu`: `>=3.0.11`
- `sea-g2p`: `>=0.7.18`
- `fastapi`: `>=0.139.0`
- `uvicorn`: `>=0.50.0`
- `numpy`: `==1.26.4`
- `soundfile`: `>=0.14.0`

Thư viện runtime/build cần cài thêm:

- `pywebview`: dùng cho cửa sổ desktop
- `pyinstaller`: dùng đóng gói `.exe`

## Luồng chạy tổng thể

1. Backend trung tâm xử lý tài khoản, số dư thời gian, hóa đơn và admin.
2. Desktop app đăng nhập qua backend trung tâm.
3. Flask hiển thị UI local ở port `5000`.
4. FastAPI/VieNeu sinh giọng nói ở port `8005`.
5. Live client đọc bình luận TikTok, gọi LLM, gọi TTS và phát audio.
