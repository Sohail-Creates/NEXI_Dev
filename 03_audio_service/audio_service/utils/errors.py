"""
Custom error classes for Audio Service.
Provides specific exceptions with user-friendly messages and recovery suggestions.
"""

from typing import Optional, Dict, Any


class AudioServiceError(Exception):
    """
    Base exception for all audio service errors.
    
    Attributes:
        message: User-friendly error message
        technical_details: Technical details for logging/debugging
        user_message: Message to show to end users
        recovery_suggestion: Suggestion for how to recover from error
        error_code: Machine-readable error code
    """
    
    def __init__(
        self,
        message: str,
        technical_details: Optional[str] = None,
        user_message: Optional[str] = None,
        recovery_suggestion: Optional[str] = None,
        error_code: Optional[str] = None
    ):
        super().__init__(message)
        self.message = message
        self.technical_details = technical_details or message
        self.user_message = user_message or "An error occurred. Please try again."
        self.recovery_suggestion = recovery_suggestion or "If the problem persists, contact support."
        self.error_code = error_code or self.__class__.__name__
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for API responses."""
        return {
            "error_type": self.error_code,
            "message": self.user_message,
            "suggestion": self.recovery_suggestion,
            "technical_details": self.technical_details
        }


# ============================================================================
# NETWORK & API ERRORS
# ============================================================================

class NetworkError(AudioServiceError):
    """Network connectivity issues."""
    
    def __init__(self, message: str, technical_details: Optional[str] = None):
        super().__init__(
            message=message,
            technical_details=technical_details,
            user_message="Network connection issue. Please check your internet connection.",
            recovery_suggestion="Verify your internet connection is active and try again.",
            error_code="NETWORK_ERROR"
        )


class BackendConnectionError(NetworkError):
    """Backend server connection issues."""
    
    def __init__(self, message: str, technical_details: Optional[str] = None):
        super().__init__(
            message=message,
            technical_details=technical_details
        )
        self.user_message = "Cannot connect to backend server."
        self.recovery_suggestion = "The system will queue your request and retry automatically when the backend is available."
        self.error_code = "BACKEND_CONNECTION_ERROR"


class APITimeoutError(AudioServiceError):
    """API request timed out."""
    
    def __init__(self, service_name: str, timeout_seconds: float):
        super().__init__(
            message=f"{service_name} API request timed out after {timeout_seconds} seconds",
            user_message=f"{service_name} is taking longer than expected to respond.",
            recovery_suggestion="Please wait a moment and try again. If the issue persists, the service may be experiencing high load.",
            error_code="API_TIMEOUT"
        )


class APIRateLimitError(AudioServiceError):
    """API rate limit exceeded."""
    
    def __init__(self, service_name: str, retry_after: Optional[int] = None):
        retry_msg = f" Try again in {retry_after} seconds." if retry_after else " Please try again later."
        super().__init__(
            message=f"{service_name} API rate limit exceeded",
            user_message=f"Too many requests to {service_name}.{retry_msg}",
            recovery_suggestion=f"Wait a few moments before trying again.",
            error_code="API_RATE_LIMIT"
        )
        self.retry_after = retry_after


class APIError(AudioServiceError):
    """General API error."""
    
    def __init__(self, service_name: str, status_code: int, details: Optional[str] = None):
        super().__init__(
            message=f"{service_name} API error: HTTP {status_code}",
            technical_details=details,
            user_message=f"{service_name} service encountered an error.",
            recovery_suggestion="Please try again. If the problem persists, the service may be temporarily unavailable.",
            error_code="API_ERROR"
        )
        self.status_code = status_code


class ServiceUnavailableError(AudioServiceError):
    """External service is unavailable."""
    
    def __init__(self, service_name: str):
        super().__init__(
            message=f"{service_name} service is currently unavailable",
            user_message=f"{service_name} is temporarily unavailable.",
            recovery_suggestion="The service should be back online shortly. Please try again in a few minutes.",
            error_code="SERVICE_UNAVAILABLE"
        )


# ============================================================================
# HARDWARE ERRORS
# ============================================================================

class MicrophoneError(AudioServiceError):
    """Microphone hardware issues."""
    
    def __init__(self, message: str = None, technical_details: Optional[str] = None, 
                 user_message: Optional[str] = None, recovery_suggestion: Optional[str] = None):
        super().__init__(
            message=message or "Microphone error",
            technical_details=technical_details,
            user_message=user_message or "Cannot access microphone.",
            recovery_suggestion=recovery_suggestion or "Check that your microphone is properly connected and not being used by another application.",
            error_code="MICROPHONE_ERROR"
        )


class MicrophoneNotFoundError(MicrophoneError):
    """No microphone device found."""
    
    def __init__(self):
        super().__init__(
            message="No audio input device found",
            user_message="No microphone detected.",
            recovery_suggestion="Please connect a microphone to continue."
        )
        self.error_code = "MICROPHONE_NOT_FOUND"


class MicrophonePermissionError(MicrophoneError):
    """Microphone permission denied."""
    
    def __init__(self):
        super().__init__(
            message="Microphone permission denied",
            user_message="Permission to access microphone was denied.",
            recovery_suggestion="Please grant microphone access in your system settings and restart the application."
        )
        self.error_code = "MICROPHONE_PERMISSION_DENIED"


class AudioBufferError(AudioServiceError):
    """Audio buffer overflow or underflow."""
    
    def __init__(self, buffer_type: str = "unknown"):
        super().__init__(
            message=f"Audio buffer {buffer_type} occurred",
            user_message="Audio processing issue detected.",
            recovery_suggestion="This usually resolves itself. If audio quality is poor, try restarting the service.",
            error_code="AUDIO_BUFFER_ERROR"
        )


# ============================================================================
# RESOURCE ERRORS
# ============================================================================

class DiskFullError(AudioServiceError):
    """Disk space exhausted."""
    
    def __init__(self, required_space_mb: Optional[float] = None):
        space_msg = f" Need at least {required_space_mb}MB free." if required_space_mb else ""
        super().__init__(
            message=f"Insufficient disk space{space_msg}",
            user_message="Not enough disk space to save audio files.",
            recovery_suggestion="Free up disk space by deleting unnecessary files.",
            error_code="DISK_FULL"
        )


class MemoryError(AudioServiceError):
    """Insufficient memory."""
    
    def __init__(self):
        super().__init__(
            message="Insufficient memory to complete operation",
            user_message="System is running low on memory.",
            recovery_suggestion="Close other applications to free up memory.",
            error_code="MEMORY_ERROR"
        )


class FilePermissionError(AudioServiceError):
    """File permission denied."""
    
    def __init__(self, file_path: str):
        super().__init__(
            message=f"Permission denied for file: {file_path}",
            user_message="Cannot access required file due to permissions.",
            recovery_suggestion="Check file permissions or run with appropriate privileges.",
            error_code="FILE_PERMISSION_ERROR"
        )


# ============================================================================
# AUDIO PROCESSING ERRORS
# ============================================================================

class InvalidAudioError(AudioServiceError):
    """Audio file or data is invalid."""
    
    def __init__(self, reason: str = "unknown"):
        super().__init__(
            message=f"Invalid audio: {reason}",
            user_message="The audio file appears to be corrupted or invalid.",
            recovery_suggestion="Please record new audio or use a different file.",
            error_code="INVALID_AUDIO"
        )


class AudioTooShortError(AudioServiceError):
    """Audio duration too short for processing."""
    
    def __init__(self, duration: float, minimum: float):
        super().__init__(
            message=f"Audio too short: {duration}s (minimum: {minimum}s)",
            user_message=f"Audio is too short. Please speak for at least {minimum} seconds.",
            recovery_suggestion=f"Record for at least {minimum} seconds of clear speech.",
            error_code="AUDIO_TOO_SHORT"
        )


class AudioTooLongError(AudioServiceError):
    """Audio duration exceeds maximum."""
    
    def __init__(self, duration: float, maximum: float):
        super().__init__(
            message=f"Audio too long: {duration}s (maximum: {maximum}s)",
            user_message=f"Audio is too long. Please keep recordings under {maximum} seconds.",
            recovery_suggestion=f"Record shorter audio clips (max {maximum} seconds).",
            error_code="AUDIO_TOO_LONG"
        )


class SilenceDetectedError(AudioServiceError):
    """Only silence detected in audio."""
    
    def __init__(self):
        super().__init__(
            message="No speech detected in audio (silence only)",
            user_message="No speech detected. Please speak clearly into the microphone.",
            recovery_suggestion="Ensure you are speaking clearly and the microphone is not muted.",
            error_code="SILENCE_DETECTED"
        )


class NoiseError(AudioServiceError):
    """Audio quality too poor due to noise."""
    
    def __init__(self):
        super().__init__(
            message="Audio quality too poor (excessive background noise)",
            user_message="Too much background noise detected.",
            recovery_suggestion="Try recording in a quieter environment or closer to the microphone.",
            error_code="EXCESSIVE_NOISE"
        )


# ============================================================================
# WAKE WORD ERRORS
# ============================================================================

class WakeWordError(AudioServiceError):
    """Wake word detection errors."""
    
    def __init__(self, message: str, technical_details: Optional[str] = None):
        super().__init__(
            message=message,
            technical_details=technical_details,
            user_message="Wake word detection encountered an issue.",
            recovery_suggestion="Try stopping and restarting wake word detection.",
            error_code="WAKE_WORD_ERROR"
        )


class WakeWordAlreadyRunningError(WakeWordError):
    """Wake word detection already active."""
    
    def __init__(self):
        super().__init__(
            message="Wake word detection is already running",
            user_message="Wake word detection is already active.",
            recovery_suggestion="Stop the current detection before starting a new one."
        )
        self.error_code = "WAKE_WORD_ALREADY_RUNNING"


class WakeWordNotRunningError(WakeWordError):
    """Wake word detection not active."""
    
    def __init__(self):
        super().__init__(
            message="Wake word detection is not running",
            user_message="Wake word detection is not currently active.",
            recovery_suggestion="Start wake word detection before attempting to stop it."
        )
        self.error_code = "WAKE_WORD_NOT_RUNNING"


# ============================================================================
# SPEAKER VERIFICATION ERRORS
# ============================================================================

class SpeakerVerificationError(AudioServiceError):
    """Speaker verification errors."""
    
    def __init__(self, message: str, technical_details: Optional[str] = None):
        super().__init__(
            message=message,
            technical_details=technical_details,
            user_message="Speaker verification encountered an issue.",
            recovery_suggestion="Please try again with clearer audio.",
            error_code="SPEAKER_VERIFICATION_ERROR"
        )


class SpeakerNotFoundError(SpeakerVerificationError):
    """Speaker not enrolled."""
    
    def __init__(self, user_id: Optional[str] = None):
        user_msg = f"Speaker '{user_id}' is not enrolled." if user_id else "Unknown speaker detected."
        super().__init__(
            message=f"Speaker not found: {user_id}",
            user_message=user_msg,
            recovery_suggestion="Please enroll your voice before verification."
        )
        self.error_code = "SPEAKER_NOT_FOUND"


class SpeakerAlreadyEnrolledError(SpeakerVerificationError):
    """Speaker already enrolled."""
    
    def __init__(self, user_id: str):
        super().__init__(
            message=f"Speaker already enrolled: {user_id}",
            user_message=f"'{user_id}' is already enrolled.",
            recovery_suggestion="Use a different user ID or delete the existing enrollment."
        )
        self.error_code = "SPEAKER_ALREADY_ENROLLED"


# ============================================================================
# TRANSCRIPTION ERRORS
# ============================================================================

class TranscriptionError(AudioServiceError):
    """Speech-to-text transcription errors."""
    
    def __init__(self, message: str, technical_details: Optional[str] = None):
        super().__init__(
            message=message,
            technical_details=technical_details,
            user_message="Could not transcribe audio.",
            recovery_suggestion="Please try speaking more clearly or in a quieter environment.",
            error_code="TRANSCRIPTION_ERROR"
        )


class LanguageDetectionError(TranscriptionError):
    """Language detection failed."""
    
    def __init__(self):
        super().__init__(
            message="Could not reliably detect language",
            user_message="Could not determine the language spoken.",
            recovery_suggestion="Try speaking for a bit longer or manually select the language."
        )
        self.error_code = "LANGUAGE_DETECTION_ERROR"


class EmptyTranscriptionError(TranscriptionError):
    """Transcription returned empty result."""
    
    def __init__(self):
        super().__init__(
            message="Transcription returned empty result",
            user_message="No speech could be transcribed from the audio.",
            recovery_suggestion="Please speak more clearly and ensure the microphone is working."
        )
        self.error_code = "EMPTY_TRANSCRIPTION"


class SuspiciousTranscriptionError(TranscriptionError):
    """Transcription result appears invalid."""
    
    def __init__(self, reason: str):
        super().__init__(
            message=f"Suspicious transcription: {reason}",
            user_message="The transcription result may not be accurate.",
            recovery_suggestion="Try recording again with clearer speech."
        )
        self.error_code = "SUSPICIOUS_TRANSCRIPTION"


class AudioQualityError(AudioServiceError):
    """Audio quality is insufficient for transcription."""
    
    def __init__(self, reason: str, technical_details: str = None):
        super().__init__(
            message=f"Poor audio quality: {reason}",
            user_message="The audio quality is too low for accurate transcription.",
            recovery_suggestion="Please speak louder and closer to the microphone, and reduce background noise.",
            technical_details=technical_details
        )
        self.error_code = "AUDIO_QUALITY"


# ============================================================================
# CONFIGURATION ERRORS
# ============================================================================

class ConfigurationError(AudioServiceError):
    """Configuration or setup errors."""
    
    def __init__(self, message: str):
        super().__init__(
            message=message,
            user_message="System configuration error.",
            recovery_suggestion="Please check your configuration and restart the service.",
            error_code="CONFIGURATION_ERROR"
        )


class MissingAPIKeyError(ConfigurationError):
    """Required API key not configured."""
    
    def __init__(self, service_name: str):
        super().__init__(
            message=f"Missing API key for {service_name}",
            user_message=f"{service_name} is not configured.",
            recovery_suggestion=f"Please add the {service_name} API key to your .env file."
        )
        self.error_code = "MISSING_API_KEY"


# ============================================================================
# DATABASE & QUEUE ERRORS  
# ============================================================================

class DatabaseError(AudioServiceError):
    """Database operation errors."""
    
    def __init__(self, message: str, technical_details: Optional[str] = None):
        super().__init__(
            message=message,
            technical_details=technical_details,
            user_message="Database operation failed.",
            recovery_suggestion="The system will retry automatically. If the problem persists, contact support.",
            error_code="DATABASE_ERROR"
        )


class QueueError(AudioServiceError):
    """Queue management errors."""
    
    def __init__(self, message: str, technical_details: Optional[str] = None):
        super().__init__(
            message=message,
            technical_details=technical_details,
            user_message="Queue operation failed.",
            recovery_suggestion="The system will retry automatically. Your request will be processed when possible.",
            error_code="QUEUE_ERROR"
        )


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def wrap_error(error: Exception) -> AudioServiceError:
    """
    Wrap a generic exception into a user-friendly AudioServiceError.
    
    Args:
        error: Original exception
    
    Returns:
        AudioServiceError with appropriate user message
    """
    # If already an AudioServiceError, return as-is
    if isinstance(error, AudioServiceError):
        return error
    
    # Map common exception types to AudioServiceError
    error_str = str(error).lower()
    
    if "timeout" in error_str:
        return NetworkError(
            message=f"Operation timed out: {error}",
            technical_details=str(error)
        )
    
    if "connection" in error_str or "network" in error_str:
        return NetworkError(
            message=f"Network error: {error}",
            technical_details=str(error)
        )
    
    if "permission" in error_str:
        return FilePermissionError(file_path="unknown")
    
    if "disk" in error_str or "space" in error_str:
        return DiskFullError()
    
    if "memory" in error_str:
        return MemoryError()
    
    # Default: wrap as generic AudioServiceError
    return AudioServiceError(
        message=str(error),
        technical_details=str(error),
        user_message="An unexpected error occurred.",
        recovery_suggestion="Please try again. If the problem persists, contact support."
    )
