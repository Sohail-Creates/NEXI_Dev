"""
Audio Service Configuration
Part of the Nexi Robo system - global configuration support
"""

import os
import platform
from pathlib import Path
from dotenv import load_dotenv

# Try to import config module for environment-agnostic port configuration
try:
    from config.ports import ServicePorts
    _HAVE_CONFIG_PORTS = True
except (ImportError, ModuleNotFoundError):
    _HAVE_CONFIG_PORTS = False

load_dotenv()

# Detect the current platform
CURRENT_PLATFORM = platform.system()  # Returns 'Windows', 'Linux', 'Darwin' (macOS)

# ============================================================================
# API CONFIGURATION
# ============================================================================
API_CONFIG = {
    "host": os.getenv("AUDIO_SERVICE_HOST", "0.0.0.0"),
    "port": int(os.getenv("AUDIO_SERVICE_PORT", 8002)),
    "title": "Audio Service",
    "version": "1.0.0",
    "description": "Audio processing, speaker verification, and embeddings"
}

AUDIO_CONFIG = API_CONFIG

# ============================================================================
# FILE & DATA CONFIGURATION
# ============================================================================
DATA_DIR = Path(os.getenv("AUDIO_DATA_DIR", "03_audio_service/audio_service/data"))
AUDIO_FILE_EXTENSION = os.getenv("AUDIO_FILE_EXTENSION", ".wav")
AUDIO_FILE_PREFIX = os.getenv("AUDIO_FILE_PREFIX", "audio")
ENROLLMENT_FILE_PREFIX = os.getenv("ENROLLMENT_FILE_PREFIX", "enrollment")
WAKE_WORD_FILE_PREFIX = os.getenv("WAKE_WORD_FILE_PREFIX", "wake_word")
TIMESTAMP_FORMAT = os.getenv("TIMESTAMP_FORMAT", "%Y%m%d_%H%M%S")

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# ============================================================================
# QUEUE CONFIGURATION
# ============================================================================
QUEUE_CONFIG = {
    "db_path": os.getenv("AUDIO_QUEUE_DB_PATH", "audio_service/data/queue.db"),
    "max_retry_count": int(os.getenv("AUDIO_QUEUE_MAX_RETRY", 3)),
    "max_queue_size": int(os.getenv("AUDIO_QUEUE_MAX_SIZE", 1000)),
    "poll_interval": int(os.getenv("AUDIO_QUEUE_POLL_INTERVAL", 1)),
    "batch_size": int(os.getenv("AUDIO_QUEUE_BATCH_SIZE", 10))
}

# ============================================================================
# BACKEND CONFIGURATION
# ============================================================================
BACKEND_CONFIG = {
    "enable_polling": os.getenv("AUDIO_BACKEND_ENABLE_POLLING", "true").lower() == "true",
    "poll_interval": int(os.getenv("AUDIO_BACKEND_POLL_INTERVAL", 5)),
    "base_url": os.getenv("AUDIO_BACKEND_BASE_URL", os.getenv("CENTRAL_SERVER_URL", "http://localhost:8000")),
    "api_key": os.getenv("AUDIO_BACKEND_API_KEY", ""),
    "timeout": int(os.getenv("AUDIO_BACKEND_TIMEOUT", 30)),
    "max_retries": int(os.getenv("AUDIO_BACKEND_MAX_RETRIES", 3)),
    "verify_ssl": os.getenv("AUDIO_BACKEND_VERIFY_SSL", "true").lower() == "true",
    "circuit_breaker": {
        "enabled": os.getenv("AUDIO_CIRCUIT_BREAKER_ENABLED", "true").lower() == "true",
        "failure_threshold": int(os.getenv("AUDIO_CB_FAILURE_THRESHOLD", 5)),
        "recovery_timeout": int(os.getenv("AUDIO_CB_TIMEOUT", 60)),
        "half_open_attempts": int(os.getenv("AUDIO_CB_HALF_OPEN", 3))
    }
}

# ============================================================================
# PIPELINE CONFIGURATION
# ============================================================================
PIPELINE_CONFIG = {
    "sample_rate": int(os.getenv("AUDIO_SAMPLE_RATE", 16000)),
    "channels": int(os.getenv("AUDIO_CHANNELS", 1)),
    "chunk_size": int(os.getenv("AUDIO_CHUNK_SIZE", 1024)),
    "format": os.getenv("AUDIO_FORMAT", "pcm_16"),
    "enable_wake_word": os.getenv("PORCUPINE_WAKE_WORD_ENABLED", "true").lower() == "true",
    "enable_speaker_verification": os.getenv("SPEAKER_VERIFICATION_ENABLED", "true").lower() == "true",
    "enable_stt": os.getenv("STT_ENABLED", "true").lower() == "true",
    "queue_poll_interval": int(os.getenv("AUDIO_QUEUE_POLL_INTERVAL", 1)),
    "queue_batch_size": int(os.getenv("AUDIO_QUEUE_BATCH_SIZE", 10))
}

