"""
Audio Service Client for Enrollment Service

This client provides enrollment-specific methods for interacting with the Audio Service.
Uses the shared AudioServiceClient from shared/clients/audio_client.py
"""

import sys
from pathlib import Path
import logging

# Add parent directories to path for shared utilities
sys_path = str(Path(__file__).resolve().parent.parent.parent.parent)
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

from shared.clients.audio_client import AudioServiceClient
from shared.utils.error_handling import ServiceUnavailableError, ServiceTimeoutError, APIError

logger = logging.getLogger(__name__)


class AudioClient:
    """
    Audio Service Client wrapper for enrollment operations.
    
    Provides high-level methods for speaker enrollment and verification.
    Wraps the shared AudioServiceClient for consistency.
    """
    
    def __init__(self):
        """Initialize the audio client."""
        self.client = AudioServiceClient()

    async def sync_speakers_from_central(self) -> dict:
        """Ask Audio to atomically refresh its verification store from Central."""
        import httpx
        from config.ssl_config import client_verify
        from shared.security import internal_service_headers

        base_url = self.client.base_url.rstrip("/")
        async with httpx.AsyncClient(
            timeout=self.client.timeout,
            verify=client_verify(base_url),
        ) as client:
            response = await client.post(
                f"{base_url}/api/v1/speaker-sync",
                headers=internal_service_headers(),
            )
            response.raise_for_status()
            result = response.json()
        if result.get("success") is not True:
            raise RuntimeError(result.get("message") or "Audio speaker sync failed")
        return result
    
    async def enroll_speaker(self, speaker_id: str, audio_bytes: bytes) -> dict:
        """
        Enroll a speaker with audio samples.
        
        Args:
            speaker_id: Unique identifier for the speaker
            audio_bytes: Raw audio data in bytes
            
        Returns:
            dict: Enrollment result with speaker embeddings
            
        Raises:
            ServiceUnavailableError: If audio service is unavailable
            ServiceTimeoutError: If request times out
            APIError: For other API errors
        """
        try:
            logger.info(f"Enrolling speaker {speaker_id}")
            
            # Use correct parameters for shared client process_voice
            result = await self.client.process_voice(
                audio_file_bytes=audio_bytes,  # Correct parameter name
                filename=f"enrollment_{speaker_id}.wav"  # Required parameter
            )
            
            if not result.success:
                logger.error(f"Audio processing failed: {result.error_message}")
                raise Exception(f"Audio processing failed: {result.error_message}")
            
            # Extract embeddings from ServiceCallResult data
            data = result.data or {}
            embeddings = data.get("embeddings") or data.get("embedding") or data.get("voice_embedding")
            logger.info(f"Speaker {speaker_id} enrolled successfully")
            return {
                "success": True,
                "embeddings": embeddings,
                "speaker_id": speaker_id
            }
            
        except Exception as e:
            logger.error(f"Failed to enroll speaker {speaker_id}: {e}")
            raise
    
    async def verify_speaker(self, speaker_id: str, audio_bytes: bytes) -> dict:
        """
        Verify a speaker from audio sample.
        
        Args:
            speaker_id: ID of speaker to verify
            audio_bytes: Raw audio data for verification
            
        Returns:
            dict: Verification result with confidence score
            
        Raises:
            ServiceUnavailableError: If audio service is unavailable
            ServiceTimeoutError: If request times out
            APIError: For other API errors
        """
        try:
            logger.info(f"Verifying speaker {speaker_id}")
            
            # Use correct method from shared client
            result = await self.client.verify_speaker(
                speaker_id=speaker_id,
                audio_file_bytes=audio_bytes,
                filename="verification.wav"
            )
            
            if result.success:
                logger.info(f"Speaker {speaker_id} verified")
                return {
                    "success": True,
                    "verified": result.data.get("verified", False),
                    "confidence": result.data.get("confidence", 0.0),
                    "speaker_id": result.data.get("speaker_id", speaker_id)
                }
            else:
                logger.error(f"Verification failed: {result.error_message}")
                return {
                    "success": False,
                    "error": result.error_message
                }
            
        except Exception as e:
            logger.error(f"Failed to verify speaker {speaker_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def extract_speaker_embeddings(self, audio_bytes: bytes) -> dict:
        """
        Extract speaker embeddings from audio sample.
        
        Args:
            audio_bytes: Raw audio data
            
        Returns:
            dict: Embeddings and metadata
            
        Raises:
            ServiceUnavailableError: If audio service is unavailable
            ServiceTimeoutError: If request times out
            APIError: For other API errors
        """
        try:
            logger.info("Extracting speaker embeddings")
            result = await self.client.extract_embeddings(audio_data=audio_bytes)
            logger.info(" Speaker embeddings extracted successfully")
            return result
        except Exception as e:
            logger.error(f"Failed to extract embeddings: {e}")
            raise
    
    async def transcribe_audio(self, audio_bytes: bytes) -> dict:
        """
        Transcribe audio to text.
        
        Args:
            audio_bytes: Raw audio data
            
        Returns:
            dict: Transcription result with text
            
        Raises:
            ServiceUnavailableError: If audio service is unavailable
            ServiceTimeoutError: If request times out
            APIError: For other API errors
        """
        try:
            logger.info("Transcribing audio")
            result = await self.client.get_transcription(audio_data=audio_bytes)
            logger.info(" Audio transcribed successfully")
            return result
        except Exception as e:
            logger.error(f"Failed to transcribe audio: {e}")
            raise
    
    async def process_voice_sample(self, audio_bytes: bytes) -> dict:
        """
        Process voice sample (transcribe and extract embeddings).
        
        Args:
            audio_bytes: Raw audio data
            
        Returns:
            dict: Processing result with transcription and embeddings
            
        Raises:
            ServiceUnavailableError: If audio service is unavailable
            ServiceTimeoutError: If request times out
            APIError: For other API errors
        """
        try:
            logger.info("Processing voice sample")
            result = await self.client.process_voice(
                audio_file_bytes=audio_bytes,  # Correct parameter name
                filename="voice_sample.wav"     # Required parameter
            )
            if not result.success:
                logger.error(f"Voice processing failed: {result.error_message}")
                raise Exception(f"Voice processing failed: {result.error_message}")
            logger.info(" Voice sample processed successfully")
            # Return result data, not the ServiceCallResult object
            return result.data or {}
        except Exception as e:
            logger.error(f"Failed to process voice sample: {e}")
            raise
    
    async def check_health(self) -> bool:
        """
        Check if Audio Service is healthy.
        
        Returns:
            bool: True if service is available, False otherwise
        """
        try:
            result = await self.client.health_check()
            is_healthy = result.get("status") == "healthy" or result.get("status") == "success"
            if is_healthy:
                logger.info(" Audio Service is healthy")
            else:
                logger.warning(" Audio Service reported unhealthy status")
            return is_healthy
        except Exception as e:
            logger.warning(f" Audio Service health check failed: {e}")
            return False
    
    async def list_speakers(self) -> list:
        """
        Get list of enrolled speakers.
        
        Returns:
            list: List of speaker IDs
            
        Raises:
            ServiceUnavailableError: If audio service is unavailable
            APIError: For other API errors
        """
        try:
            logger.info("Fetching enrolled speakers list")
            result = await self.client.list_speakers()
            logger.info(f" Retrieved {len(result)} enrolled speakers")
            return result
        except Exception as e:
            logger.error(f"Failed to list speakers: {e}")
            raise
    
    async def delete_speaker(self, speaker_id: str) -> dict:
        """
        Delete a speaker enrollment.
        
        Args:
            speaker_id: ID of speaker to delete
            
        Returns:
            dict: Deletion result
            
        Raises:
            ServiceUnavailableError: If audio service is unavailable
            APIError: For other API errors
        """
        try:
            logger.info(f"Deleting speaker enrollment: {speaker_id}")
            result = await self.client.delete_speaker(speaker_id=speaker_id)
            logger.info(f" Speaker {speaker_id} deleted successfully")
            return result
        except Exception as e:
            logger.error(f"Failed to delete speaker {speaker_id}: {e}")
            raise
    
    async def get_voice_embedding(self, audio_path: str) -> dict:
        """
        Get voice embedding from audio file.
        
        Args:
            audio_path: Path to the audio file
            
        Returns:
            dict: Dictionary with embedding and quality_score
            
        Raises:
            FileNotFoundError: If audio file doesn't exist
            APIError: For other API errors
        """
        try:
            import os
            
            # Validate file exists
            if not os.path.exists(audio_path):
                logger.error(f"Audio file not found: {audio_path}")
                raise FileNotFoundError(f"Audio file not found: {audio_path}")
            
            logger.info(f"Extracting voice embedding from: {audio_path}")
            
            # Read audio file
            with open(audio_path, 'rb') as f:
                audio_bytes = f.read()
            
            # Get embeddings using shared client (returns ServiceCallResult, not dict)
            import os
            filename = os.path.basename(audio_path)
            result = await self.client.process_voice(
                audio_file_bytes=audio_bytes,  # Correct parameter name
                filename=filename               # Required parameter
            )
            
            if not result.success:
                error_msg = result.error_message or "Voice embedding extraction failed"
                logger.error(f"Voice embedding extraction failed: {error_msg}")
                raise Exception(f"Audio processing failed: {error_msg}")
            
            # Extract data from ServiceCallResult
            data = result.data or {}
            logger.info(f" Voice embedding extracted successfully (quality: {data.get('quality_score', 0):.3f})")
            
            return {
                "embedding": data.get("embedding"),
                "quality_score": float(data.get("quality_score", 0.0)),
                "voice_detected": data.get("voice_detected", True)
            }
        except Exception as e:
            logger.error(f"Failed to get voice embedding: {e}")
            raise
