python : 3.10.9

tạo môi trường ảo:

python -m venv venv

tải các thư viện cần thiết:

pip install -r requirements.txt


chạy :

uvicorn main:app --host 0.0.0.0 --port 8005