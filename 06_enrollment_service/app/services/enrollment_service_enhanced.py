"""
Enhanced Enrollment Service with Complete Speaker Enrollment
============================================================

Integration Points:
1. Vision Service (Port 8001) - Face embeddings
2. Audio Service (Port 8002) - Voice embeddings & speaker enrollment
3. Central Server (Port 8000) - User registration & persistence

Complete Enrollment Workflow:
1. Collect user info (name, age, relation)
2. Collect 5 photos → Face embeddings → Central Server
3. Collect 5 voice samples → Speaker enrollment in Audio Service → Voice embeddings → Central Server
4. Register user with both embeddings in Central Server
5. Encrypt and store locally

Runtime Voice Verification Flow:
1. Capture audio on robot
2. Detect wake word
3. Verify speaker (Audio Service checks against enrolled speakers)
4. If verified → Proceed with transcription
5. If not verified → Return "Speaker not recognized"
"""

import os
import asyncio
from datetime import datetime
from typing import Dict, Optional, List, Tuple, Any
from fastapi import UploadFile, HTTPException
import logging

from app.utils.file_handler import save_uploaded_file, ALLOWED_IMAGE_TYPES, ALLOWED_AUDIO_TYPES
from app.clients.vision_client import VisionClient
from app.clients.audio_client_complete import AudioClientComplete
from app.clients.central_server_client import CentralServerClient
from app.utils.storage import get_storage
from app.utils.progress_tracker import EnrollmentProgress
from app.utils.validators import EnrollmentValidator, ValidationError, ErrorFormatter

logger = logging.getLogger(__name__)


