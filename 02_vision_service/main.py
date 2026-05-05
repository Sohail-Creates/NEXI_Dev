"""
Vision Service Main Entry Point
Starts the Vision Service with Uvicorn
"""

import sys
import os
import logging
from pathlib import Path

# Add root project to path for shared modules access
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import and run the application
try:
    from vision_service.config import Config
    from vision_service.app import app
    import uvicorn
    
    logger.info("=" * 60)
    logger.info("VISION SERVICE - STARTUP")
    logger.info("=" * 60)
    logger.info(f"Project Root: {root_dir}")
    logger.info(f"Service Host: {Config.HOST}")
    logger.info(f"Service Port: {Config.PORT}")
    logger.info(f"Log Level: {Config.LOG_LEVEL}")
    logger.info("=" * 60)
    
    # Run the application
    uvicorn.run(
        "vision_service.app:app",
        host=Config.HOST,
        port=Config.PORT,
        reload=False,  # Disable reload in production
        log_level=Config.LOG_LEVEL.lower()
    )
    
except ImportError as e:
    logger.error(f"Import error - missing dependencies: {e}")
    logger.error("Please ensure all requirements are installed: pip install -r requirements.txt")
    sys.exit(1)
except Exception as e:
    logger.error(f"Startup error: {e}", exc_info=True)
    sys.exit(1)
