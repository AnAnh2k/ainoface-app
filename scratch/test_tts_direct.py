import sys
import os

# Set HF_HOME environment variable to the same local cache directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'test_vieneu')))

from vieneu import Vieneu

# Set HF cache directory
os.environ["HF_HOME"] = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tts_model_cache"))

print("Initializing Vieneu...")
try:
    model = Vieneu()
    print("Vieneu initialized successfully.")
    
    print("Testing inference with 'mì tôm' and voice 'Trúc Ly'...")
    audio = model.infer(text="mì tôm", voice="Trúc Ly")
    print(f"Success! Generated audio array of length {len(audio)}")
except Exception as e:
    import traceback
    print("Error during VieNeu TTS initialization/inference:")
    traceback.print_exc()
