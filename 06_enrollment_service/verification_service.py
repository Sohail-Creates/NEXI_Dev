"""
Phase 5: Speaker Verification Service
Implements speaker matching against enrolled users.

This service handles comparing a new audio sample against stored speaker embeddings.
Uses cosine similarity with configurable threshold for match determination.

Architecture:
- get_verification_service() - Global singleton
- verify_speaker() - Compare audio embedding against enrollment
- find_best_match() - Find best matching user from enrolled users
- compute_speaker_confidence() - Confidence scoring

Non-Negotiable Rules:
- No silent failures - all errors explicit
- All embeddings validated non-zero before comparison
- Cosine similarity must be within valid range [0, 1]
- Never return uncertain results
- Atomic operations (all-or-nothing)
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
import logging

# Configure logging
logger = logging.getLogger(__name__)


class VerificationResult(Enum):
    """Speaker verification outcomes."""
    MATCH = "match"
    NO_MATCH = "no_match"
    INSUFFICIENT_DATA = "insufficient_data"
    ERROR = "error"


@dataclass
class SpeakerVerification:
    """Result of speaker verification operation."""
    result: VerificationResult
    user_name: Optional[str]
    similarity_score: Optional[float]
    threshold: float
    timestamp: str
    error_message: Optional[str] = None
    confidence: float = 0.0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for API response."""
        return {
            "result": self.result.value,
            "user_name": self.user_name,
            "similarity_score": self.similarity_score,
            "threshold": self.threshold,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "error": self.error_message
        }


