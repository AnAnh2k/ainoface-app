# Hướng Dẫn Chi Tiết Gộp 2 Thư Mục Thành Một App Desktop Duy Nhất (.exe)

Tài liệu này hướng dẫn bạn gộp thư mục giao diện **`live_noface`** và thư mục xử lý giọng đọc **`test_vieneu`** thành một ứng dụng desktop duy nhất. 

Ứng dụng này sẽ:
1. Chạy hoàn toàn ở máy khách hàng (Client), tự khởi động cả giao diện và bộ chuyển giọng nói (TTS) cục bộ mà không bắt máy chủ của bạn chịu tải.
2. Khi mở lên sẽ hiển thị một cửa sổ phần mềm độc lập (không cần mở trình duyệt Chrome/Edge thủ công).
3. Khách hàng tải về giải nén ra là nhấp đúp chạy ngay, không cần cài đặt Python hay thư viện gì khác.

---

## CẤU TRÚC THƯ MỤC DỰ ÁN SAU KHI GỘP

Bạn sẽ tạo một file khởi chạy chính tên là **`run_app.py`** nằm ở thư mục gốc của dự án (`D:\interntaks\Ainofaoce`). Cấu trúc thư mục sẽ như sau:

```text
D:\interntaks\Ainofaoce\
├── live_noface/          # Thư mục chứa giao diện Flask
│   ├── templates/
│   ├── static/
│   ├── app.py
│   └── ...
├── test_vieneu/          # Thư mục chứa API TTS FastAPI
│   ├── main.py
│   └── ...
└── run_app.py            # <-- FILE CHẠY CHÍNH BẠN SẼ TẠO
```

---

## BƯỚC 1: TẠO FILE KHỞI CHẠY CHÍNH (`run_app.py`)

