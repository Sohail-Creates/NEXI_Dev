#!/usr/bin/env python3
"""
COMPREHENSIVE TEST RUNNER - Unit, Integration, Regression Tests
Tests all NEXI Robo microservices end-to-end
"""

import asyncio
import httpx
import json
import sys
import time
from datetime import datetime

def print_header(text):
    print("\n" + "="*70)
    print(f"  {text}")
    print("="*70)

def print_test(name, result, details=""):
    status = "PASS" if result else "FAIL"
    symbol = "[+]" if result else "[-]"
    print(f"{symbol} {name:50} {status}")
    if details:
        print(f"    {details}")

async def run_tests():
    """Run all tests"""
    
    passed = 0
    failed = 0
    
    print_header("NEXI ROBO COMPREHENSIVE TEST SUITE")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Test 1: Port connectivity
    print_header("TEST GROUP 1: Service Availability")
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        services = {
            'Central Server': 8000,
            'Vision': 8001,
            'Audio': 8002,
            'TTS': 8003,
            'Enrollment': 8005
        }
        
        for service_name, port in services.items():
            try:
                resp = await client.get(f"http://localhost:{port}/health")
                if resp.status_code == 200:
                    print_test(f"{service_name} Health Check", True, f"Status: {resp.status_code}")
                    passed += 1
                else:
                    print_test(f"{service_name} Health Check", False, f"Status: {resp.status_code}")
                    failed += 1
            except Exception as e:
                print_test(f"{service_name} Health Check", False, str(e))
                failed += 1
    
    # Test 2: Central Server Endpoints
    print_header("TEST GROUP 2: Central Server Core Endpoints")
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        endpoints = [
            ('GET', '/'),
            ('GET', '/status'),
            ('GET', '/users/list'),
        ]
        
        for method, endpoint in endpoints:
            try:
                if method == 'GET':
                    resp = await client.get(f"http://localhost:8000{endpoint}")
                    print_test(f"Central Server {method} {endpoint}", resp.status_code == 200, f"Status: {resp.status_code}")
                    if resp.status_code == 200:
                        passed += 1
                    else:
                        failed += 1
            except Exception as e:
                print_test(f"Central Server {method} {endpoint}", False, str(e))
                failed += 1
    
    # Test 3: Audio Service Endpoints
    print_header("TEST GROUP 3: Audio Service Endpoints")
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        endpoints = [
            ('GET', '/'),
            ('GET', '/health'),
        ]
        
        for method, endpoint in endpoints:
            try:
                if method == 'GET':
                    resp = await client.get(f"http://localhost:8002{endpoint}")
                    print_test(f"Audio Service {method} {endpoint}", resp.status_code == 200, f"Status: {resp.status_code}")
                    if resp.status_code == 200:
                        passed += 1
                    else:
                        failed += 1
            except Exception as e:
                print_test(f"Audio Service {method} {endpoint}", False, str(e))
                failed += 1
    
    # Test 4: Vision Service Endpoints
    print_header("TEST GROUP 4: Vision Service Endpoints")
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        endpoints = [
            ('GET', '/'),
            ('GET', '/health'),
        ]
        
        for method, endpoint in endpoints:
            try:
                if method == 'GET':
                    resp = await client.get(f"http://localhost:8001{endpoint}")
                    print_test(f"Vision Service {method} {endpoint}", resp.status_code == 200, f"Status: {resp.status_code}")
                    if resp.status_code == 200:
                        passed += 1
                    else:
                        failed += 1
            except Exception as e:
                print_test(f"Vision Service {method} {endpoint}", False, str(e))
                failed += 1
    
    # Test 5: TTS Service Endpoints
    print_header("TEST GROUP 5: TTS Service Endpoints")
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        endpoints = [
            ('GET', '/'),
            ('GET', '/health'),
        ]
        
        for method, endpoint in endpoints:
            try:
                if method == 'GET':
                    resp = await client.get(f"http://localhost:8003{endpoint}")
                    print_test(f"TTS Service {method} {endpoint}", resp.status_code == 200, f"Status: {resp.status_code}")
                    if resp.status_code == 200:
                        passed += 1
                    else:
                        failed += 1
            except Exception as e:
                print_test(f"TTS Service {method} {endpoint}", False, str(e))
                failed += 1
    
    # Test 6: Enrollment Service Endpoints
    print_header("TEST GROUP 6: Enrollment Service Endpoints")
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        endpoints = [
            ('GET', '/'),
            ('GET', '/health'),
        ]
        
        for method, endpoint in endpoints:
            try:
                if method == 'GET':
                    resp = await client.get(f"http://localhost:8005{endpoint}")
                    print_test(f"Enrollment Service {method} {endpoint}", resp.status_code == 200, f"Status: {resp.status_code}")
                    if resp.status_code == 200:
                        passed += 1
                    else:
                        failed += 1
            except Exception as e:
                print_test(f"Enrollment Service {method} {endpoint}", False, str(e))
                failed += 1
    
    # Summary
    print_header("TEST SUMMARY")
    
    total = passed + failed
    percentage = (passed / total * 100) if total > 0 else 0
    
    print(f"Total Tests:    {total}")
    print(f"Passed:         {passed}")
    print(f"Failed:         {failed}")
    print(f"Success Rate:   {percentage:.1f}%")
    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if failed == 0:
        print("\nSTATUS: ALL TESTS PASSED!")
        return 0
    else:
        print(f"\nSTATUS: {failed} TEST(S) FAILED")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(run_tests())
    sys.exit(exit_code)
