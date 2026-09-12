"""
TTS Service Client

All communication with TTS Service (port 8004) goes through this class.
Handles text-to-speech synthesis in multiple languages and voices.
"""

import httpx
from config.ssl_config import client_verify
from shared.security import internal_service_headers
import logging
from ..utils.circuit_breaker import CircuitBreaker
from .models import ServiceCallResult
from ..config import ServiceConfig
from shared.focus_mode import FocusModeClient

logger = logging.getLogger(__name__)

# Service configuration (dynamically loaded from env vars or localhost)
TTS_SERVICE_URL = ServiceConfig.get_service_url("tts")
CIRCUIT_BREAKER_MAX_FAILURES = 3
CIRCUIT_BREAKER_RESET_TIMEOUT = 30


class TTSServiceClient:
    """
    Dedicated client for TTS Service communication.
    Synthesizes text to speech in English and Urdu.
    """

    def __init__(self, base_url: str = TTS_SERVICE_URL, focus_mode_client=None):
        self.base_url = base_url
        self.timeout = httpx.Timeout(
            connect=5.0,
            read=20.0,  # TTS synthesis can take time
            write=10.0,
            pool=5.0
        )
        self.circuit_breaker = CircuitBreaker(
            name="tts_service",
            failure_threshold=CIRCUIT_BREAKER_MAX_FAILURES,
            recovery_timeout=CIRCUIT_BREAKER_RESET_TIMEOUT
        )
        self.focus_mode_client = focus_mode_client or FocusModeClient()

    async def cooperate_with_focus(self, request_context="conversation"):
        """Queue one non-TeachMe call briefly while TeachMe owns focus."""
        return await self.focus_mode_client.async_defer_if_needed(request_context)

    async def synthesize(
        self,
        text: str,
        voice: str = "default",
        language: str = "en",
        request_context: str = "conversation",
    ) -> ServiceCallResult:
        """
        Send text to TTS Service for speech synthesis.
        Returns audio file bytes.
        
        Args:
            text: Text to synthesize
            voice: The specific voice model to use (e.g., 'en-US-ryan-high')
            language: Target language (informational, service auto-detects)
            
        Returns:
            ServiceCallResult with audio_bytes on success
        """
        try:
            await self.cooperate_with_focus(request_context)
            if self.circuit_breaker.state.value == "OPEN":
                return ServiceCallResult(
                    success=False,
                    error_code="TTS_SERVICE_CIRCUIT_OPEN",
                    error_message="TTS Service is temporarily unavailable"
                )

            # Map generic voice names to actual voice IDs if needed
            voice_mapping = {
                "default": "en-US-ryan-high",
                "female": "en-US-libritts-high",
                "male": "en-US-ryan-high",
                "female_urdu": "ur-PK-kani-female",
                "british": "en-GB-jenny",
            }
            voice_id = voice_mapping.get(voice, voice)

            async with httpx.AsyncClient(timeout=self.timeout, verify=client_verify(self.base_url)) as client:
                payload = {
                    "text": text,
                    "voice_id": voice_id
                }
                response = await client.post(
                    f"{self.base_url}/speak",
                    json=payload,
                    headers=internal_service_headers(),
                )

                if response.status_code == 200:
                    self.circuit_breaker.record_success()
                    # TTS returns audio bytes directly as WAV
                    return ServiceCallResult(
                        success=True,
                        data={
                            "audio_bytes": response.content,
                            "content_type": response.headers.get("content-type", "audio/wav")
                        }
                    )
                else:
                    self.circuit_breaker.record_failure()
                    return ServiceCallResult(
                        success=False,
                        error_code="TTS_SYNTHESIS_FAILED",
                        error_message=f"TTS Service returned {response.status_code}: {response.text[:200]}"
                    )

        except httpx.TimeoutException:
            self.circuit_breaker.record_failure()
            return ServiceCallResult(
                success=False,
                error_code="TTS_SERVICE_TIMEOUT",
                error_message="TTS Service did not respond in time"
            )
        except (httpx.ConnectError, httpx.RequestError):
            self.circuit_breaker.record_failure()
            return ServiceCallResult(
                success=False,
                error_code="TTS_SERVICE_UNREACHABLE",
                error_message="Could not connect to TTS Service"
            )
        except Exception as e:
            self.circuit_breaker.record_failure()
            return ServiceCallResult(
                success=False,
                error_code="TTS_SERVICE_ERROR",
                error_message=f"Unexpected error: {str(e)}"
            )

    async def health_check(self) -> ServiceCallResult:
        """
        Health check without circuit breaker.
        Used to determine if service is up.
        """
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(3.0), verify=client_verify(self.base_url)) as client:
                response = await client.get(f"{self.base_url}/health")
                if response.status_code == 200:
                    return ServiceCallResult(
                        success=True,
                        data=response.json()
                    )
                else:
                    return ServiceCallResult(
                        success=False,
                        error_code="TTS_UNHEALTHY",
                        error_message=f"Health check returned {response.status_code}"
                    )
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
            return ServiceCallResult(
                success=False,
                error_code="TTS_UNREACHABLE",
                error_message="TTS Service is not responding"
            )
        except Exception as e:
            return ServiceCallResult(
                success=False,
                error_code="TTS_HEALTH_ERROR",
                error_message=str(e)
            )
    async def list_voices(self) -> ServiceCallResult:
        """
        Get list of available TTS voices from the service.
        
        Returns:
            ServiceCallResult with list of available voices
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout, verify=client_verify(self.base_url)) as client:
                response = await client.get(f"{self.base_url}/voices")
                
                if response.status_code == 200:
                    self.circuit_breaker.record_success()
                    return ServiceCallResult(
                        success=True,
                        data=response.json()
                    )
                else:
                    self.circuit_breaker.record_failure()
                    return ServiceCallResult(
                        success=False,
                        error_code="TTS_LIST_VOICES_FAILED",
                        error_message=f"TTS Service returned {response.status_code}"
                    )
        
        except httpx.TimeoutException:
            self.circuit_breaker.record_failure()
            return ServiceCallResult(
                success=False,
                error_code="TTS_SERVICE_TIMEOUT",
                error_message="TTS Service did not respond in time"
            )
        except (httpx.ConnectError, httpx.RequestError):
            self.circuit_breaker.record_failure()
            return ServiceCallResult(
                success=False,
                error_code="TTS_SERVICE_UNREACHABLE",
                error_message="Could not connect to TTS Service"
            )
        except Exception as e:
            self.circuit_breaker.record_failure()
            return ServiceCallResult(
                success=False,
                error_code="TTS_SERVICE_ERROR",
                error_message=f"Unexpected error: {str(e)}"
            )