Tạo file [run_app.py](file:///d:/interntaks/Ainofaoce/run_app.py) ở thư mục gốc và dán đoạn mã sau vào. File này có nhiệm vụ khởi động luồng ngầm cho Flask, FastAPI và mở cửa sổ ứng dụng:

```python
import threading
import time
import os
import sys
import uvicorn
import webview

# Thêm đường dẫn các thư mục con vào hệ thống để Python có thể import được code bên trong
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'live_noface')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'test_vieneu')))

from live_noface.app import app as flask_app
from test_vieneu.main import app as fastapi_app

# Thiết lập thư mục tải và lưu Model TTS tự động trên máy khách hàng
# Model sẽ được lưu tại thư mục cài đặt của app (không sợ mất hoặc tải lại nếu cài lại win)
if getattr(sys, 'frozen', False):
    # Nếu đang chạy từ file .exe đóng gói
    app_dir = os.path.dirname(sys.executable)
else:
    # Nếu đang chạy file .py thường
    app_dir = os.path.dirname(os.path.abspath(__file__))

# Cấu hình thư mục cache của HuggingFace nằm ngay tại thư mục App của khách hàng
os.environ["HF_HOME"] = os.path.join(app_dir, "tts_model_cache")

def run_flask():
    """Khởi chạy Flask App trên cổng 5000 dưới nền"""
    # Tắt chế độ debug và reloader khi chạy production/desktop để tránh xung đột luồng
    flask_app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)

def run_fastapi():
    """Khởi chạy FastAPI TTS trên cổng 8005 dưới nền"""
    # Sử dụng asyncio loop tương thích với Windows
    uvicorn.run(fastapi_app, host='127.0.0.1', port=8005, loop="asyncio", log_level="warning")

if __name__ == "__main__":
    print("Đang khởi động các dịch vụ Live AI ngầm...")
    
    # 1. Khởi chạy Flask và FastAPI dưới dạng các luồng ngầm (daemon threads)
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    fastapi_thread = threading.Thread(target=run_fastapi, daemon=True)
    
    flask_thread.start()
    fastapi_thread.start()
    
    # Đợi 3 giây để các server khởi động hoàn tất
    time.sleep(3)
    
    print("Mở cửa sổ ứng dụng Desktop...")
    # 2. Khởi tạo cửa sổ Desktop trỏ đến giao diện Flask ở cổng 5000
    webview.create_window(
        title='Hệ Thống Live AI - S Live', 
        url='http://127.0.0.1:5000', 
        width=1280, 
        height=850,
        resizable=True
    )
    
    # 3. Chạy ứng dụng. Khi người dùng tắt cửa sổ này, toàn bộ tiến trình ngầm sẽ tự động tắt theo
    webview.start()
```

---

## BƯỚC 2: CÀI ĐẶT THƯ VIỆN CẦN THIẾT

Bạn hãy sử dụng terminal trong môi trường ảo của bạn và cài thêm thư viện **`pywebview`** (để tạo cửa sổ App) và **`pyinstaller`** (để đóng gói thành file `.exe`):

1. Mở cửa sổ Terminal của dự án lên.
2. Di chuyển vào thư mục `test_vieneu` và kích hoạt môi trường ảo:
   ```powershell
   cd D:\interntaks\Ainofaoce\test_vieneu
   .\venv\Scripts\activate
   ```
3. Cài đặt các thư viện cần thiết:
   ```powershell
   pip install pywebview pyinstaller
   ```

---

## BƯỚC 3: TIẾN HÀNH ĐÓNG GÓI THÀNH APP DESKTOP (`.exe`)

Sau khi cài đặt xong các thư viện cần thiết ở Bước 2, bạn đứng ở thư mục `app-ainoface` để chạy lệnh đóng gói:

1. Di chuyển vào thư mục `app-ainoface`:
   ```powershell
   cd D:\interntaks\Ainofaoce\app-ainoface
   ```
2. Chạy lệnh đóng gói bằng PyInstaller (đoạn mã này tự động sao lưu cấu hình `config.json` cũ để tránh bị xóa sạch khi đóng gói lại):
   ```powershell
   Stop-Process -Name "Live_AI_SLive" -ErrorAction SilentlyContinue ; Stop-Process -Name "live_client" -ErrorAction SilentlyContinue ; $backup = "D:\interntaks\Ainofaoce\app-ainoface\dist_backup" ; New-Item -ItemType Directory -Force -Path $backup | Out-Null ; if (Test-Path "D:\interntaks\Ainofaoce\app-ainoface\dist\Live_AI_SLive\config.json") { Copy-Item "D:\interntaks\Ainofaoce\app-ainoface\dist\Live_AI_SLive\config.json" -Destination $backup -Force } ; & "D:\interntaks\Ainofaoce\app-ainoface\test_vieneu\venv\Scripts\pyinstaller.exe" --clean --noconfirm --onedir --windowed --name "Live_AI_SLive" --icon "D:\interntaks\Ainofaoce\app-ainoface\icon.ico" --paths "D:\interntaks\Ainofaoce\app-ainoface\live_noface" --paths "D:\interntaks\Ainofaoce\app-ainoface\test_vieneu" --distpath "D:\interntaks\Ainofaoce\app-ainoface\dist" --workpath "D:\interntaks\Ainofaoce\app-ainoface\build" --specpath "D:\interntaks\Ainofaoce\app-ainoface" --collect-data vieneu --collect-data sea_g2p --add-data "D:\interntaks\Ainofaoce\app-ainoface\live_noface\templates;live_noface/templates" D:\interntaks\Ainofaoce\app-ainoface\run_app.py ; & "D:\interntaks\Ainofaoce\app-ainoface\test_vieneu\venv\Scripts\pyinstaller.exe" --clean --noconfirm --onefile --console --name "live_client" --icon "D:\interntaks\Ainofaoce\app-ainoface\icon.ico" --paths "D:\interntaks\Ainofaoce\app-ainoface\live_noface" --paths "D:\interntaks\Ainofaoce\app-ainoface\test_vieneu" --distpath "D:\interntaks\Ainofaoce\app-ainoface\dist" --workpath "D:\interntaks\Ainofaoce\app-ainoface\build" --specpath "D:\interntaks\Ainofaoce\app-ainoface" D:\interntaks\Ainofaoce\app-ainoface\live_noface\live.py ; Move-Item -Path "D:\interntaks\Ainofaoce\app-ainoface\dist\live_client.exe" -Destination "D:\interntaks\Ainofaoce\app-ainoface\dist\Live_AI_SLive\_internal\live_client.exe" -Force ; if (Test-Path "$backup\config.json") { Copy-Item "$backup\config.json" -Destination "D:\interntaks\Ainofaoce\app-ainoface\dist\Live_AI_SLive\config.json" -Force } else { if (Test-Path "D:\interntaks\Ainofaoce\app-ainoface\config.json") { Copy-Item "D:\interntaks\Ainofaoce\app-ainoface\config.json" -Destination "D:\interntaks\Ainofaoce\app-ainoface\dist\Live_AI_SLive\config.json" -Force } } ; Remove-Item -Path $backup -Recurse -Force -ErrorAction SilentlyContinue
   ```

### **Giải thích các tham số trong câu lệnh:**
* **`--onedir`**: Đóng gói thành một thư mục chứa file `.exe` và các thư viện bổ trợ đi kèm. *(Khuyên dùng dạng này thay vì `--onefile` vì file `.exe` nặng chứa mô hình AI nếu nén vào 1 file sẽ khởi động cực kỳ lâu do phải giải nén hàng trăm MB mỗi lần nhấp đúp).*
* **`--windowed`**: Chạy dưới dạng ứng dụng cửa sổ đồ họa (ẩn cửa sổ dòng lệnh đen xì của Python đi).
* **`--add-data`**: Đính kèm các thư mục tài nguyên quan trọng như file giao diện HTML (`templates`), CSS/JS (`static`) vào bên trong thư mục đóng gói để ứng dụng hiển thị đầy đủ giao diện.

---

## BƯỚC 4: KẾT QUẢ VÀ CÁCH BÀN GIAO CHO KHÁCH HÀNG

1. Sau khi chạy lệnh đóng gói thành công, trong thư mục gốc sẽ sinh ra thư mục **`dist/Live_AI_SLive`**.
2. Bên trong thư mục đó sẽ có một file chạy chính tên là **`Live_AI_SLive.exe`**.
3. **Cách phân phối:** Bạn chỉ cần nén thư mục `Live_AI_SLive` này thành một file **`.zip`** gửi cho khách hàng.
4. **Cách khách hàng sử dụng:** 
   * Khách hàng tải file `.zip` về máy, giải nén ra.
   * Nhấp đúp vào file `Live_AI_SLive.exe` để sử dụng trực tiếp.
   * **Về mô hình TTS:** Ở lần chạy đầu tiên, chương trình sẽ tự động tải các file model TTS từ HuggingFace về máy của khách hàng và lưu vào thư mục `Live_AI_SLive/tts_model_cache` vừa tạo. Các lần chạy sau sẽ đọc trực tiếp từ thư mục này, không cần mạng internet và không cần tải lại nữa!
