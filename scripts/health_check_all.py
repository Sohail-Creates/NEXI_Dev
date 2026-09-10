#!/usr/bin/env python
"""
Health Check Script - Verify all services are running
Run this script to check the health of all NEXI services
"""
import asyncio
import httpx
import sys
from datetime import datetime

SERVICES = {
    "Central Server": "http://localhost:8000/health",
    "Vision Service": "http://localhost:8001/health",
    "Audio Service": "http://localhost:8002/health",
    "TTS Service": "http://localhost:8003/health",
    "TeachMe Service": "http://localhost:8004/health",
    "Enrollment Service": "http://localhost:8005/health",
    "LLM Service": "http://localhost:8006/api/v1/health",
}

async def check_service_health(name: str, url: str, client: httpx.AsyncClient) -> bool:
    """Check if a service is running and healthy"""
    try:
        resp = await client.get(url, timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            reported_status = data.get("status")
            if reported_status not in {"healthy", "degraded"}:
                print(f"  [FAIL] {name:25} - {reported_status or 'unknown'}")
                return False
            print(f"  [OK] {name:25} - {reported_status}")
            return True
        else:
            print(f"  [FAIL] {name:25} - HTTP {resp.status_code}")
            return False
    except asyncio.TimeoutError:
        print(f"  [TIMEOUT] {name:25} - No response")
        return False
    except Exception as e:
        print(f"  [ERROR] {name:25} - {str(e)}")
        return False

async def main():
    """Check health of all services"""
    print("\n" + "="*60)
    print(f"NEXI Services Health Check - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60 + "\n")
    
    results = {}
    async with httpx.AsyncClient() as client:
        for name, url in SERVICES.items():
            results[name] = await check_service_health(name, url, client)
    
    # Summary
    print("\n" + "="*60)
    healthy = sum(1 for v in results.values() if v)
    total = len(results)
    
    if healthy == total:
        print(f"RESULT: ALL SERVICES RESPONSIVE ({healthy}/{total})")
        status = 0
    elif healthy > 0:
        print(f"RESULT: PARTIAL HEALTH ({healthy}/{total})")
        status = 1
    else:
        print(f"RESULT: NO SERVICES RUNNING ({healthy}/{total})")
        status = 2
    
    print("="*60 + "\n")
    return status

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
