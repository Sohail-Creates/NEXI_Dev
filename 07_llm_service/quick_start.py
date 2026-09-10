#!/usr/bin/env python3
"""
NEXI LLM Service - Simple Quick Start Script

This script starts the online LLM service using deployment configuration.

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
    
    env = os.environ.copy()
    print("Starting online service using configured OpenRouter settings...\n")
    
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