# ============================================================================
# SERVICE DISCOVERY
# ============================================================================
# Use environment variables with defaults from config.ports if available
if _HAVE_CONFIG_PORTS:
    CENTRAL_SERVER_URL = os.getenv("CENTRAL_SERVER_URL", ServicePorts.get_base_url("central"))
    VISION_SERVICE_URL = os.getenv("VISION_SERVICE_URL", ServicePorts.get_base_url("vision"))
    TTS_SERVICE_URL = os.getenv("TTS_SERVICE_URL", ServicePorts.get_base_url("tts"))
else:
    # Fallback to defaults if config module not available (local dev)
    CENTRAL_SERVER_URL = os.getenv("CENTRAL_SERVER_URL", "http://localhost:8000")
    VISION_SERVICE_URL = os.getenv("VISION_SERVICE_URL", "http://localhost:8001")
    TTS_SERVICE_URL = os.getenv("TTS_SERVICE_URL", "http://localhost:8003")

# ============================================================================
# FEATURE FLAGS
# ============================================================================
ENABLE_CIRCUIT_BREAKER = os.getenv("ENABLE_CIRCUIT_BREAKER", "true").lower() == "true"
ENABLE_CACHING = os.getenv("ENABLE_AUDIO_CACHE", "true").lower() == "true"

# ============================================================================
# SPEAKER VERIFICATION CONFIGURATION
# ============================================================================
SPEAKER_CONFIG = {
    "model": os.getenv("SPEAKER_MODEL", "resemblyzer"),
    "sample_rate": int(os.getenv("SPEAKER_SAMPLE_RATE", 16000)),
    "min_duration": float(os.getenv("SPEAKER_MIN_DURATION", 1.0)),
    "max_duration": float(os.getenv("SPEAKER_MAX_DURATION", 10.0)),
    "similarity_threshold": float(os.getenv("SPEAKER_SIMILARITY_THRESHOLD", 0.7)),
    "enable_cache": os.getenv("SPEAKER_ENABLE_CACHE", "true").lower() == "true",
    "embeddings_file": Path(os.getenv("SPEAKER_EMBEDDINGS_FILE", "03_audio_service/audio_service/data/speaker_embeddings.pkl")),
    "enrollment_duration": float(os.getenv("SPEAKER_ENROLLMENT_DURATION", 5.0)),
    "min_speech_duration": float(os.getenv("SPEAKER_MIN_SPEECH_DURATION", 1.0)),
    "verification_threshold": float(os.getenv("SPEAKER_VERIFICATION_THRESHOLD", 0.65))
}

# ============================================================================
# SPEECH-TO-TEXT CONFIGURATION
# ============================================================================
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
STT_CONFIG = {
    "model": os.getenv("STT_MODEL", "whisper-large-v3"),
    "language": os.getenv("STT_LANGUAGE", "en"),
    "temperature": float(os.getenv("STT_TEMPERATURE", 0.0)),
    "max_tokens": int(os.getenv("STT_MAX_TOKENS", 2048)),
    "max_retries": int(os.getenv("STT_MAX_RETRIES", 3)),
    "retry_delay": float(os.getenv("STT_RETRY_DELAY", 1.0)),
    "timeout": int(os.getenv("STT_TIMEOUT", 30)),
    "default_language": "en",
    "supported_languages": ["en", "ur"],
    "enable_preprocessing": os.getenv("STT_ENABLE_PREPROCESSING", "true").lower() == "true"
}

ENHANCED_STT_CONFIG = {
    "enable_punctuation": os.getenv("ENHANCED_STT_PUNCTUATION", "true").lower() == "true",
    "enable_diarization": os.getenv("ENHANCED_STT_DIARIZATION", "false").lower() == "true",
    "enable_entity_recognition": os.getenv("ENHANCED_STT_ENTITY", "false").lower() == "true",
    "circuit_breaker": {
        "failure_threshold": int(os.getenv("STT_CB_FAILURE_THRESHOLD", 5)),
        "recovery_timeout": int(os.getenv("STT_CB_TIMEOUT", 60)),
        "recovery_threshold": int(os.getenv("STT_CB_RECOVERY_THRESHOLD", 2))
    }
}

