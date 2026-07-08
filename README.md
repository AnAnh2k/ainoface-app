# Hệ Thống Live AI - S Live (MC Ảo Livestream Tự Động)

Dự án phát triển ứng dụng MC ảo tự động tương tác livestream trên nền tảng TikTok. Ứng dụng tích hợp mô hình ngôn ngữ lớn (LLM Qwen) để tự động trả lời câu hỏi của người xem và mô hình chuyển đổi văn bản thành giọng nói (AI TTS VieNeu) để phát giọng MC ảo tự nhiên trong thời gian thực.

---

## 📂 Cấu Trúc Thư Mục Dự Án

*   `live_noface/`: Thư mục chứa giao diện Flask App (Web UI, login, quản lý kịch bản).
*   `test_vieneu/`: Thư mục chứa API TTS (FastAPI), quản lý mô hình giọng nói và tối ưu hóa luồng xử lý âm thanh.
*   `run_app.py`: File điều phối chính (kết nối Flask, FastAPI và khởi chạy dưới dạng cửa sổ Desktop độc lập).
*   `dist/Live_AI_SLive/`: Thư mục chứa bộ cài đặt/đóng gói hoàn chỉnh dạng `.exe` để bàn giao cho khách hàng.

---

## 🛠️ Chuẩn Bị Môi Trường & Cài Đặt

### 1. Kích hoạt môi trường ảo (venv) có sẵn
Môi trường ảo chứa đầy đủ các thư viện cần thiết đã được cài đặt sẵn tại thư mục `test_vieneu/venv`. 

Mở terminal tại thư mục gốc `Ainofaoce` và chạy lệnh sau để kích hoạt:
```powershell
.\test_vieneu\venv\Scripts\activate
```

*(Nếu kích hoạt bị chặn do chính sách của Windows, bạn hãy chạy lệnh `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process` trước).*

### 2. Cài đặt thư viện mới (Nếu có thay đổi package)
Nếu cần cài đặt lại hoặc bổ sung thư viện, hãy đảm bảo đã kích hoạt môi trường ảo ở trên và chạy:
```powershell
pip install -r test_vieneu/requirements.txt
pip install -r live_noface/requirements.txt
```

---

## 🚀 Hướng Dẫn Khởi Chạy Ở Chế Độ Phát Triển (Development Mode)

Chạy trực tiếp dự án từ mã nguồn để kiểm tra log lỗi hoặc chỉnh sửa code:

1.  Kích hoạt môi trường ảo.
2.  Chạy lệnh khởi động file điều phối:
    ```powershell
    python run_app.py
    ```
3.  **Hệ thống sẽ tự động**:
    *   Khởi chạy Flask App trên cổng `5000` (Giao diện Web).
    *   Khởi chạy FastAPI TTS Engine trên cổng `8005` (Sinh giọng nói).
    *   Mở một cửa sổ Desktop đồ họa chuyên nghiệp (PyWebView).

### 🔑 Thông tin đăng nhập mặc định:
*   **Tài khoản**: `admin`
*   **Mật khẩu**: `admin123`
*(Bạn có thể cấu hình/đổi mật khẩu trực tiếp trong file `config.json` được tạo ra sau lần chạy đầu tiên).*

---

## 🧪 Hướng Dẫn Thử Nghiệm Các Tính Năng

### 1. Test giọng đọc MC (TTS) thủ công:
*   Đăng nhập vào phần mềm -> Bấm **Bắt đầu** (màu xanh dương).
*   Nhập kịch bản hoặc yêu cầu vào ô **Nhập prompt của bạn** (Ví dụ: *"Viết kịch bản ngắn giới thiệu về mì tôm Hảo Hảo"*).
*   Bấm **Gửi**. Hệ thống sẽ tự động sinh văn bản và MC ảo sẽ đọc gối đầu liên tục ra loa của bạn.
*   **Chỉnh tốc độ nói**: Kéo thanh trượt **⚡ Tốc độ** (đầu giao diện) để tăng/giảm tốc độ đọc của MC (khuyên dùng `0.80x` - `1.05x` tùy cấu hình CPU).