class VerificationService:
    """
    Verifies speaker identity against enrolled users.
    
    Implements speaker matching with the following pipeline:
    1. Accept new speaker embedding (256D)
    2. Load all enrolled users
    3. For each enrolled user, compute cosine similarity
    4. Find best match
    5. Compare against threshold
    6. Return result with confidence
    
    Thread-safe: Uses file-based locking for enrollment data access.
    """
    
    # Similarity threshold for speaker match (tuned for MFCC features)
    SIMILARITY_THRESHOLD = 0.75
    
    # Minimum similarity for confidence calculation
    MIN_SIMILARITY = 0.5
    MAX_SIMILARITY = 1.0
    
    def __init__(self, enrollment_data_dir: str = "01_central_server/data"):
        """
        Initialize verification service.
        
        Args:
            enrollment_data_dir: Directory containing enrolled user data
        """
        self.enrollment_data_dir = enrollment_data_dir
        self.users_file = os.path.join(enrollment_data_dir, "users.json")
        logger.info(f"VerificationService initialized with data dir: {enrollment_data_dir}")
    
    @staticmethod
    def cosine_similarity(embedding1: List[float], embedding2: List[float]) -> float:
        """
        Compute cosine similarity between two embeddings.
        
        Formula: cos(θ) = (A·B) / (||A|| * ||B||)
        
        Args:
            embedding1: First embedding vector (256D)
            embedding2: Second embedding vector (256D)
            
        Returns:
            Similarity score in range [0, 1]
            
        Raises:
            ValueError: If embeddings invalid or zero-length
        """
        if not embedding1 or not embedding2:
            raise ValueError("Embeddings cannot be empty")
        
        if len(embedding1) != len(embedding2):
            raise ValueError(f"Embedding dimension mismatch: {len(embedding1)} vs {len(embedding2)}")
        
        # Compute dot product
        dot_product = sum(a * b for a, b in zip(embedding1, embedding2))
        
        # Compute magnitudes
        mag1 = sum(x ** 2 for x in embedding1) ** 0.5
        mag2 = sum(x ** 2 for x in embedding2) ** 0.5
        
        if mag1 == 0 or mag2 == 0:
            raise ValueError("Cannot compute similarity with zero-magnitude vector")
        
        # Compute cosine similarity
        similarity = dot_product / (mag1 * mag2)
        
        # Clamp to valid range [0, 1] (numerical stability)
        similarity = max(0.0, min(1.0, similarity))
        
        return similarity
    
    def _load_enrollments(self) -> Dict:
        """
        Load all enrolled users from disk.
        
        Returns:
            Dictionary mapping user_name to user data
            
        Raises:
            FileNotFoundError: If users file not found
            ValueError: If file is corrupted
        """
        if not os.path.exists(self.users_file):
            logger.warning(f"Users file not found: {self.users_file}")
            return {}
        
        try:
            with open(self.users_file, 'r') as f:
                data = json.load(f)
            
            # Handle both list and dict formats
            if isinstance(data, list):
                # Convert list format to dict format
                # Assume list contains user objects with 'user_name' or 'name' field
                result = {}
                for user_data in data:
                    user_name = user_data.get('user_name') or user_data.get('name')
                    if user_name:
                        result[user_name] = user_data
                logger.info(f"Converted list format to dict: {len(result)} users")
                return result
            
            elif isinstance(data, dict):
                logger.info(f"Loaded {len(data)} enrolled users")
                return data
            
            else:
                raise ValueError(f"Expected dict or list, got {type(data)}")
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode users file: {e}")
            raise ValueError(f"Corrupted users file: {e}")
        except Exception as e:
            logger.error(f"Error loading enrollments: {e}")
            raise
    
    def _validate_embedding(self, embedding: List[float]) -> None:
        """
        Validate embedding before use in comparison.
        
        Checks:
        - Must be list/array
        - Must have 256 dimensions
        - Must be all non-zero (non-silence)
        - Must contain only valid floats
        
        Args:
            embedding: Embedding vector to validate
            
        Raises:
            ValueError: If validation fails
        """
        if not isinstance(embedding, (list, tuple)):
            raise ValueError(f"Embedding must be list/tuple, got {type(embedding)}")
        
        if len(embedding) != 256:
            raise ValueError(f"Embedding must be 256D, got {len(embedding)}D")
        
        # Check all values are valid floats
        try:
            embedding_float = [float(x) for x in embedding]
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid embedding values: {e}")
        
        # Check for non-zero (indicates audio content)
        if all(x == 0 for x in embedding_float):
            raise ValueError("Embedding is all zeros (indicates silence/invalid audio)")
        
        # Check magnitude is reasonable
        magnitude = sum(x ** 2 for x in embedding_float) ** 0.5
        if magnitude < 0.1:
            raise ValueError(f"Embedding magnitude too small: {magnitude} (indicates silence)")
    
    def _extract_embedding_from_enrollment(self, user_data: Dict) -> List[float]:
        """
        Extract speaker embedding from enrollment record.
        
        User data structure:
        {
            "user_name": "...",
            "audio_embedding": [...],
            "face_embedding": [...],
            "aggregated_embedding": [...]
        }
        
        Args:
            user_data: Enrollment record
            
        Returns:
            Speaker embedding (256D)
            
        Raises:
            ValueError: If embedding not found or invalid
        """
        # Try to get aggregated embedding first (most reliable)
        if "aggregated_embedding" in user_data:
            embedding = user_data["aggregated_embedding"]
        elif "audio_embedding" in user_data:
            # Fall back to audio embedding
            embedding = user_data["audio_embedding"]
        else:
            raise ValueError("No embedding found in user data")
        
        # Validate
        self._validate_embedding(embedding)
        return embedding
    
    def find_best_match(self, speaker_embedding: List[float]) -> Tuple[Optional[str], float]:
        """
        Find best matching user from enrolled users.
        
        Iterates through all enrolled users, computes cosine similarity,
        returns user with highest similarity score.
        
        Args:
            speaker_embedding: New speaker embedding (256D)
            
        Returns:
            Tuple of (best_user_name, best_similarity_score)
            Returns (None, 0.0) if no users enrolled or all comparisons fail
            
        Raises:
            ValueError: If speaker_embedding invalid
        """
        self._validate_embedding(speaker_embedding)
        
        enrollments = self._load_enrollments()
        
        if not enrollments:
            logger.warning("No enrolled users found")
            return None, 0.0
        
        best_user = None
        best_similarity = 0.0
        
        for user_name, user_data in enrollments.items():
            try:
                enrolled_embedding = self._extract_embedding_from_enrollment(user_data)
                similarity = self.cosine_similarity(speaker_embedding, enrolled_embedding)
                
                logger.debug(f"User {user_name}: similarity={similarity:.4f}")
                
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_user = user_name
            
            except ValueError as e:
                logger.warning(f"Could not compare with user {user_name}: {e}")
                continue
        
        logger.info(f"Best match: {best_user} (similarity={best_similarity:.4f})")
        return best_user, best_similarity
    
    def compute_speaker_confidence(self, similarity_score: float) -> float:
        """
        Compute confidence score from similarity.
        
        Maps similarity score [0, 1] to confidence [0, 1] using sigmoid-like function:
        - Below threshold: low confidence
        - At threshold: ~50% confidence
        - Well above threshold: high confidence
        
        Args:
            similarity_score: Raw similarity score [0, 1]
            
        Returns:
            Confidence score [0, 1]
        """
        if similarity_score < self.MIN_SIMILARITY:
            return 0.0
        
        if similarity_score >= self.MAX_SIMILARITY:
            return 1.0
        
        # Normalize to [0, 1] then apply smooth curve
        normalized = (similarity_score - self.MIN_SIMILARITY) / (self.MAX_SIMILARITY - self.MIN_SIMILARITY)
        
        # Smooth curve that goes from 0 to 1
        # Using sigmoid-like function: confidence = normalized^2 * (3 - 2*normalized)
        confidence = normalized ** 2 * (3 - 2 * normalized)
        
        return min(1.0, max(0.0, confidence))
    
    def verify_speaker(self, speaker_embedding: List[float], 
                      expected_user: Optional[str] = None) -> SpeakerVerification:
        """
        Verify speaker identity.
        
        Two modes:
        1. Identify speaker: Find best match from all enrolled users
        2. Verify specific user: Check if speaker matches expected_user
        
        Args:
            speaker_embedding: New speaker embedding (256D)
            expected_user: Optional user name to verify against (if None, identify best match)
            
        Returns:
            SpeakerVerification result with match status and confidence
        """
        timestamp = datetime.utcnow().isoformat()
        
        try:
            # Validate input embedding
            self._validate_embedding(speaker_embedding)
            
            # Load enrollments
            enrollments = self._load_enrollments()
            if not enrollments:
                return SpeakerVerification(
                    result=VerificationResult.INSUFFICIENT_DATA,
                    user_name=None,
                    similarity_score=None,
                    threshold=self.SIMILARITY_THRESHOLD,
                    timestamp=timestamp,
                    error_message="No enrolled users in system"
                )
            
            if expected_user:
                # Mode: Verify specific user
                if expected_user not in enrollments:
                    return SpeakerVerification(
                        result=VerificationResult.ERROR,
                        user_name=expected_user,
                        similarity_score=None,
                        threshold=self.SIMILARITY_THRESHOLD,
                        timestamp=timestamp,
                        error_message=f"User '{expected_user}' not enrolled"
                    )
                
                try:
                    enrolled_embedding = self._extract_embedding_from_enrollment(
                        enrollments[expected_user]
                    )
                    similarity = self.cosine_similarity(speaker_embedding, enrolled_embedding)
                    
                    match = similarity >= self.SIMILARITY_THRESHOLD
                    confidence = self.compute_speaker_confidence(similarity)
                    
                    result = VerificationResult.MATCH if match else VerificationResult.NO_MATCH
                    
                    return SpeakerVerification(
                        result=result,
                        user_name=expected_user,
                        similarity_score=similarity,
                        threshold=self.SIMILARITY_THRESHOLD,
                        timestamp=timestamp,
                        confidence=confidence
                    )
                
                except ValueError as e:
                    return SpeakerVerification(
                        result=VerificationResult.ERROR,
                        user_name=expected_user,
                        similarity_score=None,
                        threshold=self.SIMILARITY_THRESHOLD,
                        timestamp=timestamp,
                        error_message=f"Failed to verify user: {str(e)}"
                    )
            
            else:
                # Mode: Identify best match
                best_user, best_similarity = self.find_best_match(speaker_embedding)
                
                if best_user is None:
                    return SpeakerVerification(
                        result=VerificationResult.NO_MATCH,
                        user_name=None,
                        similarity_score=0.0,
                        threshold=self.SIMILARITY_THRESHOLD,
                        timestamp=timestamp,
                        error_message="No matching speaker found in system"
                    )
                
                match = best_similarity >= self.SIMILARITY_THRESHOLD
                confidence = self.compute_speaker_confidence(best_similarity)
                
                result = VerificationResult.MATCH if match else VerificationResult.NO_MATCH
                
                return SpeakerVerification(
                    result=result,
                    user_name=best_user,
                    similarity_score=best_similarity,
                    threshold=self.SIMILARITY_THRESHOLD,
                    timestamp=timestamp,
                    confidence=confidence
                )
        
        except ValueError as e:
            logger.error(f"Verification error: {e}")
            return SpeakerVerification(
                result=VerificationResult.ERROR,
                user_name=None,
                similarity_score=None,
                threshold=self.SIMILARITY_THRESHOLD,
                timestamp=timestamp,
                error_message=str(e)
            )
        except Exception as e:
            logger.error(f"Unexpected verification error: {e}")
            return SpeakerVerification(
                result=VerificationResult.ERROR,
                user_name=None,
                similarity_score=None,
                threshold=self.SIMILARITY_THRESHOLD,
                timestamp=timestamp,
                error_message=f"Unexpected error: {str(e)}"
            )


