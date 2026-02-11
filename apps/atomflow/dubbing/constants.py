import os

# Model Paths
WHISPER_PATH = os.environ.get("WHISPER_MODEL_PATH", "/app/local_models/whisper")
YAMNET_MODEL_PATH = os.environ.get("YAMNET_MODEL_PATH", "/app/local_models/yamnet/yamnet.onnx")
YAMNET_CLASS_MAP_PATH = os.path.join(os.path.dirname(YAMNET_MODEL_PATH), "yamnet_class_map.csv")
VAD_MODEL_PATH = os.environ.get("VAD_MODEL_PATH", "/app/local_models/vad/silero_vad.onnx")
AUDIO_SEPARATOR_MODEL_DIR = os.environ.get("AUDIO_SEPARATOR_MODEL_DIR", "/app/local_models/audio_separator")
DEEPFILTERNET_MODEL_DIR = os.environ.get("DEEPFILTERNET_MODEL_DIR", "/app/local_models/deepfilternet")
INSIGHTFACE_MODEL_DIR = os.environ.get("INSIGHTFACE_HOME", "/app/local_models/insightface")
OCR_DIR = os.environ.get("OCR_MODEL_DIR", "/app/local_models/ocr")
LAMA_MODEL_PATH = os.environ.get("LAMA_MODEL_PATH", "/app/local_models/inpainting/big-lama.pt")
