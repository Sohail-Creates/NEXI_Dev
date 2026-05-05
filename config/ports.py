from __future__ import annotations

from typing import Dict
import os


def _env_int(key: str, default: int) -> int:
    value = os.getenv(key)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_str(key: str, default: str) -> str:
    """Get string environment variable with default."""
    return os.getenv(key, default)


CENTRAL_SERVER_PORT = _env_int("CENTRAL_SERVER_PORT", 8000)
CENTRAL_SERVER_HOST = _env_str("CENTRAL_SERVER_HOST", "localhost")
VISION_SERVICE_PORT = _env_int("VISION_SERVICE_PORT", 8001)
VISION_SERVICE_HOST = _env_str("VISION_SERVICE_HOST", "localhost")
AUDIO_SERVICE_PORT = _env_int("AUDIO_SERVICE_PORT", 8002)
AUDIO_SERVICE_HOST = _env_str("AUDIO_SERVICE_HOST", "localhost")
TTS_SERVICE_PORT = _env_int("TTS_SERVICE_PORT", 8003)
TTS_SERVICE_HOST = _env_str("TTS_SERVICE_HOST", "localhost")
TEACHME_SERVICE_PORT = _env_int("TEACHME_SERVICE_PORT", 8004)
TEACHME_SERVICE_HOST = _env_str("TEACHME_SERVICE_HOST", "localhost")
ENROLLMENT_SERVICE_PORT = _env_int("ENROLLMENT_SERVICE_PORT", 8005)
ENROLLMENT_SERVICE_HOST = _env_str("ENROLLMENT_SERVICE_HOST", "localhost")
LLM_SERVICE_PORT = _env_int("LLM_SERVICE_PORT", 8006)
LLM_SERVICE_HOST = _env_str("LLM_SERVICE_HOST", "localhost")
STREAMLIT_UI_PORT = _env_int("STREAMLIT_UI_PORT", 8501)
STREAMLIT_UI_HOST = _env_str("STREAMLIT_UI_HOST", "localhost")


SERVICE_PORTS: Dict[str, int] = {
    "central_server": CENTRAL_SERVER_PORT,
    "vision_service": VISION_SERVICE_PORT,
    "audio_service": AUDIO_SERVICE_PORT,
    "tts_service": TTS_SERVICE_PORT,
    "teachme_service": TEACHME_SERVICE_PORT,
    "enrollment_service": ENROLLMENT_SERVICE_PORT,
    "llm_service": LLM_SERVICE_PORT,
    "streamlit_ui": STREAMLIT_UI_PORT,
}


def get_port(service_name: str, default: int | None = None) -> int | None:
    if service_name in SERVICE_PORTS:
        return SERVICE_PORTS[service_name]
    return default


class ServicePorts:
    """Service ports configuration class."""
    CENTRAL_SERVER = CENTRAL_SERVER_PORT
    VISION_SERVICE = VISION_SERVICE_PORT
    AUDIO_SERVICE = AUDIO_SERVICE_PORT
    TTS_SERVICE = TTS_SERVICE_PORT
    TEACHME_SERVICE = TEACHME_SERVICE_PORT
    ENROLLMENT_SERVICE = ENROLLMENT_SERVICE_PORT
    LLM_SERVICE = LLM_SERVICE_PORT
    STREAMLIT_UI = STREAMLIT_UI_PORT
    
    @staticmethod
    def get_base_url(service_name: str) -> str:
        """
        Get base URL for a service from environment variables.
        Supports both local development and Docker deployment:
        
        LOCAL DEV: http://localhost:8002
        DOCKER:    http://audio-service:8002
        
        Configure via .env:
        - AUDIO_SERVICE_HOST=audio-service (for Docker)
        - AUDIO_SERVICE_HOST=localhost (for local dev)
        """
        service_map = {
            "central": f"http://{CENTRAL_SERVER_HOST}:{CENTRAL_SERVER_PORT}",
            "audio": f"http://{AUDIO_SERVICE_HOST}:{AUDIO_SERVICE_PORT}",
            "vision": f"http://{VISION_SERVICE_HOST}:{VISION_SERVICE_PORT}",
            "tts": f"http://{TTS_SERVICE_HOST}:{TTS_SERVICE_PORT}",
            "teachme": f"http://{TEACHME_SERVICE_HOST}:{TEACHME_SERVICE_PORT}",
            "enrollment": f"http://{ENROLLMENT_SERVICE_HOST}:{ENROLLMENT_SERVICE_PORT}",
            "streamlit": f"http://{STREAMLIT_UI_HOST}:{STREAMLIT_UI_PORT}",
        }
        return service_map.get(service_name, f"http://{CENTRAL_SERVER_HOST}:{CENTRAL_SERVER_PORT}")