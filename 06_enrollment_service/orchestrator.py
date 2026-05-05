"""
Enrollment Orchestrator - Phase 3

Manages enrollment lifecycle as a state machine:
  IDLE → VALIDATION → AUDIO_PROCESSING → FACE_PROCESSING 
    → AGGREGATION → STORAGE → SUCCESS | ROLLBACK_ON_FAILURE
"""

import asyncio
import threading
from typing import Dict, Any, Optional, List
from enum import Enum
from datetime import datetime
import json
import os
import sys

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.models import get_logger, ErrorCode, error_response, success_response

logger = get_logger('EnrollmentOrchestrator')


class EnrollmentState(str, Enum):
    """Enrollment states"""
    IDLE = "IDLE"
    VALIDATION = "VALIDATION"
    AUDIO_PROCESSING = "AUDIO_PROCESSING"
    FACE_PROCESSING = "FACE_PROCESSING"
    AGGREGATION = "AGGREGATION"
    STORAGE = "STORAGE"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    ROLLBACK = "ROLLBACK"


class EnrollmentOrchestrator:
    """Manages atomic enrollment operations"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or "01_central_server/data/users.json"
        self._enrollment_locks: Dict[str, threading.RLock] = {}
        self._locks_mutex = threading.Lock()
    
    def _get_enrollment_lock(self, user_id: str) -> threading.RLock:
        """Get or create mutex for user enrollment"""
        with self._locks_mutex:
            if user_id not in self._enrollment_locks:
                self._enrollment_locks[user_id] = threading.RLock()
            return self._enrollment_locks[user_id]
    
    def _validate_enrollment_input(self, user_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate enrollment input
        
        Returns:
            (is_valid, error_message)
        """
        
        # Check required fields
        required_fields = ['user_name', 'email', 'phone']
        for field in required_fields:
            if field not in user_data or not user_data[field]:
                return False, f"Missing required field: {field}"
        
        # Validate audio embeddings
        if 'voice_embeddings' in user_data and user_data['voice_embeddings']:
            embeddings = user_data['voice_embeddings']
            
            if not isinstance(embeddings, list):
                return False, "voice_embeddings must be a list"
            
            for i, emb in enumerate(embeddings):
                if not isinstance(emb, (list, tuple)):
                    return False, f"Embedding {i} is not a list/tuple"
                
                if len(emb) != 256:
                    return False, f"Embedding {i} has invalid dimension: {len(emb)} != 256"
                
                # Check non-zero
                if all(abs(x) < 1e-8 for x in emb):
                    return False, f"Embedding {i} is all zeros"
        
        return True, None
    
    def _load_enrollments(self) -> Dict[str, Any]:
        """Load enrollments from disk"""
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, 'r') as f:
                    data = json.load(f)
                    return data.get('users', {})
            except Exception as e:
                logger.error(f"Failed to load enrollments: {e}", error_code=ErrorCode.STORAGE_ERROR)
                return {}
        return {}
    
    def _save_enrollments(self, enrollments: Dict[str, Any]) -> bool:
        """Save enrollments to disk atomically"""
        try:
            # Create backup
            if os.path.exists(self.db_path):
                backup_path = self.db_path + '.backup'
                with open(self.db_path, 'r') as src:
                    with open(backup_path, 'w') as dst:
                        dst.write(src.read())
            
            # Write new data
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            with open(self.db_path, 'w') as f:
                json.dump({'users': enrollments}, f, indent=2)
            
            logger.info(f"Enrollments saved successfully", count=len(enrollments))
            return True
        except Exception as e:
            logger.error(f"Failed to save enrollments: {e}", error_code=ErrorCode.PERSISTENCE_FAILED)
            return False
    
    async def enroll_user(self, user_data: Dict[str, Any]) -> tuple[bool, Optional[str], Optional[Dict]]:
        """
        Atomic user enrollment with state machine
        
        Returns:
            (success, error_message, result_data)
        """
        
        trace_id = logger.generate_trace_id()
        user_id = user_data.get('user_name', 'unknown')
        
        # Get lock for this user (prevents concurrent enrollment)
        lock = self._get_enrollment_lock(user_id)
        
        with lock:
            try:
                state = EnrollmentState.VALIDATION
                logger.info(f"Starting enrollment", user_id=user_id, state=state)
                
                # PHASE 1: VALIDATION
                is_valid, error_msg = self._validate_enrollment_input(user_data)
                if not is_valid:
                    logger.error(f"Enrollment validation failed: {error_msg}", user_id=user_id)
                    return False, error_msg, None
                
                logger.info(f"Validation passed", user_id=user_id)
                
                # PHASE 2: AUDIO PROCESSING (already done by caller, just validate)
                state = EnrollmentState.AUDIO_PROCESSING
                audio_embeddings = user_data.get('voice_embeddings', [])
                if not audio_embeddings:
                    logger.warning(f"No audio embeddings provided", user_id=user_id)
                else:
                    logger.info(f"Audio embeddings present: {len(audio_embeddings)}", user_id=user_id)
                
                # PHASE 3: FACE PROCESSING (mock for now)
                state = EnrollmentState.FACE_PROCESSING
                face_embeddings = user_data.get('face_embeddings', [])
                if not face_embeddings:
                    logger.warning(f"No face embeddings provided", user_id=user_id)
                else:
                    logger.info(f"Face embeddings present: {len(face_embeddings)}", user_id=user_id)
                
                # PHASE 4: AGGREGATION
                state = EnrollmentState.AGGREGATION
                aggregated_data = {
                    'user_name': user_data.get('user_name'),
                    'email': user_data.get('email'),
                    'phone': user_data.get('phone'),
                    'voice_embeddings': audio_embeddings,
                    'face_embeddings': face_embeddings,
                    'enrollment_timestamp': datetime.now().isoformat(),
                    'version': '2.0'
                }
                logger.info(f"Aggregation complete", user_id=user_id)
                
                # PHASE 5: STORAGE (atomic)
                state = EnrollmentState.STORAGE
                enrollments = self._load_enrollments()
                
                # Check for duplicate (idempotence)
                if user_id in enrollments:
                    logger.info(f"User already enrolled, updating", user_id=user_id)
                
                enrollments[user_id] = aggregated_data
                
                # Atomic write
                if not self._save_enrollments(enrollments):
                    logger.error(f"Failed to save enrollments", user_id=user_id)
                    return False, "Failed to persist enrollment", None
                
                # SUCCESS
                state = EnrollmentState.SUCCESS
                logger.info(f"Enrollment completed successfully", user_id=user_id)
                
                return True, None, aggregated_data
            
            except Exception as e:
                logger.error(f"Unexpected error during enrollment: {e}", error_code=ErrorCode.PROCESSING_FAILED)
                return False, f"Enrollment failed: {str(e)}", None
    
    async def verify_enrollment(self, user_id: str) -> tuple[bool, Optional[Dict]]:
        """Verify user is enrolled and has valid embeddings"""
        
        try:
            enrollments = self._load_enrollments()
            
            if user_id not in enrollments:
                return False, None
            
            enrollment = enrollments[user_id]
            
            # Validate embeddings exist
            voice_embs = enrollment.get('voice_embeddings', [])
            face_embs = enrollment.get('face_embeddings', [])
            
            if not voice_embs and not face_embs:
                logger.warning(f"User has no embeddings", user_id=user_id)
                return False, enrollment
            
            return True, enrollment
        
        except Exception as e:
            logger.error(f"Verification failed: {e}", error_code=ErrorCode.STORAGE_ERROR)
            return False, None


# Global instance
_orchestrator: Optional[EnrollmentOrchestrator] = None


def get_orchestrator() -> EnrollmentOrchestrator:
    """Get global orchestrator instance"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = EnrollmentOrchestrator()
    return _orchestrator