VAD_CONFIG = {
    "enabled": os.getenv("VAD_ENABLED", "true").lower() == "true",
    "threshold": float(os.getenv("VAD_THRESHOLD", 0.5)),
    "min_duration": float(os.getenv("VAD_MIN_DURATION", 0.1)),
    "frame_duration_ms": int(os.getenv("VAD_FRAME_DURATION_MS", 30)),
    "energy_threshold": float(os.getenv("VAD_ENERGY_THRESHOLD", -40.0)),
    "adaptive_threshold": os.getenv("VAD_ADAPTIVE_THRESHOLD", "true").lower() == "true",
    "webrtc_mode": int(os.getenv("VAD_WEBRTC_MODE", 0))
}

# ============================================================================
# WAKE WORD CONFIGURATION
# ============================================================================
PORCUPINE_ACCESS_KEY = os.getenv("PORCUPINE_ACCESS_KEY", "")

# Platform-specific Porcupine model detection
def _get_porcupine_model_path():
    """Get platform-specific Porcupine model file path."""
    wake_word_dir = Path(__file__).parent.parent / "wake_word_models"
    audio_service_dir = Path(__file__).parent.parent
    
    # Try root level first (preferred location) - NOW USING v4.0.0 TO MATCH STOP WORD VERSION
    root_model = audio_service_dir / "Hey-Nex-e_en_windows_v4_0_0.ppn"
    if root_model.exists():
        return root_model
    
    # Then try platform-specific directory (v4.0.0 - matching stop word dependency)
    if CURRENT_PLATFORM == "Windows":
        model_file = wake_word_dir / "Window" / "Hey-Nex-e_en_windows_v4_0_0.ppn"
    elif CURRENT_PLATFORM == "Darwin":  # macOS
        model_file = wake_word_dir / "Mac" / "Hey-Nex-e_en_macos_v4_0_0.ppn"
    elif CURRENT_PLATFORM == "Linux":
        model_file = wake_word_dir / "Linux" / "Hey-Nex-e_en_linux_v4_0_0.ppn"
    else:
        # Fallback to Windows model if platform not recognized
        model_file = wake_word_dir / "Window" / "Hey-Nex-e_en_windows_v4_0_0.ppn"
    
    if model_file.exists():
        return model_file
    
    return None

PORCUPINE_MODEL_PATH = _get_porcupine_model_path()

WAKE_WORD_CONFIG = {
    "access_key": PORCUPINE_ACCESS_KEY,
    "keyword_path": PORCUPINE_MODEL_PATH,  # Now using v4.0.0 model to match stop word
    "sensitivity": float(os.getenv("PORCUPINE_SENSITIVITY", "0.7")),
    "keywords": os.getenv("PORCUPINE_KEYWORDS", "hey google").split(","),
    "sensitivities": [float(x) for x in os.getenv("PORCUPINE_SENSITIVITIES", "0.5").split(",")],
    "model_path": os.getenv("PORCUPINE_MODEL_PATH", None),
    "library_path": os.getenv("PORCUPINE_LIBRARY_PATH", None),
    "frame_length": int(os.getenv("PORCUPINE_FRAME_LENGTH", 512)),
    "buffer_duration": float(os.getenv("PORCUPINE_BUFFER_DURATION", 2.0)),
    "command_duration": float(os.getenv("WAKE_WORD_COMMAND_DURATION", 3.0)),
    "keyword": os.getenv("WAKE_WORD_KEYWORD", "Hey Nexi"),
    "heartbeat_interval": float(os.getenv("WAKE_WORD_HEARTBEAT_INTERVAL", 1.0))
}

# ============================================================================
# POWER & AUDIO ANALYSIS CONFIGURATION
# ============================================================================
POWER_CONFIG = {
    "enabled": os.getenv("POWER_ANALYSIS_ENABLED", "true").lower() == "true",
    "update_interval": int(os.getenv("POWER_UPDATE_INTERVAL", 100)),
    "threshold": float(os.getenv("POWER_THRESHOLD", -40.0)),
    "default_mode": os.getenv("POWER_MODE", "balanced"),
    "low_power": {
        "vad_enabled": True,
        "porcupine_sensitivity": 0.5,
        "sample_rate": 8000
    },
    "balanced": {
        "vad_enabled": True,
        "porcupine_sensitivity": 0.7,
        "sample_rate": 16000
    },
    "high_performance": {
        "vad_enabled": False,
        "porcupine_sensitivity": 0.9,
        "sample_rate": 16000
    }
}

