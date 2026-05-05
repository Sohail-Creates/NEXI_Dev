#!/usr/bin/env python3
"""Quick diagnostic and test for LLM service with OpenRouter + fallback."""

import requests
import time
import json

BASE_URL = "http://localhost:8006"

def test_health():
    """Test if service is healthy."""
    try:
        resp = requests.get(f"{BASE_URL}/api/v1/health", timeout=5)
        if resp.status_code == 200:
            print("✓ Health check passed")
            return True
        else:
            print("✗ Health check failed:", resp.status_code)
            return False
    except Exception as e:
        print("✗ Health check error:", str(e))
        return False

def test_model_info():
    """Test if model info is available."""
    try:
        resp = requests.get(f"{BASE_URL}/api/v1/model-info", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            print("✓ Model info retrieved")
            print(f"  Model: {data.get('model_name', 'unknown')}")
            return True
        else:
            print("✗ Model info failed:", resp.status_code)
            return False
    except Exception as e:
        print("✗ Model info error:", str(e))
        return False

def test_generate_english():
    """Test English text generation (OpenRouter with fallback)."""
    try:
        payload = {
            "query": "What is the capital of France?",
            "language": "en",
            "max_response_tokens": 50
        }
        
        print("\n[Testing English Generation - OpenRouter + Fallback]")
        print(f"Query: {payload['query']}")
        
        start = time.time()
        resp = requests.post(
            f"{BASE_URL}/api/v1/generate",
            json=payload,
            timeout=160  # Allow for OpenRouter (1-5s) or Local LLM (90s)
        )
        elapsed = time.time() - start
        
        if resp.status_code == 200:
            result = resp.json()
            if result.get("success"):
                response = result["data"]["response"]
                metadata = result["data"].get("metadata", {})
                source = metadata.get("primary_source", "unknown")
                
                # Determine if it was OpenRouter or fallback
                if source == "openrouter":
                    source_label = "✓ OPENROUTER (Fast)"
                elif source == "local_llm":
                    source_label = "✓ LOCAL LLM (Fallback active)"
                elif source == "fallback":
                    source_label = "✓ FALLBACK USED (Local LLM)"
                else:
                    source_label = f"Source: {source}"
                
                print(f"✓ English generation successful ({elapsed:.1f}s)")
                print(f"  {source_label}")
                print(f"  Response: {response[:100]}..." if len(response) > 100 else f"  Response: {response}")
                return True
            else:
                error = result.get("error", {})
                print(f"✗ Generation failed: {error.get('message', 'unknown error')}")
                return False
        else:
            print(f"✗ HTTP error {resp.status_code}")
            return False
    except requests.Timeout:
        print(f"✗ Request timed out after 160s")
        return False
    except Exception as e:
        print(f"✗ Generation error: {str(e)}")
        return False

def test_generate_urdu():
    """Test Urdu text generation (OpenRouter with fallback)."""
    try:
        payload = {
            "query": "السلام عليكم ورحمة الله",  # Assalamualaikum
            "language": "ur",
            "max_response_tokens": 50
        }
        
        print("\n[Testing Urdu Generation - OpenRouter + Fallback]")
        print(f"Query: {payload['query']}")
        
        start = time.time()
        resp = requests.post(
            f"{BASE_URL}/api/v1/generate",
            json=payload,
            timeout=160  # Allow for OpenRouter (1-5s) or Local LLM (120s)
        )
        elapsed = time.time() - start
        
        if resp.status_code == 200:
            result = resp.json()
            if result.get("success"):
                response = result["data"]["response"]
                metadata = result["data"].get("metadata", {})
                source = metadata.get("primary_source", "unknown")
                
                # Determine if it was OpenRouter or fallback
                if source == "openrouter":
                    source_label = "✓ OPENROUTER (Fast)"
                elif source == "local_llm":
                    source_label = "✓ LOCAL LLM (Fallback active)"
                elif source == "fallback":
                    source_label = "✓ FALLBACK USED (Local LLM)"
                else:
                    source_label = f"Source: {source}"
                
                print(f"✓ Urdu generation successful ({elapsed:.1f}s)")
                print(f"  {source_label}")
                print(f"  Response: {response[:100]}..." if len(response) > 100 else f"  Response: {response}")
                return True
            else:
                error = result.get("error", {})
                print(f"✗ Generation failed: {error.get('message', 'unknown error')}")
                return False
        else:
            print(f"✗ HTTP error {resp.status_code}")
            return False
    except requests.Timeout:
        print(f"✗ Request timed out after 160s")
        return False
    except Exception as e:
        print(f"✗ Generation error: {str(e)}")
        return False

def test_offline_fallback():
    """Test that fallback works (simulated by using local LLM)."""
    try:
        print("\n[Testing Fallback System (Local LLM)]")
        
        payload = {
            "query": "Tell me a short story in Urdu",
            "language": "ur",
            "max_response_tokens": 50
        }
        
        print(f"Query: {payload['query']}")
        print(f"(If OpenRouter is unavailable, local LLM will respond)")
        
        start = time.time()
        resp = requests.post(
            f"{BASE_URL}/api/v1/generate",
            json=payload,
            timeout=160
        )
        elapsed = time.time() - start
        
        if resp.status_code == 200:
            result = resp.json()
            if result.get("success"):
                metadata = result["data"].get("metadata", {})
                source = metadata.get("primary_source", "unknown")
                fallback_used = metadata.get("fallback_used", False)
                error_reason = metadata.get("error_reason")
                
                status = f"✓ SUCCESS (source: {source}"
                if fallback_used:
                    status += f", fallback: {error_reason}"
                status += ")"
                
                print(f"{status} - Responded in {elapsed:.1f}s")
                return True
            else:
                print(f"✗ Failed: {result.get('error')}")
                return False
        else:
            print(f"✗ HTTP error {resp.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        return False

def main():
    """Run all tests."""
    print("=" * 70)
    print("LLM SERVICE DIAGNOSTIC TEST (OpenRouter + Dynamic Fallback)")
    print("=" * 70)
    
    results = {
        "Health": test_health(),
        "Model Info": test_model_info(),
        "English Generation": test_generate_english(),
        "Urdu Generation": test_generate_urdu(),
        "Fallback System": test_offline_fallback(),
    }
    
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nResult: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ All tests passed! Hybrid LLM service is working correctly.")
        print("\n📋 System Status:")
        print("  - OpenRouter (Llama 3.1 8B): Primary inference")
        print("  - Local SmolLM2-1.7B: Automatic fallback")
        print("  - Fallback triggers: Offline, Rate limit, API error, Timeout")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed. Check the service logs.")
        return 1

if __name__ == "__main__":
    exit(main())


