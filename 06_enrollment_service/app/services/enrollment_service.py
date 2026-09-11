import os
from shared.security import internal_service_headers
import asyncio
import httpx
from datetime import datetime
from typing import Dict, Optional, List, Tuple
from fastapi import UploadFile, HTTPException
from ..utils.storage_adapter import StorageAdapter
from app.utils.file_handler import save_uploaded_file, ALLOWED_IMAGE_TYPES, ALLOWED_AUDIO_TYPES
from app.clients.vision_client import VisionClient
from app.clients.audio_client import AudioClient
from app.clients.central_server_client import CentralServerClient
from app.utils.storage_adapter import get_storage_adapter
from app.utils.progress_tracker import EnrollmentProgress
from app.utils.validators import EnrollmentValidator, ValidationError, ErrorFormatter
from config.settings import settings


class EnrollmentService:
    def __init__(self, upload_dir: str, max_photo_size: int, max_voice_size: int) -> None:
        self.upload_dir: str = upload_dir
        self.max_photo_size: int = max_photo_size
        self.max_voice_size: int = max_voice_size
        
        # Initialize service clients
        self.vision_client = VisionClient()
        self.audio_client = AudioClient()
        self.central_server_client = CentralServerClient()
        
        # Initialize async storage adapter
        storage_dir: str = os.getenv("ENROLLMENT_DATA_DIR", "./enrollment_data")
        enable_encryption: bool = os.getenv("ENABLE_ENCRYPTION", "true").lower() == "true"
        self.storage: StorageAdapter = get_storage_adapter(storage_dir, enable_encryption, use_async=True)
    
    async def check_dependencies(self) -> Dict[str, bool]:
        """Check if all required services are available"""
        return {
            "vision_service": await self.vision_client.check_health(),
            "audio_service": await self.audio_client.check_health(),
            "central_server": await self.central_server_client.check_health()
        }
    
    async def process_enrollment(
        self, 
        user_name: str,
        photos: List[UploadFile],
        voice_samples: List[UploadFile],
        age: Optional[int] = None,
        relation: Optional[str] = None
    ) -> Dict:
        """
        Complete enrollment workflow with comprehensive validation and error handling
        """
        photo_paths = []
        voice_paths = []
        
        # Initialize progress tracker
        progress = EnrollmentProgress(user_name)
        
        try:
            # Stage 1: Validate inputs
            progress.update_stage('validating')
            print(f"[Enrollment] Starting enrollment for: {user_name}")
            
            # Validate username
            try:
                validated_username: str = EnrollmentValidator.validate_username(user_name)
                print(f"[Enrollment] [OK] Username validated")
            except ValidationError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)
            
            # Validate optional metadata
            try:
                metadata: Dict[str, os.Any] = EnrollmentValidator.validate_optional_metadata(age, relation)
                print(f"[Enrollment] [OK] Metadata validated")
            except ValidationError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)
            
            # Validate file counts
            try:
                EnrollmentValidator.validate_file_count(photos, voice_samples)
                print(f"[Enrollment] [OK] File count validation passed: 5 photos, 5 voice samples")
            except ValidationError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)
            
            # Validate individual photo files
            try:
                await EnrollmentValidator.validate_all_photos(photos)
                print(f"[Enrollment] [OK] All 5 photos validated")
            except ValidationError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)
            
            # Validate individual audio files
            try:
                await EnrollmentValidator.validate_all_audio(voice_samples)
                print(f"[Enrollment] [OK] All 5 audio files validated")
            except ValidationError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)
            
            # Stage 2: Saving all files
            progress.update_stage('saving_files')
            print(f"[Enrollment] Saving files (5 photos + 5 audio)...")
            
            # Save all photos
            for i, photo in enumerate(photos):
                try:
                    photo_path: str = await save_uploaded_file(
                        photo, 
                        self.upload_dir, 
                        ALLOWED_IMAGE_TYPES,
                        self.max_photo_size
                    )
                    photo_paths.append(photo_path)
                    print(f"[Enrollment]   [OK] Photo {i+1}/5 saved: {photo_path}")
                except Exception as e:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Photo {i+1} validation failed: {str(e)}"
                    )
            
            # Save all voice samples
            for i, voice in enumerate(voice_samples):
                try:
                    voice_path: str = await save_uploaded_file(
                        voice,
                        self.upload_dir,
                        ALLOWED_AUDIO_TYPES,
                        self.max_voice_size
                    )
                    voice_paths.append(voice_path)
                    print(f"[Enrollment]   [OK] Audio {i+1}/5 saved: {voice_path}")
                except Exception as e:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Audio sample {i+1} validation failed: {str(e)}"
                    )
            
            print(f"[Enrollment] [OK] All files saved successfully")
            
            # Stage 4: Processing all faces
            progress.update_stage('processing_face')
            print(f"[Enrollment] Processing face embeddings from 5 photos...")
            face_embeddings = []
            face_confidences = []
            
            for i, photo_path in enumerate(photo_paths):
                try:
                    face_data = await self.vision_client.get_face_embedding(photo_path)
                    face_embeddings.append(face_data["embedding"])
                    face_confidences.append(face_data["confidence"])
                    print(f"[Enrollment]   [OK] Photo {i+1}/5 processed (confidence: {face_data['confidence']:.3f})")
                except Exception as e:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Failed to process photo {i+1}: {str(e)}"
                    )
            
            avg_face_confidence: float = sum(face_confidences) / len(face_confidences)
            print(f"[Enrollment] [OK] Face embeddings completed (avg confidence: {avg_face_confidence:.3f})")
            
            # Stage 5: Processing all voice samples
            progress.update_stage('processing_voice')
            print(f"[Enrollment] Processing voice embeddings from 5 samples...")
            voice_embeddings = []
            voice_qualities = []
            
            for i, voice_path in enumerate(voice_paths):
                try:
                    voice_data = await self.audio_client.get_voice_embedding(voice_path)
                    voice_embeddings.append(voice_data["embedding"])
                    voice_qualities.append(voice_data["quality_score"])
                    print(f"[Enrollment]   [OK] Audio {i+1}/5 processed (quality: {voice_data['quality_score']:.3f})")
                except Exception as e:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Failed to process audio {i+1}: {str(e)}"
                    )
            
            avg_voice_quality: float = sum(voice_qualities) / len(voice_qualities)
            print(f"[Enrollment] [OK] Voice embeddings completed (avg quality: {avg_voice_quality:.3f})")
            
            # Stage 6: Registering with Central Server
            progress.update_stage('registering')
            user_data = {
                "user_name": user_name,
                "name": user_name,
                "face_embeddings": face_embeddings,      # Array of 5 embeddings
                "voice_embeddings": voice_embeddings,    # Array of 5 embeddings
                "age": age,
                "relation": relation,
                "avg_face_confidence": round(avg_face_confidence, 3),
                "avg_voice_quality": round(avg_voice_quality, 3),
                "sample_count": {
                    "images": len(face_embeddings),
                    "audio": len(voice_embeddings)
                },
                "enrollment_timestamp": datetime.utcnow().isoformat()
            }
            
            print(f"[Enrollment] Registering user with Central Server...")
            registration_result = await self.central_server_client.register_user(user_data)
            user_id = registration_result["user_id"]
            print(f"[Enrollment] [OK] User registered: {user_id}")
            
            # Stage 7: Storing data securely
            progress.update_stage('storing_data')
            print(f"[Enrollment] Storing enrollment data securely...")
            
            # Prepare comprehensive enrollment record
            enrollment_record = {
                "user_id": user_id,
                "user_name": user_name,
                "face_embeddings": face_embeddings,
                "voice_embeddings": voice_embeddings,
                "age": age,
                "relation": relation,
                "avg_face_confidence": avg_face_confidence,
                "avg_voice_quality": avg_voice_quality,
                "sample_count": {
                    "images": len(face_embeddings),
                    "audio": len(voice_embeddings)
                },
                "individual_scores": {
                    "face_confidences": face_confidences,
                    "voice_qualities": voice_qualities
                },
                "enrollment_timestamp": user_data["enrollment_timestamp"],
                "registration_status": registration_result["status"]
            }
            
            # Save to secure storage (async, non-blocking)
            await self.storage.save_enrollment_smart(user_id, enrollment_record)
            print(f"[Enrollment] [OK] Enrollment data stored securely")
            
            # Stage 8: Cleanup
            progress.update_stage('cleanup')
            self._cleanup_files(photo_paths + voice_paths)
            
            # Stage 9: Completed
            progress.update_stage('completed')
            print(f"[Enrollment] [OK] ENROLLMENT COMPLETED SUCCESSFULLY")
            from shared.jwt_manager import get_jwt_manager
            token_result = get_jwt_manager().create_session_token(user_id)
            
            return {
                "status": "success",
                "message": f"User '{user_name}' enrolled successfully with 5 images and 5 voice samples",
                "user_id": user_id,
                "access_token": token_result["token"],
                "token_type": token_result["type"],
                "expires_in": token_result["expires_in"],
                "details": {
                    "avg_face_confidence": round(avg_face_confidence, 3),
                    "avg_voice_quality": round(avg_voice_quality, 3),
                    "sample_count": {
                        "images": 5,
                        "audio": 5
                    },
                    "enrollment_timestamp": user_data["enrollment_timestamp"],
                    "stored_securely": True,
                    "encryption_enabled": self.storage.enable_encryption
                }
            }
            
        except HTTPException:
            progress.set_error("Enrollment failed")
            self._cleanup_files(photo_paths + voice_paths)
            raise
            
        except Exception as e:
            progress.set_error("Enrollment failed")
            self._cleanup_files(photo_paths + voice_paths)
            print(f"[Enrollment]  ERROR: {type(e).__name__}: {str(e)}")
            # Don't expose internal error details to client
            raise HTTPException(
                status_code=500,
                detail="Enrollment failed. Please try again or contact support."
            )
    
    
    async def improve_training(
        self,
        user_id: str,
        additional_photos: List[UploadFile],
        additional_voice_samples: List[UploadFile]
    ) -> Dict:
        """
        Add more samples to existing user (OLD samples are KEPT)
        """
        photo_paths = []
        voice_paths = []
        
        try:
            # The route and storage contract both use the durable user_id.
            if not user_id or not isinstance(user_id, str):
                raise HTTPException(status_code=400, detail="Invalid user_id")
            
            # Validate file counts
            try:
                EnrollmentValidator.validate_file_count(additional_photos, additional_voice_samples)
            except ValidationError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)
            
            # Validate individual files
            try:
                await EnrollmentValidator.validate_all_photos(additional_photos)
                await EnrollmentValidator.validate_all_audio(additional_voice_samples)
            except ValidationError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)
            
            print(f"[ImproveTraining] Adding training data for user {user_id}...")
            
            actual_user_id = user_id
            existing_data = await self.storage.get_enrollment_smart(actual_user_id)
            if not existing_data:
                raise HTTPException(
                    status_code=404,
                    detail=f"User ID '{user_id}' not found in enrollment records"
                )
            
            # Save new files
            for i, photo in enumerate(additional_photos):
                photo_path: str = await save_uploaded_file(
                    photo, self.upload_dir, ALLOWED_IMAGE_TYPES, self.max_photo_size
                )
                photo_paths.append(photo_path)
                print(f"[ImproveTraining]   [OK] Photo {i+1}/5 saved")
            
            for i, voice in enumerate(additional_voice_samples):
                voice_path: str = await save_uploaded_file(
                    voice, self.upload_dir, ALLOWED_AUDIO_TYPES, self.max_voice_size
                )
                voice_paths.append(voice_path)
                print(f"[ImproveTraining]   [OK] Audio {i+1}/5 saved")
            
            # Process new files
            new_face_embeddings = []
            new_face_confidences = []
            for i, photo_path in enumerate(photo_paths):
                face_data = await self.vision_client.get_face_embedding(photo_path)
                new_face_embeddings.append(face_data["embedding"])
                new_face_confidences.append(face_data["confidence"])
                print(f"[ImproveTraining]   [OK] Photo {i+1}/5 processed")
            
            new_voice_embeddings = []
            new_voice_qualities = []
            for i, voice_path in enumerate(voice_paths):
                voice_data = await self.audio_client.get_voice_embedding(voice_path)
                new_voice_embeddings.append(voice_data["embedding"])
                new_voice_qualities.append(voice_data["quality_score"])
                print(f"[ImproveTraining]   [OK] Audio {i+1}/5 processed")
            
            # Update local storage with new sample counts
            existing_data["sample_count"]["images"] += 5
            existing_data["sample_count"]["audio"] += 5
            existing_data["last_improved"] = datetime.utcnow().isoformat()
            
            # Save to local storage first (async)
            await self.storage.save_enrollment_smart(actual_user_id, existing_data)
            print(f"[ImproveTraining] [OK] Local storage updated")
            
            # Update Central Server with new embeddings
            try:
                print(f"[ImproveTraining] Updating Central Server with new embeddings...")
                await self.central_server_client.append_user_embeddings(
                    user_id=actual_user_id,
                    face_embeddings=new_face_embeddings,
                    voice_embeddings=new_voice_embeddings,
                    face_confidences=new_face_confidences,
                    voice_qualities=new_voice_qualities
                )
                print(f"[ImproveTraining] [OK] Central Server updated successfully")
            except Exception as cs_error:
                print(f"[ImproveTraining]  ERROR: Failed to update Central Server: {str(cs_error)}")
                # Rollback local storage changes since Central Server update failed
                print(f"[ImproveTraining] Rolling back local storage changes...")
                self.storage.save_enrollment(actual_user_id, {
                    **existing_data,
                    "sample_count": {
                        "images": existing_data["sample_count"]["images"] - 5,
                        "audio": existing_data["sample_count"]["audio"] - 5
                    }
                })
                self._cleanup_files(photo_paths + voice_paths)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to update Central Server with new embeddings: {str(cs_error)}"
                )
            
            self._cleanup_files(photo_paths + voice_paths)
            
            print(f"[ImproveTraining] [OK] Training improved for user {user_id}")
            
            return {
                "status": "success",
                "message": f"Training improved for user {user_id}",
                "user_id": user_id,
                "total_samples": {
                    "images": existing_data["sample_count"]["images"],
                    "audio": existing_data["sample_count"]["audio"]
                }
            }
            
        except HTTPException:
            self._cleanup_files(photo_paths + voice_paths)
            raise
        except Exception as e:
            self._cleanup_files(photo_paths + voice_paths)
            error_msg: str = str(e) if str(e) else f"{type(e).__name__}: Unknown error"
            print(f"[ImproveTraining]  ERROR: {error_msg}")
            import traceback
            print(f"[ImproveTraining] Traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Improve training failed: {error_msg}")
    
    async def update_model(
        self,
        user_id: str,
        new_photos: List[UploadFile],
        new_voice_samples: List[UploadFile]
    ) -> Dict:
        """
        Replace all old samples with new ones (RE-ENROLLMENT)
        """
        photo_paths = []
        voice_paths = []
        
        try:
            # The route and storage contract both use the durable user_id.
            if not user_id or not isinstance(user_id, str):
                raise HTTPException(status_code=400, detail="Invalid user_id")
            
            # Validate file counts
            try:
                EnrollmentValidator.validate_file_count(new_photos, new_voice_samples)
            except ValidationError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)
            
            # Validate individual files
            try:
                await EnrollmentValidator.validate_all_photos(new_photos)
                await EnrollmentValidator.validate_all_audio(new_voice_samples)
            except ValidationError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)
            
            print(f"[ReEnrollment] RE-ENROLLING user {user_id}...")
            
            actual_user_id = user_id
            existing_data = await self.storage.get_enrollment_smart(actual_user_id)
            if not existing_data:
                raise HTTPException(
                    status_code=404,
                    detail=f"User ID '{user_id}' not found in enrollment records"
                )
            
            # Save new files
            for i, photo in enumerate(new_photos):
                photo_path: str = await save_uploaded_file(
                    photo, self.upload_dir, ALLOWED_IMAGE_TYPES, self.max_photo_size
                )
                photo_paths.append(photo_path)
                print(f"[ReEnrollment]   [OK] Photo {i+1}/5 saved")
            
            for i, voice in enumerate(new_voice_samples):
                voice_path: str = await save_uploaded_file(
                    voice, self.upload_dir, ALLOWED_AUDIO_TYPES, self.max_voice_size
                )
                voice_paths.append(voice_path)
                print(f"[ReEnrollment]   [OK] Audio {i+1}/5 saved")
            
            # Process new files
            new_face_embeddings = []
            new_face_confidences = []
            for i, photo_path in enumerate(photo_paths):
                face_data = await self.vision_client.get_face_embedding(photo_path)
                new_face_embeddings.append(face_data["embedding"])
                new_face_confidences.append(face_data["confidence"])
                print(f"[ReEnrollment]   [OK] Photo {i+1}/5 processed")
            
            new_voice_embeddings = []
            new_voice_qualities = []
            for i, voice_path in enumerate(voice_paths):
                voice_data = await self.audio_client.get_voice_embedding(voice_path)
                new_voice_embeddings.append(voice_data["embedding"])
                new_voice_qualities.append(voice_data["quality_score"])
                print(f"[ReEnrollment]   [OK] Audio {i+1}/5 processed")
            
            # REPLACE ALL samples (reset to 5 and 5)
            avg_face_confidence: float = sum(new_face_confidences) / len(new_face_confidences)
            avg_voice_quality: float = sum(new_voice_qualities) / len(new_voice_qualities)
            
            existing_data["sample_count"] = {"images": 5, "audio": 5}
            existing_data["avg_face_confidence"] = round(avg_face_confidence, 3)
            existing_data["avg_voice_quality"] = round(avg_voice_quality, 3)
            existing_data["individual_scores"] = {
                "face_confidences": new_face_confidences,
                "voice_qualities": new_voice_qualities
            }
            existing_data["last_re_enrolled"] = datetime.utcnow().isoformat()
            
            # Save to local storage first (async)
            await self.storage.save_enrollment_smart(actual_user_id, existing_data)
            print(f"[ReEnrollment] [OK] Local storage updated")
            
            # Update Central Server with new embeddings (replace all)
            try:
                print(f"[ReEnrollment] Updating Central Server with new embeddings...")
                await self.central_server_client.update_user_embeddings(
                    user_id=actual_user_id,
                    face_embeddings=new_face_embeddings,
                    voice_embeddings=new_voice_embeddings,
                    avg_face_confidence=avg_face_confidence,
                    avg_voice_quality=avg_voice_quality,
                    face_confidences=new_face_confidences,
                    voice_qualities=new_voice_qualities
                )
                print(f"[ReEnrollment] [OK] Central Server updated successfully")
            except Exception as cs_error:
                print(f"[ReEnrollment]  ERROR: Failed to update Central Server: {str(cs_error)}")
                # Rollback local storage - restore to old state
                print(f"[ReEnrollment] Rolling back local storage changes...")
                # We saved the new data, so we need to revert but we don't have the old state here
                # So we'll clear it and let user re-enroll
                self.storage.delete_enrollment(actual_user_id)
                self._cleanup_files(photo_paths + voice_paths)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to update Central Server with new embeddings: {str(cs_error)}"
                )
            
            self._cleanup_files(photo_paths + voice_paths)
            
            print(f"[ReEnrollment] [OK] Re-enrollment completed for user {user_id}")
            
            return {
                "status": "success",
                "message": f"Model updated for user {user_id}",
                "user_id": user_id,
                "total_samples": {
                    "images": 5,
                    "audio": 5
                }
            }
            
        except HTTPException:
            self._cleanup_files(photo_paths + voice_paths)
            raise
        except Exception as e:
            self._cleanup_files(photo_paths + voice_paths)
            print(f"[ReEnrollment]  ERROR: {type(e).__name__}: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Re-enrollment failed. Please try again or contact support."
            )
    
    async def get_enrollment_data(self, user_id: str) -> Optional[Dict]:
        """Retrieve enrollment data from secure storage (async)"""
        return await self.storage.get_enrollment_smart(user_id)
    
    async def delete_enrollment_data(self, user_id: str) -> bool:
        """Delete enrollment data from secure storage (async)"""
        return await self.storage.delete_enrollment_smart(user_id)
    
    async def get_storage_stats(self) -> Dict:
        """Get storage statistics (async)"""
        return await self.storage.get_storage_stats_async()
    
    async def list_all_enrollments(self) -> list:
        """List all enrolled user IDs (async)"""
        return await self.storage.get_all_users_async()

    async def sync_local_enrollments_to_central(self) -> Dict:
        """Sync local enrollment records into Central Server if missing."""
        user_ids = await self.storage.get_all_users_async()
        if not user_ids:
            return {"total": 0, "synced": 0, "skipped": 0, "errors": 0}

        results = {"total": len(user_ids), "synced": 0, "skipped": 0, "errors": 0, "error_details": []}
        base_url: str = settings.central_server_url.rstrip("/")

        async with httpx.AsyncClient(timeout=20.0, headers=internal_service_headers()) as client:
            for user_id in user_ids:
                try:
                    enrollment_data = await self.storage.get_enrollment_smart(user_id)
                    if not enrollment_data:
                        results["skipped"] += 1
                        continue

                    for field in ("face_embeddings", "voice_embeddings"):
                        vectors = enrollment_data.get(field)
                        if not isinstance(vectors, list) or not vectors:
                            raise ValueError(
                                f"Local enrollment {user_id}: missing or invalid {field}; "
                                "restore embeddings from a verified backup or re-enroll. "
                                "Record preserved; recovery rejected."
                            )

                    name = enrollment_data.get("user_name") or enrollment_data.get("name")
                    if not name:
                        results["skipped"] += 1
                        continue

                    check_resp: httpx.Response = await client.get(
                        f"{base_url}/users/check",
                        params={"name": name}
                    )
                    if check_resp.status_code == 200 and check_resp.json().get("exists"):
                        results["skipped"] += 1
                        continue

                    payload = {
                        "name": name,
                        "user_name": name,
                        "user_id": enrollment_data.get("user_id"),
                        "face_embeddings": enrollment_data.get("face_embeddings", []),
                        "voice_embeddings": enrollment_data.get("voice_embeddings", []),
                        "age": enrollment_data.get("age"),
                        "relation": enrollment_data.get("relation"),
                        "avg_face_confidence": enrollment_data.get("avg_face_confidence"),
                        "avg_voice_quality": enrollment_data.get("avg_voice_quality"),
                        "enrollment_timestamp": enrollment_data.get("enrollment_timestamp"),
                    }

                    add_resp: httpx.Response = await client.post(f"{base_url}/users", json=payload)
                    if add_resp.status_code == 200:
                        results["synced"] += 1
                    else:
                        results["errors"] += 1
                except Exception as exc:
                    results["errors"] += 1
                    results["error_details"].append({"user_id": user_id, "error": str(exc)})

        return results
    
    async def find_enrollment_by_user_name(self, user_name: str) -> Optional[Tuple[str, Dict]]:
        """
        Find enrollment by user name from Central Server (ASYNC)
        Returns: (user_id, enrollment_record) or (None, None) if not found
        
        The user_id passed from Streamlit UI is actually the user_name (e.g., "sohail").
        We query Central Server to find the full user record.
        """
        if not user_name:
            print(f"[FindUser] User name is empty or None")
            return None, None
        
        user_name = user_name.strip()
        print(f"[FindUser] Looking for user: '{user_name}'")
        
        try:
            # Use asynchronous httpx client to query Central Server
            import httpx
            from config.settings import settings
            async with httpx.AsyncClient(timeout=10.0, headers=internal_service_headers()) as client:
                try:
                    url: str = f"{settings.central_server_url}/users/check"
                    response: httpx.Response = await client.get(
                        url,
                        params={"name": user_name}
                    )
                    if response.status_code == 200:
                        user_data = response.json()
                        if user_data:
                            print(f"[FindUser] Found user in Central Server")
                            # Convert Central Server format to enrollment format
                            enrollment_record: Dict[str, os.Any] = {
                                "user_id": user_data.get("user_id", user_name),
                                "user_name": user_data.get("name") or user_data.get("user_name", user_name),
                                "sample_count": user_data.get("sample_count", {"images": 5, "audio": 5}),
                                "age": user_data.get("age"),
                                "relation": user_data.get("relation"),
                                "avg_face_confidence": user_data.get("avg_face_confidence", 0.0),
                                "avg_voice_quality": user_data.get("avg_voice_quality", 0.0),
                                "enrollment_timestamp": user_data.get("enrollment_timestamp"),
                            }
                            user_id = user_data.get("user_id", user_name)
                            print(f"[FindUser]  FOUND user {user_id}")
                            return user_id, enrollment_record
                except Exception as e:
                    print(f"[FindUser] Error querying Central Server: {type(e).__name__}: {str(e)}")
            
            print(f"[FindUser]  User '{user_name}' not found in Central Server")
            return None, None
            
        except Exception as e:
            print(f"[FindUser]  ERROR: {type(e).__name__}: {str(e)}")
            import traceback
            print(f"[FindUser] Traceback: {traceback.format_exc()}")
            return None, None
    
    async def delete_user_from_all(self, user_name: str) -> Dict:
        """Delete user from both Central Server and local storage"""
        try:
            print(f"[DeleteUser] Starting synchronized deletion for user: {user_name}")
            
            # Step 1: Find user in Central Server to get user_id
            actual_user_id, existing_data = await self.find_enrollment_by_user_name(user_name)
            if not actual_user_id:
                raise HTTPException(
                    status_code=404,
                    detail=f"User '{user_name}' not found in enrollment records"
                )
            
            print(f"[DeleteUser] Found user_id: {actual_user_id}")
            
            # Step 2: Delete from Central Server
            try:
                import httpx
                async with httpx.AsyncClient(
                    timeout=10.0, headers=internal_service_headers(actual_user_id)
                ) as client:
                    response: httpx.Response = await client.delete(f"{settings.central_server_url}/users/{actual_user_id}")
                    if response.status_code != 200:
                        raise HTTPException(
                            status_code=response.status_code,
                            detail=f"Failed to delete from Central Server: {response.text}"
                        )
                    print(f"[DeleteUser]  Deleted from Central Server")
            except Exception as e:
                print(f"[DeleteUser]  Error deleting from Central Server: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Failed to delete from Central Server: {str(e)}")
            
            # Step 3: Delete from local storage (async)
            try:
                await self.storage.delete_enrollment_smart(actual_user_id)
                print(f"[DeleteUser]  Deleted from local storage")
            except Exception as e:
                print(f"[DeleteUser]  Error deleting from local storage: {str(e)}")
                # Don't fail here - user is already deleted from Central Server
                # Log the error but continue
            
            print(f"[DeleteUser]  Successfully deleted user {user_name}")
            
            return {
                "status": "deleted",
                "message": f"User '{user_name}' deleted from all systems",
                "user_id": actual_user_id,
                "user_name": user_name
            }
        
        except HTTPException:
            raise
        except Exception as e:
            print(f"[DeleteUser]  ERROR: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to delete user: {str(e)}")
    
    def _cleanup_files(self, file_paths: list) -> None:
        """Delete temporary files"""
        for path in file_paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    print(f"[Enrollment] Cleaned up: {path}")
                except Exception as e:
                    print(f"[Enrollment] Failed to cleanup {path}: {str(e)}")