# ============================================================================
# AUDIO PREPROCESSING CONFIGURATION
# ============================================================================
PREPROCESSING_CONFIG = {
    "normalize": os.getenv("PREPROCESSING_NORMALIZE", "true").lower() == "true",
    "trim_silence": os.getenv("PREPROCESSING_TRIM_SILENCE", "true").lower() == "true",
    "remove_noise": os.getenv("PREPROCESSING_REMOVE_NOISE", "true").lower() == "true",
    "sample_rate": int(os.getenv("PREPROCESSING_SAMPLE_RATE", 16000)),
    "frame_length": int(os.getenv("PREPROCESSING_FRAME_LENGTH", 2048)),
    "hop_length": int(os.getenv("PREPROCESSING_HOP_LENGTH", 512))
}

# ============================================================================
# RESILIENCE CONFIGURATION
# ============================================================================
RESILIENCE_CONFIG = {
    "enable_circuit_breaker": os.getenv("RESILIENCE_CIRCUIT_BREAKER", "true").lower() == "true",
    "failure_threshold": int(os.getenv("RESILIENCE_FAILURE_THRESHOLD", 5)),
    "recovery_timeout": int(os.getenv("RESILIENCE_RECOVERY_TIMEOUT", 60)),
    "enable_retry": os.getenv("RESILIENCE_RETRY", "true").lower() == "true",
    "max_retries": int(os.getenv("RESILIENCE_MAX_RETRIES", 3))
}

# ============================================================================
# STOP WORD DETECTION CONFIGURATION (NEW - v4.0.0)
# ============================================================================
# NOTE: Both wake word and stop word now use v4.0.0 for consistency and to avoid dependency conflicts
def _get_stop_word_model_path():
    """Get stop word Porcupine model file path (v4.0.0)."""
    # Try multiple possible locations - BOTH USING v4.0.0 NOW
    possible_paths = [
        Path("03_audio_service/stopword_model/stop-nex-e_en_windows_v4_0_0.ppn"),
        Path(__file__).parent.parent / "stopword_model" / "stop-nex-e_en_windows_v4_0_0.ppn",
        Path.cwd() / "03_audio_service" / "stopword_model" / "stop-nex-e_en_windows_v4_0_0.ppn",
    ]
    
    for path in possible_paths:
        try:
            if Path(path).exists():
                return Path(path).resolve()
        except Exception:
            continue
    
    return None

STOP_WORD_MODEL_PATH = _get_stop_word_model_path()

STOP_WORD_CONFIG = {
    "access_key": PORCUPINE_ACCESS_KEY,
    "model_path": STOP_WORD_MODEL_PATH,
    "sensitivity": float(os.getenv("STOP_WORD_SENSITIVITY", "0.7")),
    "enabled": os.getenv("STOP_WORD_ENABLED", "true").lower() == "true",
    "frame_length": int(os.getenv("STOP_WORD_FRAME_LENGTH", 512))
}

# ============================================================================
# VAD RECORDER CONFIGURATION (NEW)
# ============================================================================
# ENHANCED FIX: Reduced max_recording_seconds from 30s to 5s for faster response
# - Turn 1 query typically 3-5 seconds
# - Stop word detection responds within 1 second instead of 30 seconds
# - User can continue speaking after 5s by saying query again
VAD_RECORDER_CONFIG = {
    "sample_rate": int(os.getenv("VAD_RECORDER_SAMPLE_RATE", 16000)),
    "chunk_size": int(os.getenv("VAD_RECORDER_CHUNK_SIZE", 512)),
    "channels": int(os.getenv("VAD_RECORDER_CHANNELS", 1)),
    "silence_threshold_ms": int(os.getenv("VAD_SILENCE_THRESHOLD_MS", 500)),
    "max_recording_seconds": int(os.getenv("VAD_MAX_RECORDING_SECONDS", 5)),
    "output_directory": Path(os.getenv("VAD_RECORDING_OUTPUT_DIR", "03_audio_service/audio_service/data/recordings"))
}

# Create recordings directory if it doesn't exist
VAD_RECORDER_CONFIG["output_directory"].mkdir(parents=True, exist_ok=True)

# ============================================================================
# CONVERSATION STATE CONFIGURATION (NEW)
# ============================================================================
CONVERSATION_CONFIG = {
    "timeout_seconds": int(os.getenv("CONVERSATION_TIMEOUT_SECONDS", 120)),
    "enable_continuous_mode": os.getenv("CONVERSATION_CONTINUOUS_MODE", "true").lower() == "true",
    "max_consecutive_silence": int(os.getenv("CONVERSATION_MAX_SILENCE_SEC", 120))
}
