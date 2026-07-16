import os
import subprocess
import shutil
import json

PRODUCTION_CENTRAL_API_URL = "https://ainoface-backend.onrender.com"

# 1. Stop running app instances
try:
    subprocess.run(["taskkill", "/F", "/T", "/IM", "Live_AI_SLive.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["taskkill", "/F", "/T", "/IM", "live_client.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
except:
    pass

pyinstaller_path = os.path.join("test_vieneu", "venv", "Scripts", "pyinstaller.exe")

# 2. Build launcher
print("Building Live_AI_SLive...")
subprocess.run([pyinstaller_path, "--clean", "--noconfirm", "Live_AI_SLive.spec"])

# 3. Build live_client
print("Building live_client...")
subprocess.run([pyinstaller_path, "--clean", "--noconfirm", "live_client.spec"])

# 4. Move live_client.exe to internal folder
src_client = os.path.join("dist", "live_client.exe")
dest_client = os.path.join("dist", "Live_AI_SLive", "_internal", "live_client.exe")

if os.path.exists(src_client):
    os.makedirs(os.path.dirname(dest_client), exist_ok=True)
    shutil.move(src_client, dest_client)
    print("Successfully moved live_client.exe to internal folder.")
else:
    print("Error: live_client.exe not found.")

# 5. Copy config.json to dist/Live_AI_SLive/ next to the executable.
# Keep the packaged app pointed at production even when local config.json uses localhost.
src_config = "config.json"
dest_config = os.path.join("dist", "Live_AI_SLive", "config.json")
if os.path.exists(src_config):
    with open(src_config, "r", encoding="utf-8") as f:
        config_data = json.load(f)
    config_data["central_api_url"] = PRODUCTION_CENTRAL_API_URL
    os.makedirs(os.path.dirname(dest_config), exist_ok=True)
    with open(dest_config, "w", encoding="utf-8") as f:
        json.dump(config_data, f, ensure_ascii=False, indent=4)
    print("Successfully wrote production config.json next to executable.")
else:
    print("Warning: config.json not found in root.")

print("\nRebuild completed successfully! App is inside 'dist/Live_AI_SLive'.")
