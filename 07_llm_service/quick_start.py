#!/usr/bin/env python3
"""
NEXI LLM Service - Simple Quick Start Script

This script starts the LLM service with automatic model download from HuggingFace.
Just run this and wait for the model to download (first time only).

Usage:
    python quick_start.py
"""

import subprocess
import sys
import os

def main():
    print("\n" + "="*70)
    print("  NEXI LLM SERVICE - QUICK START")
    print("="*70 + "\n")
    
    # Change to service directory
    service_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(service_dir)
    
    print(f"Working directory: {os.getcwd()}\n")
    
    # Set environment variables for automatic model download
    env = os.environ.copy()
    env['LLM_MODEL_PATH'] = 'HuggingFaceTB/SmolLM2-1.7B-Instruct'
    env['LLM_PORT'] = '8006'
    env['LLM_DEVICE'] = 'cpu'
    env['LLM_INFERENCE_TIMEOUT'] = '90.0'
    
    print("Configuration:")
    print(f"  Model: HuggingFaceTB/SmolLM2-1.7B-Instruct")
    print(f"  Port: 8006")
    print(f"  Device: CPU")
    print(f"  Timeout: 90.0 seconds")
    print("\nStarting service...\n")
    
    # Start the service
    try:
        subprocess.run(
            [sys.executable, 'main.py'],
            env=env,
            check=True
        )
    except KeyboardInterrupt:
        print("\n\nService stopped by user.")
    except subprocess.CalledProcessError as e:
        print(f"Service exited with error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
