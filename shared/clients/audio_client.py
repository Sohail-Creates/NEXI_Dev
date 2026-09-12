"""
Audio Service Client

All communication with Audio Service (port 8002) goes through this class.
Never call Audio Service directly from a route handler.
Every method wraps the HTTP call in the circuit breaker.
"""

import httpx
from config.ssl_config import client_verify
from shared.security import internal_service_headers
import logging
from typing import Optional
from ..utils.circuit_breaker import CircuitBreaker, CircuitBreakerException
from .models import ServiceCallResult
from ..config import ServiceConfig

logger = logging.getLogger(__name__)

# Service configuration (dynamically loaded from env vars or localhost)
AUDIO_SERVICE_URL = ServiceConfig.get_service_url("audio")
CIRCUIT_BREAKER_MAX_FAILURES = 3
CIRCUIT_BREAKER_RESET_TIMEOUT = 30


class AudioServiceClient:
    """
    Dedicated client for Audio Service communication.
    Wraps all HTTP calls with circuit breaker pattern.
    Handles timeouts, retries, and error responses.
    """

    def __init__(
        self,
        base_url: str = AUDIO_SERVICE_URL,
        timeout: int = 30,
        max_retries: int = 3
    ):
        self.base_url = base_url
        self.max_retries = max_retries
        self.timeout = httpx.Timeout(
            connect=5.0,
            read=float(timeout),
            write=10.0,
            pool=5.0
        )
        self.circuit_breaker = CircuitBreaker(
            name="audio_service",
            failure_threshold=CIRCUIT_BREAKER_MAX_FAILURES,
            recovery_timeout=CIRCUIT_BREAKER_RESET_TIMEOUT
        )

    async def enroll_speaker(
        self,
        speaker_id: str,
        audio_samples: list,
        phrase: str = "hello"
    ) -> ServiceCallResult:
        """
        Enroll a speaker with multiple audio samples (bytes).
        
        The Audio Service's /enroll-speaker-files endpoint expects file PATHS, not bytes.
        So we first POST the audio bytes to the Audio Service to write them to temp files,
        then call /enroll-speaker-files with those paths.
        
        As a workaround: We use the Audio Service's process-voice endpoint to extract 
        embeddings from each sample, then average them for enrollment.
        
        Args:
            speaker_id: Unique speaker identifier
            audio_samples: List of audio bytes 
            phrase: Enrollment phrase (ignored for file-based enrollment)
            
        Returns:
            ServiceCallResult with enrollment data (user_id, embedding_size, voice_embedding)
        """
        try:
            if self.circuit_breaker.state.value == "OPEN":
                logger.warning("[AudioClient] Circuit breaker OPEN - rejecting enroll_speaker call")
                return ServiceCallResult(
                    success=False,
                    error_code="AUDIO_SERVICE_CIRCUIT_OPEN",
                    error_message="Audio Service is temporarily unavailable (circuit breaker open)"
                )

            logger.info(f"[AudioClient] Enrolling speaker {speaker_id} with {len(audio_samples)} samples")
            
            if not audio_samples or len(audio_samples) == 0:
                return ServiceCallResult(
                    success=False,
                    error_code="NO_AUDIO_SAMPLES",
                    error_message="At least one audio sample required"
                )
            
            # Process each audio sample through /process-voice to get embeddings
            # Then average them for the final speaker embedding
            embeddings = []
            
            logger.info(f"[AudioClient] Starting embedding extraction for {len(audio_samples)} samples from speaker {speaker_id}")
            logger.info(f"[AudioClient] Base URL: {self.base_url}")
            
            async with httpx.AsyncClient(timeout=self.timeout, verify=client_verify(self.base_url)) as client:
                for idx, audio_data in enumerate(audio_samples):
                    try:
                        filename = f"enrollment_{speaker_id}_{idx}.wav"
                        files = {"file": (filename, audio_data, "audio/wav")}
                        
                        logger.info(f"[AudioClient] ===== SAMPLE {idx+1}/{len(audio_samples)} =====")
                        logger.info(f"[AudioClient] File: {filename}")
                        logger.info(f"[AudioClient] Size: {len(audio_data)} bytes")
                        logger.info(f"[AudioClient] Posting to {self.base_url}/api/v1/process-voice")
                        
                        response = await client.post(
                            f"{self.base_url}/api/v1/process-voice",
                            files=files,
                            headers=internal_service_headers(speaker_id),
                        )
                        
                        logger.info(f"[AudioClient]  Response received: status={response.status_code}")
                        
                        if response.status_code == 200:
                            logger.info(f"[AudioClient] Response text length: {len(response.text)} bytes")
                            
                            try:
                                result = response.json()
                                logger.info(f"[AudioClient]  JSON parsed successfully")
                            except Exception as json_err:
                                logger.error(f"[AudioClient]  JSON parsing FAILED: {str(json_err)}")
                                logger.error(f"[AudioClient] Response text: {response.text[:500]}")
                                raise
                            
                            logger.info(f"[AudioClient] Response type: {type(result).__name__}")
                            
                            if isinstance(result, dict):
                                logger.info(f"[AudioClient] Response keys: {list(result.keys())}")
                                logger.info(f"[AudioClient] 'success' key: {result.get('success', 'KEY NOT FOUND')}")
                                logger.info(f"[AudioClient] 'data' key: {'EXISTS' if 'data' in result else 'NOT FOUND'}")
                                
                                # Handle APIResponse structure: embedding is nested under 'data' field
                                if result.get("success"):
                                    logger.info(f"[AudioClient]  success=True")
                                    data = result.get("data", {})
                                    logger.info(f"[AudioClient] Data type: {type(data).__name__}")
                                    
                                    if isinstance(data, dict):
                                        logger.info(f"[AudioClient] Data keys: {list(data.keys())}")
                                        embedding = data.get("embedding")
                                        
                                        if embedding:
                                            if isinstance(embedding, (list, tuple)):
                                                logger.info(f"[AudioClient]  Got embedding: type={type(embedding).__name__}, size={len(embedding)}")
                                                embeddings.append(embedding)
                                                logger.info(f"[AudioClient]  Processed enrollment sample {idx+1}/{len(audio_samples)} - embedding size: {len(embedding)}")
                                            else:
                                                logger.error(f"[AudioClient]  Embedding is wrong type: {type(embedding).__name__} (expected list/tuple)")
                                        else:
                                            logger.error(f"[AudioClient]  Embedding is None/empty in data: {data}")
                                    else:
                                        logger.error(f"[AudioClient]  Data is not a dict, it's {type(data).__name__}: {data}")
                                else:
                                    logger.error(f"[AudioClient]  success=False")
                                    logger.error(f"[AudioClient] Error field: {result.get('error', 'NO ERROR FIELD')}")
                            else:
                                logger.error(f"[AudioClient]  Response is not a dict, it's {type(result).__name__}: {str(result)[:200]}")
                        else:
                            logger.error(f"[AudioClient]  HTTP {response.status_code}")
                            error_text = response.text[:500] if response.text else "NO ERROR TEXT"
                            logger.error(f"[AudioClient] Error response: {error_text}")
                    
                    except Exception as sample_err:
                        logger.error(f"[AudioClient]  EXCEPTION processing sample {idx+1}: {str(sample_err)}")
                        logger.error(f"[AudioClient] Exception type: {type(sample_err).__name__}")
                        import traceback
                        logger.error(f"[AudioClient] Traceback: {traceback.format_exc()}")
                        raise
            
            if not embeddings:
                logger.error(f"[AudioClient] No valid embeddings extracted from {len(audio_samples)} samples")
                return ServiceCallResult(
                    success=False,
                    error_code="NO_VALID_EMBEDDINGS",
                    error_message="Could not extract embeddings from any audio sample"
                )
            
            # Average the embeddings
            import numpy as np
            avg_embedding = list(np.mean(embeddings, axis=0))
            embedding_size = len(avg_embedding)
            
            logger.info(f"[AudioClient] Enrollment SUCCESS - {len(embeddings)} samples, embedding size: {embedding_size}")
            
            self.circuit_breaker.record_success()
            return ServiceCallResult(
                success=True,
                data={
                    "user_id": speaker_id,
                    "speaker_id": speaker_id,
                    "embedding_size": embedding_size,
                    "embedding_array": avg_embedding,
                    "voice_embedding": avg_embedding,
                    "num_samples": len(embeddings),
                    "status": "success",
                    "message": f"Speaker enrolled successfully with {len(embeddings)} samples"
                }
            )

        except httpx.TimeoutException as e:
            self.circuit_breaker.record_failure()
            logger.error(f"[AudioClient] enroll_speaker TIMEOUT: {str(e)}")
            return ServiceCallResult(
                success=False,
                error_code="AUDIO_SERVICE_TIMEOUT",
                error_message="Audio Service enrollment timeout"
            )
        except (httpx.ConnectError, httpx.RequestError) as e:
            self.circuit_breaker.record_failure()
            logger.error(f"[AudioClient] enroll_speaker UNREACHABLE: {str(e)}")
            return ServiceCallResult(
                success=False,
                error_code="AUDIO_SERVICE_UNREACHABLE",
                error_message="Could not connect to Audio Service"
            )
        except Exception as e:
            self.circuit_breaker.record_failure()
            logger.error(f"[AudioClient] enroll_speaker ERROR: {str(e)}")
            return ServiceCallResult(
                success=False,
                error_code="AUDIO_SERVICE_ERROR",
                error_message=f"Unexpected error: {str(e)}"
            )

    async def process_voice(
        self,
        audio_file_bytes: bytes,
        filename: str
    ) -> ServiceCallResult:
        """
        Send audio file to Audio Service for embedding extraction.
        Returns ServiceCallResult with embeddings in the data field on success.
        
        Args:
            audio_file_bytes: Raw audio bytes
            filename: Original filename
            
        Returns:
            ServiceCallResult with embeddings on success, error details on failure
        """
        try:
            logger.info(f"[process_voice] Called with filename={filename}, size={len(audio_file_bytes)} bytes")
            
            if self.circuit_breaker.state.value == "OPEN":
                logger.warning("[process_voice] Circuit breaker OPEN - rejecting call")
                return ServiceCallResult(
                    success=False,
                    error_code="AUDIO_SERVICE_CIRCUIT_OPEN",
                    error_message="Audio Service is temporarily unavailable (circuit breaker open)"
                )

            logger.info(f"[process_voice] Calling Audio Service: POST /api/v1/process-voice with file {filename} ({len(audio_file_bytes)} bytes)")
            async with httpx.AsyncClient(timeout=self.timeout, verify=client_verify(self.base_url)) as client:
                files = {"file": (filename, audio_file_bytes, "audio/wav")}
                response = await client.post(
                    f"{self.base_url}/api/v1/process-voice",
                    files=files,
                    headers=internal_service_headers(),
                )
                logger.info(f"[process_voice]  Response: status={response.status_code}")

                if response.status_code == 200:
                    self.circuit_breaker.record_success()
                    logger.info(f"[process_voice] Parsing response...")
                    
                    try:
                        result_data = response.json()
                        logger.info(f"[process_voice]  JSON parsed, type={type(result_data).__name__}")
                    except Exception as json_err:
                        logger.error(f"[process_voice]  JSON parsing failed: {str(json_err)}")
                        logger.error(f"[process_voice] Response text: {response.text[:500]}")
                        raise
                    
                    # Handle APIResponse structure: embedding is nested under 'data' field
                    if isinstance(result_data, dict) and result_data.get("success"):
                        logger.info(f"[process_voice]  success=True")
                        data = result_data.get("data", {})
                        embedding = data.get("embedding", []) if isinstance(data, dict) else []
                        logger.info(f"[process_voice]  Extracted embedding: size={len(embedding) if isinstance(embedding, (list, tuple)) else 'NOT A LIST'}")
                        logger.info(f"[process_voice] SUCCESS - embedding dimensions: {len(embedding)}")
                        # Return only the inner data, not the full APIResponse
                        return ServiceCallResult(
                            success=True,
                            data=data
                        )
                    else:
                        logger.error(f"[process_voice]  Unexpected response structure: success={result_data.get('success') if isinstance(result_data, dict) else 'not a dict'}")
                        logger.error(f"[process_voice] Response: {str(result_data)[:300]}")
                        self.circuit_breaker.record_failure()
                        return ServiceCallResult(
                            success=False,
                            error_code="INVALID_RESPONSE_FORMAT",
                            error_message="Audio Service returned unexpected response structure"
                        )
                else:
                    self.circuit_breaker.record_failure()
                    error_text = response.text[:500] if response.text else "NO ERROR TEXT"
                    logger.error(f"[process_voice]  HTTP {response.status_code}: {error_text}")
                    return ServiceCallResult(
                        success=False,
                        error_code="AUDIO_PROCESSING_FAILED",
                        error_message=f"Audio Service returned {response.status_code}: {response.text[:200]}"
                    )

        except httpx.TimeoutException as e:
            self.circuit_breaker.record_failure()
            logger.error(f"[AudioClient] process_voice TIMEOUT: {str(e)}")
            return ServiceCallResult(
                success=False,
                error_code="AUDIO_SERVICE_TIMEOUT",
                error_message="Audio Service did not respond in time"
            )
        except (httpx.ConnectError, httpx.RequestError) as e:
            self.circuit_breaker.record_failure()
            logger.error(f"[AudioClient] process_voice UNREACHABLE: {str(e)}")
            return ServiceCallResult(
                success=False,
                error_code="AUDIO_SERVICE_UNREACHABLE",
                error_message="Could not connect to Audio Service"
            )
        except Exception as e:
            self.circuit_breaker.record_failure()
            logger.error(f"[AudioClient] process_voice ERROR: {str(e)}")
            return ServiceCallResult(
                success=False,
                error_code="AUDIO_SERVICE_ERROR",
                error_message=f"Unexpected error: {str(e)}"
            )

    async def verify_speaker(
        self,
        audio_file_bytes: bytes,
        filename: str,
        user_id: str
    ) -> ServiceCallResult:
        """
        Send audio file + user_id to Audio Service for speaker verification.
        Returns ServiceCallResult with match score and decision.
        
        Args:
            audio_file_bytes: Raw audio bytes
            filename: Original filename
            user_id: The user to verify against
            
        Returns:
            ServiceCallResult with verification result on success
        """
        try:
            if self.circuit_breaker.state.value == "OPEN":
                logger.warning("[AudioClient] Circuit breaker OPEN - rejecting verify_speaker call")
                return ServiceCallResult(
                    success=False,
                    error_code="AUDIO_SERVICE_CIRCUIT_OPEN",
                    error_message="Audio Service is temporarily unavailable"
                )

            logger.info(f"[AudioClient] Calling Audio Service: POST /verify-speaker for user_id={user_id}, file={filename}")
            async with httpx.AsyncClient(timeout=self.timeout, verify=client_verify(self.base_url)) as client:
                files = {"file": (filename, audio_file_bytes, "audio/wav")}
                data = {"user_id": user_id}
                response = await client.post(
                    f"{self.base_url}/api/v1/verify-speaker",
                    files=files,
                    data=data,
                    headers=internal_service_headers(user_id),
                )
                logger.info(f"[AudioClient] Audio Service response: status={response.status_code}")

                if response.status_code == 200:
                    self.circuit_breaker.record_success()
                    result_data = response.json()
                    # Accept the service's direct response and its legacy APIResponse envelope.
                    if isinstance(result_data, dict):
                        data = result_data.get("data", result_data)
                        match = data.get("is_verified", data.get("match", False))
                        similarity = data.get("confidence", data.get("similarity", 0.0))
                        data["verified"] = match
                        data["similarity"] = similarity
                        logger.info(f"[AudioClient] verify_speaker SUCCESS - match={match}, similarity={similarity:.3f}")
                        return ServiceCallResult(
                            success=True,
                            data=data
                        )
                    else:
                        logger.error(f"[AudioClient] verify_speaker got unexpected response structure: {result_data}")
                        self.circuit_breaker.record_failure()
                        return ServiceCallResult(
                            success=False,
                            error_code="INVALID_RESPONSE_FORMAT",
                            error_message="Audio Service returned unexpected response structure"
                        )
                else:
                    self.circuit_breaker.record_failure()
                    logger.error(f"[AudioClient] verify_speaker FAILED: status={response.status_code}")
                    return ServiceCallResult(
                        success=False,
                        error_code="SPEAKER_VERIFICATION_FAILED",
                        error_message=f"Audio Service returned {response.status_code}"
                    )

        except httpx.TimeoutException:
            self.circuit_breaker.record_failure()
            logger.error("[AudioClient] verify_speaker TIMEOUT")
            return ServiceCallResult(
                success=False,
                error_code="AUDIO_SERVICE_TIMEOUT",
                error_message="Audio Service verification timeout"
            )
        except (httpx.ConnectError, httpx.RequestError):
            self.circuit_breaker.record_failure()
            logger.error("[AudioClient] verify_speaker UNREACHABLE")
            return ServiceCallResult(
                success=False,
                error_code="AUDIO_SERVICE_UNREACHABLE",
                error_message="Cannot reach Audio Service"
            )
        except Exception as e:
            self.circuit_breaker.record_failure()
            logger.error(f"[AudioClient] verify_speaker ERROR: {str(e)}")
            return ServiceCallResult(
                success=False,
                error_code="AUDIO_SERVICE_ERROR",
                error_message=str(e)
            )

    async def transcribe(
        self,
        audio_file_bytes: bytes,
        filename: str,
        language: str = "auto"
    ) -> ServiceCallResult:
        """
        Send audio file to Audio Service for speech-to-text transcription.
        
        Args:
            audio_file_bytes: Raw audio bytes
            filename: Original filename
            language: Target language ('en', 'ur', 'auto')
            
        Returns:
            ServiceCallResult with transcription on success
        """
        try:
            if self.circuit_breaker.state.value == "OPEN":
                logger.warning("[AudioClient] Circuit breaker OPEN - rejecting transcribe call")
                return ServiceCallResult(
                    success=False,
                    error_code="AUDIO_SERVICE_CIRCUIT_OPEN",
                    error_message="Audio Service is temporarily unavailable"
                )

            logger.info(f"[AudioClient] Calling Audio Service: POST /transcribe with file={filename}, language={language}")
            async with httpx.AsyncClient(timeout=self.timeout, verify=client_verify(self.base_url)) as client:
                files = {"file": (filename, audio_file_bytes, "audio/wav")}
                data = {"language": language}
                response = await client.post(
                    f"{self.base_url}/transcribe",
                    files=files,
                    data=data,
                    headers=internal_service_headers(),
                )
                logger.info(f"[AudioClient] Audio Service response: status={response.status_code}")

                if response.status_code == 200:
                    self.circuit_breaker.record_success()
                    result_data = response.json()
                    transcription = result_data.get('transcription', '')
                    logger.info(f"[AudioClient] transcribe SUCCESS - text: '{transcription[:100]}...'")
                    return ServiceCallResult(
                        success=True,
                        data=result_data
                    )
                else:
                    self.circuit_breaker.record_failure()
                    logger.error(f"[AudioClient] transcribe FAILED: status={response.status_code}")
                    return ServiceCallResult(
                        success=False,
                        error_code="TRANSCRIPTION_FAILED",
                        error_message=f"Audio Service returned {response.status_code}"
                    )

        except httpx.TimeoutException:
            self.circuit_breaker.record_failure()
            logger.error("[AudioClient] transcribe TIMEOUT")
            return ServiceCallResult(
                success=False,
                error_code="AUDIO_SERVICE_TIMEOUT",
                error_message="Transcription timeout"
            )
        except (httpx.ConnectError, httpx.RequestError):
            self.circuit_breaker.record_failure()
            logger.error("[AudioClient] transcribe UNREACHABLE")
            return ServiceCallResult(
                success=False,
                error_code="AUDIO_SERVICE_UNREACHABLE",
                error_message="Cannot reach Audio Service"
            )
        except Exception as e:
            self.circuit_breaker.record_failure()
            logger.error(f"[AudioClient] transcribe ERROR: {str(e)}")
            return ServiceCallResult(
                success=False,
                error_code="AUDIO_SERVICE_ERROR",
                error_message=str(e)
            )

    async def start_wake_word(self) -> ServiceCallResult:
        """Start the continuous wake word detection loop on Audio Service."""
        try:
            if self.circuit_breaker.state.value == "OPEN":
                logger.warning("[AudioClient] Circuit breaker OPEN - rejecting start_wake_word call")
                return ServiceCallResult(
                    success=False,
                    error_code="AUDIO_SERVICE_CIRCUIT_OPEN",
                    error_message="Audio Service is temporarily unavailable"
                )

            logger.info("[AudioClient] Calling Audio Service: POST /wake-word/start")
            async with httpx.AsyncClient(timeout=self.timeout, verify=client_verify(self.base_url)) as client:
                response = await client.post(f"{self.base_url}/wake-word/start", headers=internal_service_headers())
                logger.info(f"[AudioClient] Audio Service response: status={response.status_code}")
                if response.status_code == 200:
                    self.circuit_breaker.record_success()
                    logger.info("[AudioClient] start_wake_word SUCCESS")
                    return ServiceCallResult(
                        success=True,
                        data=response.json()
                    )
                else:
                    self.circuit_breaker.record_failure()
                    logger.error(f"[AudioClient] start_wake_word FAILED: status={response.status_code}")
                    return ServiceCallResult(
                        success=False,
                        error_code="WAKE_WORD_START_FAILED",
                        error_message=f"Audio Service returned {response.status_code}"
                    )

        except httpx.TimeoutException:
            self.circuit_breaker.record_failure()
            logger.error("[AudioClient] start_wake_word TIMEOUT")
            return ServiceCallResult(
                success=False,
                error_code="AUDIO_SERVICE_TIMEOUT",
                error_message="Wake word start timeout"
            )
        except (httpx.ConnectError, httpx.RequestError):
            self.circuit_breaker.record_failure()
            logger.error("[AudioClient] start_wake_word UNREACHABLE")
            return ServiceCallResult(
                success=False,
                error_code="AUDIO_SERVICE_UNREACHABLE",
                error_message="Cannot reach Audio Service"
            )
        except Exception as e:
            self.circuit_breaker.record_failure()
            logger.error(f"[AudioClient] start_wake_word ERROR: {str(e)}")
            return ServiceCallResult(
                success=False,
                error_code="AUDIO_SERVICE_ERROR",
                error_message=str(e)
            )

    async def stop_wake_word(self) -> ServiceCallResult:
        """Stop the wake word detection loop."""
        try:
            if self.circuit_breaker.state.value == "OPEN":
                logger.warning("[AudioClient] Circuit breaker OPEN - rejecting stop_wake_word call")
                return ServiceCallResult(
                    success=False,
                    error_code="AUDIO_SERVICE_CIRCUIT_OPEN",
                    error_message="Audio Service is temporarily unavailable"
                )

            logger.info("[AudioClient] Calling Audio Service: POST /wake-word/stop")
            async with httpx.AsyncClient(timeout=self.timeout, verify=client_verify(self.base_url)) as client:
                response = await client.post(f"{self.base_url}/wake-word/stop", headers=internal_service_headers())
                logger.info(f"[AudioClient] Audio Service response: status={response.status_code}")
                if response.status_code == 200:
                    self.circuit_breaker.record_success()
                    logger.info("[AudioClient] stop_wake_word SUCCESS")
                    return ServiceCallResult(
                        success=True,
                        data=response.json()
                    )
                else:
                    self.circuit_breaker.record_failure()
                    logger.error(f"[AudioClient] stop_wake_word FAILED: status={response.status_code}")
                    return ServiceCallResult(
                        success=False,
                        error_code="WAKE_WORD_STOP_FAILED",
                        error_message=f"Audio Service returned {response.status_code}"
                    )

        except httpx.TimeoutException:
            self.circuit_breaker.record_failure()
            logger.error("[AudioClient] stop_wake_word TIMEOUT")
            return ServiceCallResult(
                success=False,
                error_code="AUDIO_SERVICE_TIMEOUT",
                error_message="Wake word stop timeout"
            )
        except (httpx.ConnectError, httpx.RequestError):
            self.circuit_breaker.record_failure()
            logger.error("[AudioClient] stop_wake_word UNREACHABLE")
            return ServiceCallResult(
                success=False,
                error_code="AUDIO_SERVICE_UNREACHABLE",
                error_message="Cannot reach Audio Service"
            )
        except Exception as e:
            self.circuit_breaker.record_failure()
            logger.error(f"[AudioClient] stop_wake_word ERROR: {str(e)}")
            return ServiceCallResult(
                success=False,
                error_code="AUDIO_SERVICE_ERROR",
                error_message=str(e)
            )

    async def get_wake_word_status(self) -> ServiceCallResult:
        """Get current state of wake word detection."""
        try:
            if self.circuit_breaker.state.value == "OPEN":
                logger.warning("[AudioClient] Circuit breaker OPEN - rejecting get_wake_word_status call")
                return ServiceCallResult(
                    success=False,
                    error_code="AUDIO_SERVICE_CIRCUIT_OPEN",
                    error_message="Audio Service is temporarily unavailable"
                )

            logger.info("[AudioClient] Calling Audio Service: GET /wake-word/status")
            async with httpx.AsyncClient(timeout=self.timeout, verify=client_verify(self.base_url)) as client:
                response = await client.get(f"{self.base_url}/wake-word/status", headers=internal_service_headers())
                logger.info(f"[AudioClient] Audio Service response: status={response.status_code}")
                if response.status_code == 200:
                    self.circuit_breaker.record_success()
                    result_data = response.json()
                    logger.info(f"[AudioClient] get_wake_word_status SUCCESS - active={result_data.get('is_listening', False)}")
                    return ServiceCallResult(
                        success=True,
                        data=result_data
                    )
                else:
                    self.circuit_breaker.record_failure()
                    logger.error(f"[AudioClient] get_wake_word_status FAILED: status={response.status_code}")
                    return ServiceCallResult(
                        success=False,
                        error_code="WAKE_WORD_STATUS_FAILED",
                        error_message=f"Audio Service returned {response.status_code}"
                    )

        except httpx.TimeoutException:
            self.circuit_breaker.record_failure()
            logger.error("[AudioClient] get_wake_word_status TIMEOUT")
            return ServiceCallResult(
                success=False,
                error_code="AUDIO_SERVICE_TIMEOUT",
                error_message="Status check timeout"
            )
        except (httpx.ConnectError, httpx.RequestError):
            self.circuit_breaker.record_failure()
            logger.error("[AudioClient] get_wake_word_status UNREACHABLE")
            return ServiceCallResult(
                success=False,
                error_code="AUDIO_SERVICE_UNREACHABLE",
                error_message="Cannot reach Audio Service"
            )
        except Exception as e:
            self.circuit_breaker.record_failure()
            logger.error(f"[AudioClient] get_wake_word_status ERROR: {str(e)}")
            return ServiceCallResult(
                success=False,
                error_code="AUDIO_SERVICE_ERROR",
                error_message=str(e)
            )

    async def health_check(self) -> ServiceCallResult:
        """
        Health check does NOT go through circuit breaker.
        It is used to determine if the service is up, which is what the circuit breaker itself needs.
        """
        try:
            logger.info("[AudioClient] Calling Audio Service: GET /health")
            async with httpx.AsyncClient(timeout=httpx.Timeout(3.0), verify=client_verify(self.base_url)) as client:
                response = await client.get(f"{self.base_url}/health")
                logger.info(f"[AudioClient] Audio Service health check: status={response.status_code}")
                if response.status_code == 200:
                    logger.info("[AudioClient] Audio Service is HEALTHY")
                    return ServiceCallResult(
                        success=True,
                        data=response.json()
                    )
                else:
                    logger.error(f"[AudioClient] Audio Service health check FAILED: status={response.status_code}")
                    return ServiceCallResult(
                        success=False,
                        error_code="AUDIO_UNHEALTHY",
                        error_message=f"Health check returned {response.status_code}"
                    )
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
            logger.error("[AudioClient] Audio Service is UNREACHABLE")
            return ServiceCallResult(
                success=False,
                error_code="AUDIO_UNREACHABLE",
                error_message="Audio Service is not responding"
            )
        except Exception as e:
            logger.error(f"[AudioClient] Health check ERROR: {str(e)}")
            return ServiceCallResult(
                success=False,
                error_code="AUDIO_HEALTH_ERROR",
                error_message=str(e)
            )
