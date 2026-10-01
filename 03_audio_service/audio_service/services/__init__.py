"""
Services package initialization.
Contains core business logic services for audio intelligence features.
"""

__all__ = [
    "WakeWordService",
    "SpeakerService",
    "STTService",
]


def __getattr__(name):
    """Load service classes on demand so importing one service does not load
    unrelated hardware/runtime dependencies such as PyAudio."""
    if name == "WakeWordService":
        from audio_service.services.wake_word_service import WakeWordService
        return WakeWordService
    if name == "SpeakerService":
        from audio_service.services.speaker_service import SpeakerService
        return SpeakerService
    if name == "STTService":
        from audio_service.services.stt_service import STTService
        return STTService
    raise AttributeError(name)
