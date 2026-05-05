"""
NEXI TTS Service Entry Point
Text-to-Speech service using Piper TTS engine
Runs on PORT 8003 (configurable via environment)
"""

import logging
import sys
from pathlib import Path

# Add workspace root to path for shared modules
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

import uvicorn

from tts_service.config import Config

if __name__ == "__main__":
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    uvicorn.run(
        "tts_service.app:app",
        host=Config.HOST,
        port=Config.PORT,
        reload=False,
        log_level=Config.LOG_LEVEL.lower()
    )