### 2. Test kết nối TikTok Live:
*   Mở trình duyệt vào trang **[tiktok.com/live](https://www.tiktok.com/live)** và tìm bất kỳ kênh nào đang phát trực tiếp.
*   Copy đường link của buổi Live đó hoặc copy Username (phần sau dấu `@`). Ví dụ: `huyen3condaily`.
*   Dán link hoặc Username vào ô **TikTok username** trên phần mềm và bấm **Kết nối**.
*   **Kết quả**: Hệ thống sẽ tự động lắng nghe bình luận thật của người xem trên TikTok, viết câu trả lời bằng AI, tự động phát giọng đọc MC ảo và chạy karaoke highlight chữ tương ứng.

---

## 📦 Hướng Dẫn Biên Dịch & Đóng Gói (Rebuild)

Khi bạn thực hiện chỉnh sửa code giao diện (`index.html`) hoặc logic python (`live.py`, `app.py`, `run_app.py`), hãy chạy câu lệnh PowerShell dưới đây tại thư mục gốc `Ainofaoce` để tự động dọn dẹp cache, đóng gói lại cả 2 tiến trình thành một file chạy duy nhất:

```powershell
Stop-Process -Name "Live_AI_SLive" -ErrorAction SilentlyContinue ; Stop-Process -Name "live_client" -ErrorAction SilentlyContinue ; & "d:\interntaks\Ainofaoce\test_vieneu\venv\Scripts\pyinstaller.exe" --clean --noconfirm --onedir --windowed --name "Live_AI_SLive" --icon "d:\interntaks\Ainofaoce\icon.ico" --paths "d:\interntaks\Ainofaoce\live_noface" --paths "d:\interntaks\Ainofaoce\test_vieneu" --distpath "d:\interntaks\Ainofaoce\dist" --workpath "d:\interntaks\Ainofaoce\build" --specpath "d:\interntaks\Ainofaoce" --collect-data vieneu --collect-data sea_g2p --add-data "d:\interntaks\Ainofaoce\live_noface\templates;live_noface/templates" d:\interntaks\Ainofaoce\run_app.py ; & "d:\interntaks\Ainofaoce\test_vieneu\venv\Scripts\pyinstaller.exe" --clean --noconfirm --onefile --console --name "live_client" --icon "d:\interntaks\Ainofaoce\icon.ico" --paths "d:\interntaks\Ainofaoce\live_noface" --paths "d:\interntaks\Ainofaoce\test_vieneu" --distpath "d:\interntaks\Ainofaoce\dist" --workpath "d:\interntaks\Ainofaoce\build" --specpath "d:\interntaks\Ainofaoce" d:\interntaks\Ainofaoce\live_noface\live.py ; Move-Item -Path "d:\interntaks\Ainofaoce\dist\live_client.exe" -Destination "d:\interntaks\Ainofaoce\dist\Live_AI_SLive\_internal\live_client.exe" -Force
```

### ⚠️ Lưu ý quan trọng khi bàn giao cho khách hàng:
*   Bộ cài hoàn chỉnh nằm tại thư mục **`dist/Live_AI_SLive/`**. Bạn chỉ cần nén thư mục này thành file **`.zip`** gửi cho khách hàng.
*   **Chế độ Hybrid thông minh**: Thư mục mô hình `tts_model_cache` đã được đưa vào `.gitignore` để file ZIP gửi đi cực nhẹ (~50MB). Khi khách hàng chạy phần mềm lần đầu tiên, app sẽ tự kết nối mạng để tải mô hình về. Từ lần thứ 2 trở đi, app tự động kích hoạt chế độ **Offline** để khởi động tức thì chỉ trong 5 giây mà không cần mạng Internet.
