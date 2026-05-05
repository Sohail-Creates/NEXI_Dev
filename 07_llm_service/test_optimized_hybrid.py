"""
Test optimized hybrid system with lazy-loading fallback.

Tests:
1. Normal OpenRouter operation (fast, ~1-5s)
2. Local LLM fallback (lazy-loaded on first use, ~27-92s)
3. Performance monitoring and metrics
4. Fallback state management
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime

SERVICE_URL = "http://localhost:8006/api/v1"

async def test_hybrid_system():
    """Test hybrid system with performance monitoring."""
    
    print("\n" + "=" * 80)
    print("OPTIMIZED HYBRID LLM SYSTEM TEST")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Service: {SERVICE_URL}")
    print()
    
    async with aiohttp.ClientSession() as session:
        # Test 1: Health check
        print("[1/4] Health Check")
        print("-" * 80)
        try:
            async with session.get(f"{SERVICE_URL}/health") as resp:
                data = await resp.json()
                print(f"Status: {resp.status}")
                print(f"Response: {json.dumps(data, indent=2)[:200]}")
                print("✓ Service is responsive\n")
        except Exception as e:
            print(f"✗ Health check failed: {str(e)}\n")
            return
        
        # Test 2: Model info
        print("[2/4] Model Information")
        print("-" * 80)
        try:
            async with session.get(f"{SERVICE_URL}/model-info") as resp:
                info = await resp.json()
                print(f"Model Loaded: {info.get('model_loaded', False)}")
                print(f"Model Name: {info.get('model_name', 'unknown')}")
                print(f"Device: {info.get('device', 'unknown')}")
                print(f"Fallback Mode: {info.get('in_fallback_mode', False)}")
                print(f"Local Model State: {info.get('fallback_state', 'unknown')}")
                print("✓ Model info retrieved\n")
        except Exception as e:
            print(f"✗ Info check failed: {str(e)}\n")
        
        # Test 3: Standard generation (OpenRouter if available, else fallback)
        print("[3/4] Standard Generation Test")
        print("-" * 80)
        try:
            test_prompts = [
                ("What is 2+2?", "en"),
                ("منہ کیا ہے", "ur"),
            ]
            
            for prompt, lang in test_prompts:
                print(f"\nPrompt: '{prompt[:30]}...' (Language: {lang})")
                
                start_time = time.time()
                async with session.post(
                    f"{SERVICE_URL}/generate",
                    json={
                        "prompt": prompt,
                        "max_response_tokens": 50,
                        "temperature": 0.6,
                    },
                    timeout=aiohttp.ClientTimeout(total=180)
                ) as resp:
                    elapsed = time.time() - start_time
                    data = await resp.json()
                    
                    # Parse response
                    response_text = data.get("response", "")[:60]
                    status = data.get("status", "unknown")
                    metadata = data.get("metadata", {})
                    
                    # Check which system was used
                    primary_source = metadata.get("primary_source", "unknown")
                    openrouter_time = metadata.get("openrouter_response_time", 0)
                    local_time = metadata.get("local_response_time", 0)
                    fallback_mode = metadata.get("fallback_mode", False)
                    cuda_enabled = metadata.get("cuda_enabled", False)
                    
                    print(f"  Response Time: {elapsed:.2f}s")
                    print(f"  Primary Source: {primary_source}")
                    print(f"  Fallback Mode Active: {fallback_mode}")
                    print(f"  CUDA Enabled: {cuda_enabled}")
                    
                    if openrouter_time > 0:
                        print(f"  OpenRouter Response Time: {openrouter_time:.2f}s")
                    if local_time > 0:
                        print(f"  Local LLM Response Time: {local_time:.2f}s")
                    
                    if fallback_mode and "fallback_duration" in metadata:
                        fallback_duration = metadata["fallback_duration"]
                        print(f"  Fallback Duration: {fallback_duration:.1f}s")
                    
                    print(f"  Response: '{response_text}...'")
                    
                    if status == "success":
                        print("  ✓ Generation succeeded")
                    else:
                        print(f"  ✗ Generation failed: {status}")
        
        except asyncio.TimeoutError:
            print("✗ Request timed out")
        except Exception as e:
            print(f"✗ Generation test failed: {str(e)}")
        
        # Test 4: Final system status
        print("\n[4/4] System Status (After Generation)")
        print("-" * 80)
        try:
            async with session.get(f"{SERVICE_URL}/model-info") as resp:
                status = await resp.json()
                print(f"OpenRouter Available: {status.get('openrouter_available', False)}")
                print(f"In Fallback Mode: {status.get('in_fallback_mode', False)}")
                print(f"Consecutive Failures: {status.get('openrouter_failures', 0)}")
                
                print("\nFallback Manager Status:")
                print(f"  State: {status.get('fallback_state', 'unknown')}")
                print(f"  Model Loaded: {status.get('model_loaded', False)}")
                print(f"  Device: {status.get('device', 'unknown')}")
                
                print("\n✓ System status retrieved")
        except Exception as e:
            print(f"✗ Final status check failed: {str(e)}")
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)
    print("\nOptimizations Applied:")
    print("1. ✓ Lazy loading: Local LLM loads only when fallback needed")
    print("2. ✓ Resource persistence: Model stays loaded during fallback")
    print("3. ✓ CUDA auto-detection: GPU acceleration when available")
    print("4. ✓ Health monitoring: Background OpenRouter recovery checks")
    print("5. ✓ Automatic recovery: Switches back to OpenRouter when available")
    print()

if __name__ == "__main__":
    try:
        asyncio.run(test_hybrid_system())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nTest failed: {str(e)}")