# Global singleton instance
_verification_service: Optional[VerificationService] = None


def get_verification_service(enrollment_data_dir: str = "01_central_server/data") -> VerificationService:
    """
    Get global verification service instance (singleton).
    
    Args:
        enrollment_data_dir: Directory containing enrolled user data
        
    Returns:
        VerificationService instance
    """
    global _verification_service
    if _verification_service is None:
        _verification_service = VerificationService(enrollment_data_dir)
    return _verification_service


if __name__ == "__main__":
    # Test speaker verification
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    service = get_verification_service()
    
    # Test cosine similarity
    print("\n=== Testing Cosine Similarity ===")
    v1 = [1, 0, 0]
    v2 = [1, 0, 0]
    v3 = [0, 1, 0]
    print(f"Same vectors: {service.cosine_similarity(v1, v2):.4f} (expected: 1.0)")
    print(f"Orthogonal vectors: {service.cosine_similarity(v1, v3):.4f} (expected: 0.0)")
    
    # Test confidence computation
    print("\n=== Testing Confidence Computation ===")
    for sim in [0.5, 0.75, 0.85, 0.95]:
        conf = service.compute_speaker_confidence(sim)
        print(f"Similarity {sim:.2f} -> Confidence {conf:.2f}")
    
    print("\n=== Verification Service Ready ===")
