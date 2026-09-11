#!/usr/bin/env python
"""
TeachMe Service - Main Entry Point
Production-Ready Knowledge API with Vision Integration

Run with: python main.py
Or: uvicorn teachme_service.app:app --host 0.0.0.0 --port 8004
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

if __name__ == "__main__":
    # Import here to ensure proper module loading
    import uvicorn
    from teachme_service.config import server_config
    
    print("=" * 80)
    print("Starting TeachMe Service v4.0.0 - Production Ready")
    print("=" * 80)
    print(f"Host: {server_config.HOST}")
    print(f"Port: {server_config.PORT}")
    print(f"Debug: {server_config.DEBUG}")
    print(f"Reload: {server_config.RELOAD}")
    print("=" * 80)
    
    # Start the FastAPI application
    uvicorn.run(
        "teachme_service.app:app",
        host=server_config.HOST,
        port=server_config.PORT,
        reload=server_config.RELOAD,
        log_level=server_config.LOG_LEVEL.lower()
    )
