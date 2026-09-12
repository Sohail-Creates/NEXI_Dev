"""
Speaker verification service using Resemblyzer.
Implements speaker enrollment and voice-based identification using voice embeddings.
"""

import logging
import pickle
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple, Optional, List

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from audio_service.config import (
    SPEAKER_CONFIG,
    DATA_DIR,
    ENROLLMENT_FILE_PREFIX,
    TIMESTAMP_FORMAT,
    AUDIO_FILE_EXTENSION
)
from audio_service.utils.audio_preprocessing import (
    load_audio_file,
    preprocess_audio,
    validate_audio_duration
)
from audio_service.utils.audio_utils import record_and_save_audio
from audio_service.utils.cache import get_default_cache
from shared.secure_storage import ENCRYPTED_PREFIX, RotatingFernet

logger = logging.getLogger(__name__)

SPEAKER_STORE_SCHEMA_VERSION = 1
SPEAKER_EMBEDDING_DIMENSION = 256


class _RestrictedNumpyUnpickler(pickle.Unpickler):
    """Legacy-only loader restricted to the globals used by NumPy arrays."""

    _ALLOWED = {
        ("numpy", "dtype"),
        ("numpy", "ndarray"),
        ("numpy.core.multiarray", "_reconstruct"),
        ("numpy._core.multiarray", "_reconstruct"),
        ("numpy.core.multiarray", "scalar"),
        ("numpy._core.multiarray", "scalar"),
    }

    def find_class(self, module, name):
        if (module, name) not in self._ALLOWED:
            raise pickle.UnpicklingError(f"Forbidden legacy pickle global: {module}.{name}")
        return super().find_class(module, name)


def _validated_embeddings(records) -> Dict[str, np.ndarray]:
    if not isinstance(records, dict):
        raise SpeakerServiceError("Speaker store must contain an object keyed by user_id")
    validated = {}
    for user_id, values in records.items():
        if not isinstance(user_id, str) or not user_id or not isinstance(values, (list, np.ndarray)):
            raise SpeakerServiceError("Invalid speaker store record")
        vector = np.asarray(values, dtype=np.float32)
        if vector.shape != (SPEAKER_EMBEDDING_DIMENSION,) or not np.isfinite(vector).all():
            raise SpeakerServiceError(f"Invalid embedding for {user_id}")
        validated[user_id] = vector
    return validated