class EnrollmentServiceEnhanced:
    """Enhanced enrollment service with complete audio integration"""
    
    def __init__(self, upload_dir: str, max_photo_size: int, max_voice_size: int):
        self.upload_dir = upload_dir
        self.max_photo_size = max_photo_size
        self.max_voice_size = max_voice_size
        
        # Initialize service clients
        self.vision_client = VisionClient()
        self.audio_client = AudioClientComplete()  # Use comprehensive client
        self.central_server_client = CentralServerClient()
        
        # Validator is a utility class, no instantiation needed
        self.validator = EnrollmentValidator
        
        # Initialize secure storage
        storage_dir = os.getenv("ENROLLMENT_DATA_DIR", "./enrollment_data")
        enable_encryption = os.getenv("ENABLE_ENCRYPTION", "true").lower() == "true"
        self.storage = get_storage(storage_dir, enable_encryption)
        
        logger.info("EnrollmentServiceEnhanced initialized")
    
    # ========================================================================
    # DEPENDENCY CHECKS
    # ========================================================================
    
    async def check_dependencies(self) -> Dict[str, bool]:
        """Check if all required services are available"""
        deps = {
            "vision_service": await self.vision_client.check_health(),
            "audio_service": await self.audio_client.check_health(),
            "central_server": await self.central_server_client.check_health()
        }
        logger.info(f"Dependency check: {deps}")
        return deps
    
    # ========================================================================
    # ENHANCED ENROLLMENT WORKFLOW
    # ========================================================================
    
    async def process_enrollment_complete(
        self,
        user_name: str,
        photos: List[UploadFile],
        voice_samples: List[UploadFile],
        age: Optional[int] = None,
        relation: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Complete enrollment workflow with voice speaker enrollment
        
        Steps:
        1. Validate inputs
        2. Process & save files
        3. Extract face embeddings
        4. Enroll speaker in Audio Service
        5. Extract voice embeddings
        6. Register user in Central Server
        7. Store locally
        
        Returns:
            Dict with enrollment result and user_id
        """
        progress = EnrollmentProgress(user_name)
        photo_paths = []
        voice_paths = []
        
        try:
            # ================================================================
            # STEP 1: VALIDATE INPUTS
            # ================================================================
            logger.info(f"Starting enrollment: user={user_name}")
            progress.update_stage("validating", "Validating inputs...")
            
            try:
                # Validate individual fields
                user_name = self.validator.validate_username(user_name)
                self.validator.validate_file_count(photos, voice_samples)
                metadata = self.validator.validate_optional_metadata(age=age, relation=relation)
            except ValidationError as e:
                logger.error(f"Validation failed: {e}")
                raise HTTPException(status_code=400, detail=str(e))
            
            # ================================================================
            # STEP 2: SAVE FILES
            # ================================================================
            progress.update_stage("saving_files", "Saving photos and audio files...")
            
            # Save photos
            for i, photo in enumerate(photos, 1):
                try:
                    file_path = await save_uploaded_file(
                        photo,
                        self.upload_dir,
                        ALLOWED_IMAGE_TYPES,
                        self.max_photo_size
                    )
                    photo_paths.append(file_path)
                    logger.debug(f"Photo {i} saved: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to save photo {i}: {e}")
                    raise HTTPException(status_code=400, detail=f"Photo {i} save failed: {str(e)}")
            
            # Save voice samples
            for i, voice in enumerate(voice_samples, 1):
                try:
                    file_path = await save_uploaded_file(
                        voice,
                        self.upload_dir,
                        ALLOWED_AUDIO_TYPES,
                        self.max_voice_size
                    )
                    voice_paths.append(file_path)
                    logger.debug(f"Voice {i} saved: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to save voice {i}: {e}")
                    raise HTTPException(status_code=400, detail=f"Voice {i} save failed: {str(e)}")
            
            # ================================================================
            # STEP 3: EXTRACT FACE EMBEDDINGS
            # ================================================================
            progress.update_stage("processing_face", "Processing face embeddings...")
            
            face_embeddings = []
            face_confidences = []
            
            for i, photo_path in enumerate(photo_paths, 1):
                try:
                    embedding = await self.vision_client.get_face_embedding(photo_path)
                    face_embeddings.append(embedding["embedding"])
                    face_confidences.append(embedding.get("confidence", 0.0))
                    logger.info(f"Face {i} embedding extracted, confidence={embedding.get('confidence', 0.0):.4f}")
                except Exception as e:
                    logger.error(f"Face embedding extraction failed for {i}: {e}")
                    raise HTTPException(status_code=503, detail=f"Face processing failed: {str(e)}")
            
            avg_face_confidence = sum(face_confidences) / len(face_confidences) if face_confidences else 0.0
            logger.info(f"Average face confidence: {avg_face_confidence:.4f}")
            
            # ================================================================
            # STEP 4: SPEAKER ENROLLMENT IN AUDIO SERVICE
            # ================================================================
            progress.update_stage("speaker_enrollment", "Enrolling speaker in Audio Service...")
            
            try:
                enrollment_result = await self.audio_client.enroll_speaker_with_files(
                    user_id=user_name,
                    audio_files=voice_paths
                )
                logger.info(f"Speaker enrolled successfully: {user_name}")
                logger.debug(f"Enrollment result: {enrollment_result}")
            except Exception as e:
                logger.error(f"Speaker enrollment failed: {e}")
                raise HTTPException(status_code=503, detail=f"Speaker enrollment failed: {str(e)}")
            
            # ================================================================
            # STEP 5: EXTRACT VOICE EMBEDDINGS
            # ================================================================
            progress.update_stage("processing_voice", "Processing voice embeddings...")
            
            voice_embeddings = []
            voice_qualities = []
            
            for i, voice_path in enumerate(voice_paths, 1):
                try:
                    embedding_data = await self.audio_client.get_voice_embedding(voice_path)
                    voice_embeddings.append(embedding_data["embedding"])
                    voice_qualities.append(embedding_data.get("quality_score", 0.0))
                    logger.info(f"Voice {i} embedding extracted, quality={embedding_data.get('quality_score', 0.0):.4f}")
                except Exception as e:
                    logger.error(f"Voice embedding extraction failed for {i}: {e}")
                    raise HTTPException(status_code=503, detail=f"Voice processing failed: {str(e)}")
            
            avg_voice_quality = sum(voice_qualities) / len(voice_qualities) if voice_qualities else 0.0
            logger.info(f"Average voice quality: {avg_voice_quality:.4f}")
            
            # ================================================================
            # STEP 6: REGISTER USER IN CENTRAL SERVER
            # ================================================================
            progress.update_stage("registering", "Registering user in Central Server...")
            
            user_data = {
                "name": user_name,
                "face_embeddings": face_embeddings,
                "voice_embeddings": voice_embeddings,
                "age": age,
                "relation": relation,
                "avg_face_confidence": avg_face_confidence,
                "avg_voice_quality": avg_voice_quality,
                "enrollment_timestamp": datetime.now().isoformat(),
                "enrolled_speaker": True,  # Marked for speaker verification
                "speaker_quality": avg_voice_quality
            }
            
            try:
                response = await self.central_server_client.register_user(user_data)
                user_id = response.get("user_id")
                if not user_id:
                    raise ValueError("Central server response missing user_id")
                logger.info(f"User registered in Central Server: user_id={user_id}")
            except Exception as e:
                logger.error(f"Central Server registration failed: {e}")
                raise HTTPException(status_code=503, detail=f"User registration failed: {str(e)}")
            
            # ================================================================
            # STEP 7: STORE LOCALLY
            # ================================================================
            progress.update_stage("storing_data", "Storing enrollment data locally...")
            
            try:
                enrollment_record = {
                    "user_id": user_id,
                    "user_name": user_name,
                    "enrollment_timestamp": datetime.now().isoformat(),
                    "age": age,
                    "relation": relation,
                    "face_samples": len(photo_paths),
                    "voice_samples": len(voice_paths),
                    "avg_face_confidence": avg_face_confidence,
                    "avg_voice_quality": avg_voice_quality,
                    "speaker_enrolled": True,
                    "central_server_registered": True
                }
                
                self.storage.save_enrollment(user_id, enrollment_record)
                logger.info(f"Enrollment data stored locally: {user_id}")
            except Exception as e:
                logger.error(f"Local storage failed: {e}")
                raise HTTPException(status_code=500, detail=f"Local storage failed: {str(e)}")
            
            # ================================================================
            # SUCCESS
            # ================================================================
            progress.update_stage("completed", "Enrollment completed successfully")
            
            result = {
                "status": "success",
                "message": f"User {user_name} enrolled successfully",
                "user_id": user_id,
                "face_samples": len(photo_paths),
                "voice_samples": len(voice_paths),
                "face_quality": round(avg_face_confidence, 4),
                "voice_quality": round(avg_voice_quality, 4),
                "speaker_enrolled": True,
                "enrollment_timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"Enrollment complete: {result}")
            return result
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Enrollment failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Enrollment failed: {str(e)}")
    
    # ========================================================================
    # SPEAKER VERIFICATION WORKFLOW (Runtime)
    # ========================================================================
    
    async def verify_speaker_runtime(self, audio_file: str) -> Dict[str, Any]:
        """
        Runtime speaker verification workflow:
        1. Detect wake word
        2. Verify speaker from audio
        3. Return user_id if verified
        
        Args:
            audio_file: Path to captured audio
            
        Returns:
            Dict with verification result
        """
        try:
            logger.info(f"Starting runtime speaker verification: {audio_file}")
            
            # Step 1: Verify speaker
            user_id, confidence = await self.audio_client.verify_speaker(audio_file)
            
            # Get verification threshold
            speakers = await self.audio_client.list_enrolled_speakers()
            
            threshold = 0.75  # Default threshold
            is_verified = confidence >= threshold and user_id in speakers
            
            result = {
                "status": "success",
                "user_id": user_id,
                "confidence": round(confidence, 4),
                "is_verified": is_verified,
                "threshold": threshold,
                "message": f"Speaker {'verified' if is_verified else 'not recognized'}"
            }
            
            logger.info(f"Speaker verification result: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Speaker verification failed: {e}")
            return {
                "status": "error",
                "user_id": "unknown",
                "confidence": 0.0,
                "is_verified": False,
                "message": f"Verification failed: {str(e)}"
            }
    
    
    async def complete_voice_flow(
        self,
        audio_file: str,
        transcribe: bool = True
    ) -> Dict[str, Any]:
        """
        Complete voice processing flow:
        1. Wake word (already detected before calling)
        2. Speaker verification
        3. Transcription (if enabled)
        4. Send to Central Server
        
        Returns:
            Dict with complete processing result
        """
        try:
            logger.info(f"Starting complete voice flow: {audio_file}")
            
            # Step 1: Speaker verification
            verify_result = await self.verify_speaker_runtime(audio_file)
            
            if not verify_result.get("is_verified"):
                logger.warning(f"Speaker not verified: {verify_result}")
                return {
                    "status": "error",
                    "message": "Speaker not recognized. Please try again.",
                    "verified": False
                }
            
            user_id = verify_result.get("user_id")
            
            # Step 2: Transcription (if enabled)
            transcript = None
            if transcribe:
                try:
                    transcription_result = await self.audio_client.transcribe_audio(
                        audio_file=audio_file,
                        language="en"
                    )
                    transcript = transcription_result.get("text", "")
                    logger.info(f"Transcription: {transcript[:50]}...")
                except Exception as e:
                    logger.warning(f"Transcription failed: {e}")
                    transcript = None
            
            # Note: Logging to central server can be added later if needed
            # Currently there's no log_voice_event endpoint available
            
            result = {
                "status": "success",
                "user_id": user_id,
                "verified": True,
                "transcript": transcript,
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"Voice flow complete: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Voice flow failed: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"Voice processing failed: {str(e)}",
                "verified": False
            }
    
    # ========================================================================
    # HELPER METHODS
    # ========================================================================
    
    def get_storage_stats(self) -> Dict:
        """Get storage statistics"""
        return self.storage.get_storage_stats()
    
    
    def list_all_enrollments(self) -> List[str]:
        """List all enrolled user IDs"""
        return self.storage.list_enrollments()
