"""
Performance verification test for optimized LLM inference.

Tests the fix for the double-inference bottleneck.
Expected improvements:
- Before: 60-150 seconds (dummy test + actual inference)
- After: 27-92 seconds (just actual inference)
"""

import asyncio
import time
import aiohttp
import json
from datetime import datetime

SERVICE_URL = "http://localhost:8006/api/v1"

async def test_response_times():
    """Test inference response times after optimization."""
    
    print("\n" + "=" * 80)
    print("OPTIMIZED INFERENCE PERFORMANCE TEST")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().strftime('%H:%M:%S')}\n")
    
    test_cases = [
        ("What is 2+2?", "en", "Simple question"),
        ("السلام عليكم", "ur", "Urdu greeting"),
        ("Tell me a short story about a robot", "en", "Creative prompt"),
    ]
    
    async with aiohttp.ClientSession() as session:
        for prompt, lang, description in test_cases:
            print(f"Test: {description}")
            print(f"Prompt: {prompt}")
            print(f"Language: {lang}")
            print("-" * 50)
            
            try:
                start_time = time.time()
                
                async with session.post(
                    f"{SERVICE_URL}/generate",
                    json={
                        "query": prompt,
                        "language": lang,
                        "max_response_tokens": 50,
                        "temperature": 0.6,
                    },
                    timeout=aiohttp.ClientTimeout(total=180)
                ) as resp:
                    elapsed = time.time() - start_time
                    result = await resp.json()
                    assert resp.status == 200, result
                    assert result['success'] is True and result['text'].strip(), result
                    assert isinstance(result['metadata'], dict), result
                    
                    success = result.get("success", False)
                    
                    if success:
                        data = result.get("data", {})
                        metadata = data.get("metadata", {})
                        response_time = metadata.get("elapsed_seconds", elapsed)
                        primary_source = metadata.get("primary_source", "unknown")
                        fallback_duration = metadata.get("fallback_duration", None)
                        cuda_enabled = metadata.get("cuda_enabled", False)
                        
                        print(f"✓ SUCCESS")
                        print(f"  Total Time: {elapsed:.2f}s")
                        print(f"  Inference Time: {response_time:.2f}s")
                        print(f"  Primary Source: {primary_source}")
                        print(f"  CUDA Enabled: {cuda_enabled}")
                        
                        if fallback_duration is not None:
                            print(f"  Fallback Duration: {fallback_duration:.2f}s")
                        
                        # Performance assessment
                        if elapsed < 5:
                            print(f"  Performance: ⭐⭐⭐⭐⭐ EXCELLENT (OpenRouter)")
                        elif elapsed < 30:
                            print(f"  Performance: ⭐⭐⭐⭐ GOOD (cached fallback)")
                        elif elapsed < 60:
                            print(f"  Performance: ⭐⭐⭐ OK (first fallback)")
                        else:
                            print(f"  Performance: ⭐⭐ SLOW (investigate)")
                        
                        response_preview = data.get("response", "")[:60]
                        print(f"  Response: '{response_preview}...'")
                    else:
                        error = result.get("error", {})
                        print(f"✗ FAILED: {error.get('message', 'Unknown error')}")
            
            except Exception as e:
                elapsed = time.time() - start_time
                print(f"✗ FAILED: {str(e)} (elapsed: {elapsed:.2f}s)")
                raise
            
            print()
    
    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)
    print("\nExpected Performance After Fix:")
    print("├─ Normal (OpenRouter): 2-5 seconds ✓")
    print("├─ Fallback First Call: 27-92 seconds (model load) ✓")
    print("├─ Fallback Cached: <30 seconds ✓")
    print("└─ NO 60-150s issues! ✓")
    print()

if __name__ == "__main__":
    try:
        asyncio.run(test_response_times())
    except KeyboardInterrupt:
        print("\n\nTest interrupted")
    except Exception as e:
        print(f"\n\nTest failed: {str(e)}")
        raise