def _write_json_store(path: Path, records: Dict[str, np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SPEAKER_STORE_SCHEMA_VERSION,
        "embedding_dimension": SPEAKER_EMBEDDING_DIMENSION,
        "speakers": {key: value.astype(float).tolist() for key, value in records.items()},
    }
    import tempfile
    fd, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        encoded = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode("utf-8")
        with os.fdopen(fd, "wb") as handle:
            handle.write(RotatingFernet().encrypt(encoded))
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def migrate_legacy_pickle(legacy_path: Path, json_path: Path) -> Dict[str, int]:
    """Idempotently migrate a trusted legacy file through a restricted loader."""
    if json_path.exists():
        raw = json_path.read_bytes()
        was_plaintext = not raw.startswith(ENCRYPTED_PREFIX)
        cipher = RotatingFernet()
        needs_rotation = not was_plaintext and not cipher.is_current(raw)
        payload = json.loads((raw if was_plaintext else cipher.decrypt(raw)).decode("utf-8"))
        existing = _validated_embeddings(payload.get("speakers", {}))
        if was_plaintext or needs_rotation:
            _write_json_store(json_path, existing)
        updated = was_plaintext or needs_rotation
        return {"examined": len(existing), "updated": len(existing) if updated else 0,
                "unchanged": 0 if updated else len(existing)}
    if not legacy_path.exists():
        return {"examined": 0, "updated": 0, "unchanged": 0}
    with legacy_path.open("rb") as handle:
        records = _validated_embeddings(_RestrictedNumpyUnpickler(handle).load())
    _write_json_store(json_path, records)
    return {"examined": len(records), "updated": len(records), "unchanged": 0}


class SpeakerServiceError(Exception):
    """Custom exception for speaker service errors."""
    pass


class SpeakerService:
    """
    Service for speaker enrollment and verification.
    
    This service uses Resemblyzer to create voice embeddings (numerical representations)
    of speaker voices. These embeddings can be compared to identify who is speaking.
    """
    
    def __init__(self):
        """Initialize the speaker verification service."""
        # Use a generic object type for encoder to avoid importing resemblyzer at module import time
        self.encoder: Optional[object] = None
        self.embeddings_file: Path = SPEAKER_CONFIG["embeddings_file"]
        if self.embeddings_file.suffix.lower() != ".json":
            self.embeddings_file = self.embeddings_file.with_suffix(".json")
        self.legacy_embeddings_file = self.embeddings_file.with_suffix(".pkl")
        self.speaker_embeddings: Dict[str, np.ndarray] = {}

        # Load existing embeddings if available
        self._load_embeddings()

        # Small cache for preprocessed audio files to speed up repeated ops
        max_cache = 32
        try:
            # prefer a configured limit if present
            from audio_service.config import RESILIENCE_CONFIG
            max_cache = int(RESILIENCE_CONFIG.get("resource_limits", {}).get("max_concurrent_transcriptions", 32))
        except Exception:
            pass
        self._preprocess_cache = get_default_cache(max_items=max_cache)

        logger.info("Speaker service initialized")
    
    def initialize_encoder(self):
        """
        Initialize the Resemblyzer voice encoder.
        
        This loads the pre-trained neural network that converts voice audio
        into fixed-size embedding vectors. The encoder is loaded on-demand
        to save memory when not needed.
        
        Raises:
            SpeakerServiceError: If encoder initialization fails
        """
        try:
            if self.encoder is None:
                logger.info("Loading Resemblyzer voice encoder...")
                # Lazy import to avoid import-time dependency issues
                try:
                    from resemblyzer import VoiceEncoder
                except Exception as e:
                    error_msg = f"Failed to import Resemblyzer: {e}. Install Microsoft Visual C++ Build Tools and run: pip install resemblyzer==0.1.1.dev0"
                    logger.error(error_msg)
                    raise SpeakerServiceError(error_msg) from e

                self.encoder = VoiceEncoder()
                logger.info("Voice encoder loaded successfully")
        except Exception as e:
            error_msg = f"Failed to initialize voice encoder: {str(e)}"
            logger.error(error_msg)
            raise SpeakerServiceError(error_msg) from e
    
    def _load_embeddings(self):
        """
        Load speaker embeddings from disk.
        
        This retrieves previously enrolled speaker voice embeddings from storage.
        If the file doesn't exist, it will be created on the first enrollment.
        """
        try:
            migration = migrate_legacy_pickle(self.legacy_embeddings_file, self.embeddings_file)
            if migration["updated"]:
                logger.info("Migrated %d legacy speaker embeddings", migration["updated"])
            if self.embeddings_file.exists():
                payload = json.loads(RotatingFernet().decrypt(self.embeddings_file.read_bytes()).decode("utf-8"))
                if payload.get("schema_version") != SPEAKER_STORE_SCHEMA_VERSION:
                    raise SpeakerServiceError("Unsupported speaker store schema")
                if payload.get("embedding_dimension") != SPEAKER_EMBEDDING_DIMENSION:
                    raise SpeakerServiceError("Speaker store dimension mismatch")
                self.speaker_embeddings = _validated_embeddings(payload.get("speakers", {}))
                logger.info(f"Loaded {len(self.speaker_embeddings)} speaker embeddings")
            else:
                logger.info("No existing embeddings file found, starting fresh")
                self.speaker_embeddings = {}
        except Exception as e:
            logger.error(f"Failed to load embeddings: {str(e)}")
            raise SpeakerServiceError("Speaker embeddings failed validation") from e
    
    def _save_embeddings(self):
        """
        Save speaker embeddings to disk.
        
        This persists the current set of speaker embeddings so they are available
        after service restarts.
        
        Raises:
            SpeakerServiceError: If save operation fails
        """
        try:
            _write_json_store(self.embeddings_file, _validated_embeddings(self.speaker_embeddings))

            logger.info(f"Saved {len(self.speaker_embeddings)} speaker embeddings")

        except Exception as e:
            error_msg = f"Failed to save embeddings: {str(e)}"
            logger.error(error_msg)
            raise SpeakerServiceError(error_msg) from e
    
    def validate_embeddings_consistency(self) -> Dict[str, any]:
        """
        Validate that all stored embeddings have correct format and dimensions.
        
        Returns:
            Dictionary with validation results:
            {
                "valid": bool,
                "total_speakers": int,
                "expected_dimension": int,
                "issues": List[str]
            }
        """
        issues = []
        valid_count = 0
        
        for user_id, embedding in self.speaker_embeddings.items():
            try:
                # Check type
                if not isinstance(embedding, (np.ndarray, list)):
                    issues.append(f"{user_id}: embedding is {type(embedding).__name__}, expected ndarray or list")
                    continue
                
                # Check dimension (Resemblyzer uses 256-dimensional embeddings)
                embed_len = len(embedding)
                if embed_len != 256:
                    issues.append(f"{user_id}: dimension is {embed_len}, expected 256")
                else:
                    valid_count += 1
                
            except Exception as e:
                issues.append(f"{user_id}: validation error - {str(e)}")
        
        return {
            "valid": len(issues) == 0,
            "total_speakers": len(self.speaker_embeddings),
            "valid_speakers": valid_count,
            "expected_dimension": 256,
            "issues": issues if issues else None
        }
    
    def enroll_speaker(self, user_id: str, duration: Optional[float] = None) -> Tuple[str, int, list]:
        """
        Enroll a new speaker by recording their voice and creating an embedding.
        
        This captures a voice sample from the speaker, generates a unique voice
        embedding, and stores it associated with the user ID.
        
        Args:
            user_id: Unique identifier for the speaker
            duration: Recording duration in seconds (uses config default if None)
        
        Returns:
            Tuple containing:
                - audio_file_path: Path to the enrollment audio file
                - embedding_size: Size of the generated embedding vector (256)
                - embedding_array: The actual voice embedding as a list of floats
        
        Raises:
            SpeakerServiceError: If enrollment fails
        """
        try:
            # Initialize encoder if not already done
            self.initialize_encoder()
            
            # Use default duration if not specified
            if duration is None:
                duration = SPEAKER_CONFIG["enrollment_duration"]
            
            # Validate duration
            if duration < SPEAKER_CONFIG["min_speech_duration"]:
                raise SpeakerServiceError(
                    f"Enrollment duration must be at least {SPEAKER_CONFIG['min_speech_duration']} seconds"
                )
            
            # Generate filename for enrollment audio
            timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
            filename = f"{ENROLLMENT_FILE_PREFIX}_{user_id}_{timestamp}{AUDIO_FILE_EXTENSION}"
            
            logger.info(f"Starting enrollment for user: {user_id} (duration: {duration}s)")
            
            # Record audio sample
            file_metadata = record_and_save_audio(
                duration=duration,
                sample_rate=SPEAKER_CONFIG["sample_rate"],
                channels=1,
                filename=filename
            )
            
            audio_file_path = file_metadata["filepath"]
            
            # Load and preprocess the recorded audio
            audio_data, sample_rate = load_audio_file(audio_file_path)
            
            # Validate audio duration
            if not validate_audio_duration(
                audio_data,
                sample_rate,
                min_duration=SPEAKER_CONFIG["min_speech_duration"]
            ):
                raise SpeakerServiceError(
                    f"Recorded audio is too short for enrollment (minimum {SPEAKER_CONFIG['min_speech_duration']}s)"
                )
            
            # Preprocess audio for Resemblyzer (lazy import)
            try:
                from resemblyzer import preprocess_wav
            except Exception as e:
                error_msg = f"Failed to import Resemblyzer preprocess_wav: {e}"
                logger.error(error_msg)
                raise SpeakerServiceError(error_msg) from e

            # Use cache keyed by filepath mtime to avoid reprocessing
            cached = self._preprocess_cache.get(audio_file_path)
            if cached is not None:
                preprocessed_audio, _ = cached
            else:
                # Resemblyzer expects audio at 16kHz
                preprocessed_audio = preprocess_wav(audio_data, sample_rate)
                try:
                    # cache processed waveform (we store sample rate as 16000 for consistency)
                    self._preprocess_cache.set(audio_file_path, (preprocessed_audio, 16000))
                except Exception:
                    pass
            
            # Generate voice embedding
            embedding = self.encoder.embed_utterance(preprocessed_audio)  # type: ignore
            
            # Store embedding with user ID
            self.speaker_embeddings[user_id] = embedding
            
            # Save to disk
            self._save_embeddings()
            
            logger.info(
                f"Successfully enrolled speaker: {user_id} "
                f"(embedding size: {len(embedding)})"
            )
            
            # Convert numpy array to list for JSON serialization
            embedding_list = embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)
            
            return audio_file_path, len(embedding), embedding_list
            
        except Exception as e:
            error_msg = f"Failed to enroll speaker {user_id}: {str(e)}"
            logger.error(error_msg)
            raise SpeakerServiceError(error_msg) from e
    
    def enroll_speaker_from_files(self, user_id: str, audio_files: list) -> dict:
        """
        Enroll a speaker using pre-recorded audio files.
        
        Alternative to microphone recording - accepts uploaded audio files.
        Averages embeddings from multiple files for better accuracy.
        
        Args:
            user_id: Unique identifier for the speaker
            audio_files: List of audio file paths
            
        Returns:
            dict with embedding_size, embedding_array, and audio_files
            
        Raises:
            SpeakerServiceError: If enrollment fails
        """
        try:
            # Initialize encoder if not already done
            self.initialize_encoder()
            
            if not audio_files or len(audio_files) == 0:
                raise SpeakerServiceError("At least one audio file required for enrollment")
            
            logger.info(f"Enrolling speaker from {len(audio_files)} files: {user_id}")
            
            embeddings = []
            
            # Process each audio file
            for audio_file in audio_files:
                # Load and preprocess audio
                audio_data, sample_rate = load_audio_file(audio_file)
                
                # Validate audio duration
                if not validate_audio_duration(
                    audio_data,
                    sample_rate,
                    min_duration=SPEAKER_CONFIG["min_speech_duration"]
                ):
                    logger.warning(f"Skipping short audio file: {audio_file}")
                    continue
                
                # Preprocess for Resemblyzer (16kHz) - lazy import
                try:
                    from resemblyzer import preprocess_wav
                except Exception as e:
                    logger.warning(f"Failed to import Resemblyzer preprocess_wav for file {audio_file}: {e}")
                    continue

                # Use cache if available
                cached = self._preprocess_cache.get(audio_file)
                if cached is not None:
                    preprocessed_audio, _ = cached
                else:
                    preprocessed_audio = preprocess_wav(audio_data, sample_rate)
                    try:
                        self._preprocess_cache.set(audio_file, (preprocessed_audio, 16000))
                    except Exception:
                        pass
                
                # Generate embedding
                embedding = self.encoder.embed_utterance(preprocessed_audio)  # type: ignore
                embeddings.append(embedding)
            
            if len(embeddings) == 0:
                raise SpeakerServiceError("No valid audio files for enrollment")
            
            # Average embeddings if multiple files
            if len(embeddings) > 1:
                import numpy as np
                final_embedding = np.mean(embeddings, axis=0)
            else:
                final_embedding = embeddings[0]
            
            # Store embedding
            self.speaker_embeddings[user_id] = final_embedding
            
            # Save to disk
            self._save_embeddings()
            
            logger.info(f"Successfully enrolled speaker: {user_id} from {len(embeddings)} files")
            
            # Convert embedding to list for JSON serialization
            embedding_list = final_embedding.tolist() if hasattr(final_embedding, 'tolist') else list(final_embedding)
            
            return {
                "embedding_size": len(final_embedding),
                "embedding_array": embedding_list,
                "audio_files": len(audio_files),
                "num_embeddings": len(embeddings)
            }
            
        except Exception as e:
            error_msg = f"Failed to enroll speaker {user_id} from files: {str(e)}"
            logger.error(error_msg)
            raise SpeakerServiceError(error_msg) from e
    
    def verify_speaker(self, audio_file_path: str) -> Tuple[str, float]:
        """
        Verify speaker identity from audio file.
        
        This loads an audio file, generates a voice embedding, and compares it
        against all enrolled speakers to find the best match.
        
        Args:
            audio_file_path: Path to the audio file for verification
        
        Returns:
            Tuple containing:
                - user_id: Identified user ID or "unknown" if not matched
                - confidence: Similarity score (0.0 to 1.0)
        
        Raises:
            SpeakerServiceError: If verification fails
        """
        try:
            # Initialize encoder if not already done
            self.initialize_encoder()
            
            # Check if there are any enrolled speakers
            if not self.speaker_embeddings:
                logger.warning("No enrolled speakers found for verification")
                return "unknown", 0.0
            
            # Load and preprocess audio
            audio_data, sample_rate = load_audio_file(audio_file_path)
            
            # Validate audio has sufficient duration
            if not validate_audio_duration(
                audio_data,
                sample_rate,
                min_duration=SPEAKER_CONFIG["min_speech_duration"]
            ):
                raise SpeakerServiceError(
                    f"Audio is too short for verification (minimum {SPEAKER_CONFIG['min_speech_duration']}s)"
                )
            
            # Preprocess for Resemblyzer (lazy import)
            try:
                from resemblyzer import preprocess_wav
            except Exception as e:
                error_msg = f"Failed to import Resemblyzer preprocess_wav: {e}"
                logger.error(error_msg)
                raise SpeakerServiceError(error_msg) from e

            preprocessed_audio = preprocess_wav(audio_data, sample_rate)
            
            # Generate embedding for the input audio
            test_embedding = self.encoder.embed_utterance(preprocessed_audio)  # type: ignore
            
            # Compare against all enrolled speakers
            best_match_id = "unknown"
            best_similarity = 0.0
            
            for user_id, stored_embedding in self.speaker_embeddings.items():
                # Calculate cosine similarity between embeddings
                # Reshape for sklearn
                similarity = cosine_similarity(
                    test_embedding.reshape(1, -1),
                    stored_embedding.reshape(1, -1)
                )[0][0]
                
                logger.debug(f"Similarity with {user_id}: {similarity:.4f}")
                
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match_id = user_id
            
            # Check if similarity meets threshold
            threshold = SPEAKER_CONFIG["verification_threshold"]
            
            if best_similarity < threshold:
                logger.info(
                    f"No match found above threshold {threshold} "
                    f"(best: {best_similarity:.4f})"
                )
                return "unknown", float(best_similarity)
            
            logger.info(
                f"Verified speaker: {best_match_id} "
                f"(confidence: {best_similarity:.4f})"
            )
            
            return best_match_id, float(best_similarity)
            
        except Exception as e:
            error_msg = f"Failed to verify speaker: {str(e)}"
            logger.error(error_msg)
            raise SpeakerServiceError(error_msg) from e
    
    def list_enrolled_speakers(self) -> List[str]:
        """
        Get list of all enrolled speaker IDs.
        
        Returns:
            List of user IDs for all enrolled speakers
        """
        return list(self.speaker_embeddings.keys())
    
    def delete_speaker(self, user_id: str) -> bool:
        """
        Remove a speaker from the enrollment database.
        
        Args:
            user_id: User ID of the speaker to remove
        
        Returns:
            True if speaker was removed, False if not found
        
        Raises:
            SpeakerServiceError: If deletion fails
        """
        try:
            if user_id not in self.speaker_embeddings:
                logger.warning(f"Speaker not found: {user_id}")
                return False
            
            del self.speaker_embeddings[user_id]
            self._save_embeddings()
            
            logger.info(f"Deleted speaker: {user_id}")
            return True
            
        except Exception as e:
            error_msg = f"Failed to delete speaker {user_id}: {str(e)}"
            logger.error(error_msg)
            raise SpeakerServiceError(error_msg) from e
    
    def get_speaker_count(self) -> int:
        """
        Get the number of enrolled speakers.
        
        Returns:
            Count of enrolled speakers
        """
        return len(self.speaker_embeddings)
    
    def get_verification_threshold(self) -> float:
        """
        Get the current verification threshold.
        
        Returns:
            Cosine similarity threshold for speaker verification
        """
        return SPEAKER_CONFIG["verification_threshold"]
