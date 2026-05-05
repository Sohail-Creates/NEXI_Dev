"""
Speech-to-Text service using Groq Whisper API.
Implements audio transcription with support for Urdu and English languages.

Week 3 Enhancements:
- Circuit breaker pattern for API resilience
- Smart language detection based on audio characteristics
- Quality validation for transcription results
- error handling with custom error classes
"""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional, Dict
import numpy as np

from groq import Groq

from audio_service.config import (
    STT_CONFIG,
    GROQ_API_KEY,
    ENHANCED_STT_CONFIG,
    VAD_CONFIG,
    RESILIENCE_CONFIG,
)
from audio_service.utils.audio_preprocessing import (
    load_audio_file,
    preprocess_audio_file
)
from audio_service.utils.cache import get_default_cache
from audio_service.utils.errors import (
    TranscriptionError,
    EmptyTranscriptionError,
    LanguageDetectionError,
    SilenceDetectedError,
    AudioQualityError,
    APITimeoutError,
    APIRateLimitError,
    ServiceUnavailableError
)
import sys
from pathlib import Path

# Add parent directories to path for shared utilities
sys_path = str(Path(__file__).resolve().parent.parent.parent.parent)
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

from shared.utils.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class STTServiceError(Exception):
    """Custom exception for speech-to-text service errors."""
    pass


class STTService:
    """
    Service for speech-to-text transcription using Groq Whisper API.
    
    This service converts spoken audio into written text, with support for
    automatic language detection and multiple languages including Urdu and English.
    
    Week 3 Enhancements:
    - Circuit breaker for API calls (prevents cascading failures)
    - Smart language detection based on audio energy patterns
    - Quality validation ensures accurate transcriptions
    - error handling with user-friendly messages
    """
    
    def __init__(self):
        """Initialize the speech-to-text service with Week 3 enhancements."""
        self.client: Optional[Groq] = None
        self.model: str = STT_CONFIG["model"]
        
        # Circuit breaker for API resilience
        self.circuit_breaker = CircuitBreaker(
            name="STT-Groq-API",
            failure_threshold=ENHANCED_STT_CONFIG["circuit_breaker"]["failure_threshold"],
            recovery_timeout=ENHANCED_STT_CONFIG["circuit_breaker"]["recovery_timeout"],
            recovery_threshold=ENHANCED_STT_CONFIG["circuit_breaker"]["recovery_threshold"]
        )
        
        # Statistics tracking
        self.stats = {
            "total_transcriptions": 0,
            "successful_transcriptions": 0,
            "failed_transcriptions": 0,
            "circuit_breaker_trips": 0,
            "language_detections": {"en": 0, "ur": 0, "other": 0},
            "average_confidence": 0.0,
            "api_calls": 0,
            "average_api_latency": 0.0,
            "last_api_latency": None,
            "quality_failures": 0
        }

        # Concurrency control for transcription requests
        # Use resource_limits from RESILIENCE_CONFIG if available
        try:
            # Prefer a global resource limit if available
            max_concurrent = int(RESILIENCE_CONFIG.get("resource_limits", {}).get("max_concurrent_transcriptions", 1))
        except Exception:
            try:
                max_concurrent = int(ENHANCED_STT_CONFIG.get("max_concurrent_transcriptions", 1))
            except Exception:
                max_concurrent = 1

        import threading
        self._transcription_semaphore = threading.Semaphore(max_concurrent)

        # Cache for preprocessed audio files (helps repeated transcribe calls)
        try:
            cache_size = int(RESILIENCE_CONFIG.get("resource_limits", {}).get("max_concurrent_transcriptions", 32))
        except Exception:
            cache_size = 32
        self._preprocess_cache = get_default_cache(max_items=cache_size)
        
        logger.info("STT service initialized with Week 3 enhancements (circuit breaker, quality validation)")

        # Initialize external clients (Groq) eagerly so transcribe endpoints work
        # without requiring an explicit call to initialize_client elsewhere.
        try:
            self.initialize_client()
        except Exception:
            # initialize_client handles its own logging; proceed with self.client possibly None
            pass
    
    def initialize_client(self):
        """Initialize Groq client for transcription calls."""
        try:
            # Initialize Groq client (lazy init allowed elsewhere)
            self.client = Groq(api_key=GROQ_API_KEY)
            logger.info("Groq client initialized for STT service")
        except Exception as e:
            logger.exception(f"Failed to initialize Groq client: {e}")
            self.client = None

    def transcribe_audio(
        self,
        audio_file_path: str,
        language: str = "auto",
    ) -> Tuple[str, str, float]:
        """
        Transcribe audio and return (text, detected_language, duration_seconds).
        """
        try:
            audio_path = Path(audio_file_path)

            # Default effective language
            effective_language = language if language else STT_CONFIG["default_language"]

            # If auto, attempt probe-based detection first, then heuristic
            if language == "auto":
                try:
                    # Load audio for probes
                    audio_sample, sr = load_audio_file(audio_file_path)
                    probe_candidates = []

                    # Try up to two short probes (start and middle) if audio long enough
                    probe_seconds = min(3.0, max(1.0, len(audio_sample) / sr if sr > 0 else 1.0))
                    probe_durations = [probe_seconds]
                    total_seconds = len(audio_sample) / sr if sr > 0 else 0
                    if total_seconds > (probe_seconds * 2):
                        probe_durations.append(probe_seconds)

                    from audio_service.utils.audio_preprocessing import convert_to_int16
                    import scipy.io.wavfile as wavfile
                    import tempfile

                    for idx, pd in enumerate(probe_durations):
                        if idx == 0:
                            start = 0
                        else:
                            start = max(0, int((len(audio_sample) - int(pd * sr)) // 2))
                        end = start + int(pd * sr)
                        probe_slice = audio_sample[start:end]

                        probe_temp = tempfile.NamedTemporaryFile(delete=False, suffix='.wav', dir=audio_path.parent)
                        probe_path = probe_temp.name
                        probe_temp.close()
                        try:
                            wavfile.write(probe_path, sr, convert_to_int16(probe_slice))
                            with open(probe_path, 'rb') as pf:
                                probe_params_local = {
                                    "file": (Path(probe_path).name, pf, "audio/wav"),
                                    "model": self.model,
                                    "response_format": "verbose_json",
                                    "temperature": 0.0,
                                }
                                try:
                                    if self.circuit_breaker is not None and self.client is not None:
                                        probe_resp = self.circuit_breaker.call(lambda: self.client.audio.transcriptions.create(**probe_params_local))
                                    elif self.client is not None:
                                        probe_resp = self.client.audio.transcriptions.create(**probe_params_local)
                                    else:
                                        probe_resp = {}

                                    probe_lang = getattr(probe_resp, 'language', None) or (probe_resp.get('language') if isinstance(probe_resp, dict) else None) or getattr(probe_resp, 'language_code', None) or (probe_resp.get('language_code') if isinstance(probe_resp, dict) else None)
                                    probe_text = getattr(probe_resp, 'text', None) or (probe_resp.get('text') if isinstance(probe_resp, dict) else None)

                                    if not probe_lang:
                                        import re
                                        arabic_re = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
                                        arabic_count = len(arabic_re.findall(probe_text or ""))
                                        latin_count = len(re.findall(r"[A-Za-z]", probe_text or ""))
                                        if arabic_count > latin_count and arabic_count > 0:
                                            probe_lang = 'ur'
                                        elif latin_count > arabic_count and latin_count > 0:
                                            probe_lang = 'en'

                                    if probe_lang:
                                        probe_candidates.append(probe_lang)
                                except Exception:
                                    logger.debug("Probe transcription failed; continuing")
                        finally:
                            try:
                                import os
                                os.unlink(probe_path)
                            except Exception:
                                pass

                    # Majority vote
                    if probe_candidates:
                        from collections import Counter
                        counts = Counter(probe_candidates)
                        most_common, cnt = counts.most_common(1)[0]
                        if most_common in STT_CONFIG['supported_languages']:
                            effective_language = most_common
                            logger.info(f"Probe-based language detection result: {effective_language} (votes: {counts})")
                    else:
                        # Fallback to local heuristic
                        try:
                            detected = self._detect_language_smart(audio_sample, sr)
                            if detected in STT_CONFIG["supported_languages"]:
                                effective_language = detected
                                logger.info(f"Heuristic language detection suggested: {detected}")
                        except Exception:
                            logger.debug("Local heuristic detection failed; leaving language as auto")

                except Exception as e:
                    logger.debug(f"Probe-based detection failed: {e}")

            elif language in STT_CONFIG["supported_languages"]:
                effective_language = language
            else:
                logger.warning(f"Unsupported language '{language}', falling back to default: {STT_CONFIG['default_language']}")
                effective_language = STT_CONFIG["default_language"]

            # Apply preprocessing if enabled for better transcription accuracy
            if STT_CONFIG.get("enable_preprocessing", True):
                logger.info("Applying audio preprocessing (noise reduction + normalization + silence trimming)...")
                try:
                    from scipy.io import wavfile
                    import tempfile

                    # Use cache for preprocess if available
                    cached = self._preprocess_cache.get(audio_file_path)
                    if cached is not None:
                        processed_data, sample_rate = cached
                    else:
                        # Preprocess the audio
                        processed_data, sample_rate = preprocess_audio_file(
                            audio_file_path,
                            target_sr=16000,
                            normalize=True,
                            noise_reduction=True
                        )
                        try:
                            self._preprocess_cache.set(audio_file_path, (processed_data, sample_rate))
                        except Exception:
                            pass

                    # Trim silence from beginning and end to reduce hallucinations
                    # Trim silence if librosa is available; otherwise skip
                    try:
                        import librosa
                        if librosa is not None:
                            processed_data, _ = librosa.effects.trim(
                                processed_data,
                                top_db=30,  # Trim audio quieter than 30dB below peak
                                frame_length=2048,
                                hop_length=512
                            )
                            logger.info("Trimmed silence from audio edges")
                        else:
                            logger.debug("librosa not available; skipping trim")
                    except Exception as _trim_err:
                        logger.debug(f"librosa trim failed or unavailable: {_trim_err}; skipping trim")

                    # Save preprocessed audio to temporary file
                    temp_file = tempfile.NamedTemporaryFile(
                        delete=False,
                        suffix='.wav',
                        dir=audio_path.parent
                    )
                    temp_path = temp_file.name
                    temp_file.close()

                    # Convert to int16 for WAV format
                    from audio_service.utils.audio_preprocessing import convert_to_int16
                    audio_int16 = convert_to_int16(processed_data)
                    wavfile.write(temp_path, sample_rate, audio_int16)

                    logger.info(f"Preprocessed audio saved to temporary file")
                    audio_file_to_use = temp_path
                    cleanup_temp = True

                except Exception as preprocess_error:
                    logger.warning(f"Preprocessing failed, using original file: {str(preprocess_error)}")
                    audio_file_to_use = str(audio_path)
                    cleanup_temp = False
            else:
                audio_file_to_use = str(audio_path)
                cleanup_temp = False

            # If preprocessing produced a temporary file and language is still auto,
            # attempt a probe on the preprocessed audio (usually cleaner) to improve
            # probe-based language detection accuracy.
            try:
                if cleanup_temp and effective_language == 'auto':
                    try:
                        with open(audio_file_to_use, 'rb') as pf:
                            probe_params_local = {
                                "file": (Path(audio_file_to_use).name, pf, "audio/wav"),
                                "model": self.model,
                                "response_format": "verbose_json",
                                "temperature": 0.0,
                            }
                            try:
                                if self.circuit_breaker is not None and self.client is not None:
                                    probe_resp = self.circuit_breaker.call(lambda: self.client.audio.transcriptions.create(**probe_params_local))
                                elif self.client is not None:
                                    probe_resp = self.client.audio.transcriptions.create(**probe_params_local)
                                else:
                                    probe_resp = {}

                                probe_lang = getattr(probe_resp, 'language', None) or (probe_resp.get('language') if isinstance(probe_resp, dict) else None) or getattr(probe_resp, 'language_code', None) or (probe_resp.get('language_code') if isinstance(probe_resp, dict) else None)
                                probe_text = getattr(probe_resp, 'text', None) or (probe_resp.get('text') if isinstance(probe_resp, dict) else None)
                                if not probe_lang:
                                    import re
                                    arabic_re = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
                                    arabic_count = len(arabic_re.findall(probe_text or ""))
                                    latin_count = len(re.findall(r"[A-Za-z]", probe_text or ""))
                                    if arabic_count > latin_count and arabic_count > 0:
                                        probe_lang = 'ur'
                                    elif latin_count > arabic_count and latin_count > 0:
                                        probe_lang = 'en'

                                if probe_lang and probe_lang in STT_CONFIG['supported_languages']:
                                    effective_language = probe_lang
                                    logger.info(f"Probe-based language detection (preprocessed) result: {effective_language}")
                            except Exception:
                                logger.debug("Preprocessed probe failed; continuing with existing language setting")
                    except Exception:
                        pass
            except Exception:
                pass

            # Get audio duration for response
            audio_data, sample_rate = load_audio_file(audio_file_path)
            audio_duration = len(audio_data) / sample_rate

            logger.info(f"[STT] Transcribing: {Path(audio_file_path).name} (duration: {audio_duration:.2f}s)")
            logger.info(
                f"Transcribing audio: {audio_file_path} "
                f"(duration: {audio_duration:.2f}s, language: {effective_language})"
            )

            # Attempt transcription with retry logic
            transcribed_text = ""
            detected_language = effective_language
            max_retries = STT_CONFIG["max_retries"]
            retry_delay = STT_CONFIG["retry_delay"]

            for attempt in range(max_retries):
                try:
                    # Acquire semaphore to limit concurrent transcriptions
                    acquired = self._transcription_semaphore.acquire(timeout=STT_CONFIG.get("timeout", 10))
                    if not acquired:
                        raise STTServiceError("Unable to acquire transcription slot; too many concurrent requests")

                    try:
                        # Open audio file in binary mode
                        with open(audio_file_to_use, "rb") as audio_file:
                            # Prepare API request parameters
                            transcription_params = {
                                "file": (Path(audio_file_to_use).name, audio_file, "audio/wav"),
                                "model": self.model,
                                "response_format": "verbose_json",
                                "temperature": 0.0,  # 0 = more accurate, less hallucination
                            }

                            # Add language parameter if not auto-detect
                            if effective_language != "auto":
                                transcription_params["language"] = effective_language
                                logger.info(f"Forcing language: {effective_language}")

                                # Add prompt to help guide the model (more specific)
                                if effective_language == "en":
                                    transcription_params["prompt"] = "This is clear English speech. Common words: name, student, semester, university."
                                elif effective_language == "ur":
                                    transcription_params["prompt"] = "یہ واضح اردو تقریر ہے۔ عام الفاظ: نام، طالب علم، سمسٹر، یونیورسٹی۔"

                            # Call Groq Whisper API via circuit breaker if available
                            logger.debug(f"Sending request to Groq API (attempt {attempt + 1}/{max_retries})")

                            # Measure API call latency for monitoring
                            api_start = time.time()
                            if self.circuit_breaker is not None and self.client is not None:
                                try:
                                    transcription = self.circuit_breaker.call(
                                        lambda: self.client.audio.transcriptions.create(**transcription_params)
                                    )
                                    # record success for monitoring
                                    try:
                                        self.circuit_breaker.record_success()
                                    except Exception:
                                        pass
                                except Exception as cb_err:
                                    # Circuit breaker prevented the call or call failed
                                    logger.warning(f"Circuit breaker prevented/failed call: {cb_err}")
                                    raise
                            elif self.client is not None:
                                transcription = self.client.audio.transcriptions.create(**transcription_params)
                            else:
                                raise STTServiceError("STT client not initialized")
                            api_latency = time.time() - api_start
                            # Update moving average for API latency
                            calls = self.stats.get("api_calls", 0) + 1
                            prev_avg = float(self.stats.get("average_api_latency", 0.0) or 0.0)
                            new_avg = ((prev_avg * (calls - 1)) + api_latency) / calls
                            self.stats["api_calls"] = calls
                            self.stats["average_api_latency"] = new_avg
                            self.stats["last_api_latency"] = api_latency
                            logger.info(f"Groq API call latency: {api_latency:.3f}s (new avg: {new_avg:.3f}s)")

                            # Extract transcribed text
                            transcribed_text = getattr(transcription, 'text', None) or (transcription.get('text') if isinstance(transcription, dict) else '')
                            transcribed_text = (transcribed_text or "").strip()

                            # Extract detected language if available
                            detected_language = getattr(transcription, 'language', None) or (transcription.get('language') if isinstance(transcription, dict) else None) or detected_language

                            # Successful transcription
                            logger.info(f"[STT] Detected Language: {detected_language}")
                            logger.info(f"[STT] Transcript length: {len(transcribed_text)}")

                    finally:
                        # Always release semaphore
                        try:
                            self._transcription_semaphore.release()
                        except Exception:
                            pass

                    # Quality validation (Week 3 feature)
                    if ENHANCED_STT_CONFIG.get("enable_quality_validation", True):
                        try:
                            is_valid, err_msg, confidence = self._validate_transcription_quality(
                                transcribed_text, audio_duration, detected_language
                            )
                            if not is_valid:
                                logger.warning(f"Transcription quality check failed: {err_msg}")
                                if attempt == max_retries - 1:
                                    raise STTServiceError(f"Transcription failed quality checks: {err_msg}")
                                else:
                                    time.sleep(retry_delay)
                                    continue
                            else:
                                logger.info(f"Transcription passed quality checks (confidence={confidence:.2f})")
                                break
                        except Exception:
                            logger.exception("Quality validation raised an exception; accepting transcription")
                            break
                    else:
                        break

                except Exception as api_error:
                    logger.warning(f"API request failed (attempt {attempt + 1}/{max_retries}): {str(api_error)}")
                    if attempt == max_retries - 1:
                        raise STTServiceError(f"Transcription failed after {max_retries} attempts: {str(api_error)}")
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)

            # Cleanup temporary file if created
            if cleanup_temp:
                try:
                    import os
                    os.unlink(temp_path)
                    logger.debug("Cleaned up temporary preprocessed file")
                except Exception:
                    pass

            # Check if transcription is empty
            if not transcribed_text:
                logger.warning("Transcription returned empty text (possible silence or unclear audio)")
                return "", detected_language, audio_duration

            return transcribed_text, detected_language, audio_duration

        except STTServiceError:
            raise
        except Exception as e:
            error_msg = f"Failed to transcribe audio: {str(e)}"
            logger.error(error_msg)
            raise STTServiceError(error_msg) from e
    
    def transcribe_with_metadata(
        self,
        audio_file_path: str,
        language: str = "auto"
    ) -> dict:
        """
        Transcribe audio and return comprehensive metadata.
        
        This is a convenience method that wraps transcribe_audio and returns
        a structured dictionary with all transcription information.
        
        Args:
            audio_file_path: Path to the audio file to transcribe
            language: Language code for transcription
        
        Returns:
            Dictionary containing:
                - text: Transcribed text
                - language: Detected language code
                - duration: Audio duration in seconds
                - success: Whether transcription succeeded
                - timestamp: ISO format timestamp of transcription
                - confidence: Confidence score (if available)
        
        Raises:
            STTServiceError: If transcription fails
        """
        try:
            # Perform transcription
            text, detected_lang, duration = self.transcribe_audio(
                audio_file_path,
                language
            )
            
            # Determine success based on whether we got text
            success = bool(text)
            
            # Build metadata dictionary
            result = {
                "text": text,
                "language": detected_lang,
                "duration": round(duration, 2),
                "success": success,
                "timestamp": datetime.now().isoformat(),
                "confidence": None  # Groq API doesn't provide confidence scores
            }
            
            return result
            
        except Exception as e:
            error_msg = f"Failed to transcribe with metadata: {str(e)}"
            logger.error(error_msg)
            raise STTServiceError(error_msg) from e
    
    def _detect_language_smart(self, audio_data: np.ndarray, sample_rate: int) -> str:
        """
        Smart language detection based on audio characteristics.
        
        Analyzes audio energy patterns to predict language
        before sending to API, reducing unnecessary API calls.
        
        Args:
            audio_data: Audio data as numpy array
            sample_rate: Sample rate of the audio
        
        Returns:
            Predicted language code ('en', 'ur', or 'auto')
        """
        try:
            # Return auto for very short signals
            if len(audio_data) < sample_rate * 0.5:
                return "auto"

            # Compute short-time Fourier transform magnitude
            import librosa

            n_fft = 2048
            hop_length = 512
            S = np.abs(librosa.stft(audio_data, n_fft=n_fft, hop_length=hop_length))

            # Map FFT bins to frequencies
            freqs = librosa.fft_frequencies(sr=sample_rate, n_fft=n_fft)

            # Energy per frequency bin (sum over time frames)
            energy_per_bin = np.sum(S, axis=1)
            total_energy = np.sum(energy_per_bin) + 1e-12

            # Compute high-frequency energy ratio (above 2000 Hz)
            hf_threshold = 2000.0
            hf_mask = freqs >= hf_threshold
            hf_energy = np.sum(energy_per_bin[hf_mask])
            hf_ratio = hf_energy / total_energy

            # Compute spectral centroid as an additional signal
            centroid = np.mean(librosa.feature.spectral_centroid(S=S, sr=sample_rate))

            logger.debug(f"Language detect heuristic: hf_ratio={hf_ratio:.3f}, centroid={centroid:.1f}Hz")

            # Heuristic thresholds (tuned conservatively):
            # - If a significant portion of energy is in higher frequencies, favor 'ur'
            # - Otherwise, prefer 'en'
            if hf_ratio > 0.20 or centroid > 2000.0:
                self.stats['language_detections']['ur'] = self.stats['language_detections'].get('ur', 0) + 1
                return 'ur'
            else:
                self.stats['language_detections']['en'] = self.stats['language_detections'].get('en', 0) + 1
                return 'en'

        except Exception as e:
            logger.warning(f"Smart language detection failed: {e}, using auto")
            return "auto"
    
    def _validate_transcription_quality(
        self,
        transcription_text: str,
        audio_duration: float,
        detected_language: str
    ) -> Tuple[bool, Optional[str], float]:
        """
        Validate transcription quality and calculate confidence score.
        
        Ensures transcription meets quality standards
        before returning to user. Rejects low-quality results.
        
        Args:
            transcription_text: The transcribed text
            audio_duration: Duration of audio in seconds
            detected_language: Detected language code
        
        Returns:
            Tuple of (is_valid, error_message, confidence_score)
        """
        try:
            # Check if empty
            if not transcription_text or len(transcription_text.strip()) == 0:
                return False, "Empty transcription (possible silence)", 0.0
            
            # Check minimum length
            min_length = ENHANCED_STT_CONFIG["quality_validation"]["min_transcription_length"]
            if len(transcription_text) < min_length:
                return False, f"Transcription too short ({len(transcription_text)} chars, min {min_length})", 0.3
            
            # Check speech rate (words per second)
            words = transcription_text.split()
            speech_rate = len(words) / audio_duration if audio_duration > 0 else 0
            
            min_rate = ENHANCED_STT_CONFIG["quality_validation"]["min_speech_rate"]
            max_rate = ENHANCED_STT_CONFIG["quality_validation"]["max_speech_rate"]
            
            if speech_rate < min_rate:
                return False, f"Speech rate too low ({speech_rate:.1f} words/sec, min {min_rate})", 0.4
            
            if speech_rate > max_rate:
                return False, f"Speech rate too high ({speech_rate:.1f} words/sec, max {max_rate})", 0.5
            
            # Calculate confidence based on various factors
            confidence = 0.7  # Base confidence
            
            # Bonus for reasonable length
            if len(transcription_text) >= min_length * 2:
                confidence += 0.1
            
            # Bonus for good speech rate
            ideal_rate = (min_rate + max_rate) / 2
            rate_deviation = abs(speech_rate - ideal_rate) / ideal_rate
            if rate_deviation < 0.3:
                confidence += 0.1
            
            # Bonus for punctuation (indicates good quality)
            if any(p in transcription_text for p in ['.', '!', '?', ',']):
                confidence += 0.05
            
            # Cap at 0.95
            confidence = min(confidence, 0.95)
            
            return True, None, confidence
            
        except Exception as e:
            logger.warning(f"Quality validation failed: {e}, accepting transcription")
            return True, None, 0.6  # Default moderate confidence
    
    def validate_audio_file(self, audio_file_path: str) -> bool:
        """
        Validate that an audio file is suitable for transcription.
        
        This checks basic properties of the audio file to ensure it can be
        processed by the transcription service.
        
        Args:
            audio_file_path: Path to the audio file to validate
        
        Returns:
            True if file is valid, False otherwise
        """
        try:
            audio_path = Path(audio_file_path)
            
            # Check file exists
            if not audio_path.exists():
                logger.warning(f"Audio file does not exist: {audio_file_path}")
                return False
            
            # Check file is not empty
            if audio_path.stat().st_size == 0:
                logger.warning(f"Audio file is empty: {audio_file_path}")
                return False
            
            # Try to load the audio file
            try:
                audio_data, sample_rate = load_audio_file(audio_file_path)
                
                # Check duration is reasonable (at least 0.5 seconds)
                duration = len(audio_data) / sample_rate
                if duration < 0.5:
                    logger.warning(
                        f"Audio file is too short for transcription: {duration:.2f}s"
                    )
                    return False
                
                return True
                
            except Exception as load_error:
                logger.warning(f"Failed to load audio file: {str(load_error)}")
                return False
                
        except Exception as e:
            logger.error(f"Audio validation failed: {str(e)}")
            return False
    
    def transcribe_local(
        self,
        audio_file_path: str,
        language: str = "auto"
    ) -> Tuple[str, str, float]:
        """
        Transcribe audio using local Whisper model (offline fallback).
        
        This method uses OpenAI Whisper loaded locally, enabling transcription
        without internet connectivity. Used as fallback when Groq API is unavailable.
        
        Args:
            audio_file_path: Path to audio file
            language: Language code ('en', 'ur', or 'auto')
        
        Returns:
            Tuple of (transcription_text, detected_language, duration_seconds)
        
        Raises:
            TranscriptionError: If transcription fails
        """
        try:
            import whisper
            from pathlib import Path
            
            logger.info(f"Starting local Whisper transcription for: {audio_file_path}")
            start_time = time.time()
            
            # Load local Whisper model (cached after first load)
            if not hasattr(self, '_local_whisper_model'):
                model_size = ENHANCED_STT_CONFIG.get("local_whisper_model", "base")
                logger.info(f"Loading local Whisper model: {model_size}")
                self._local_whisper_model = whisper.load_model(model_size)
                logger.info("Local Whisper model loaded successfully")
            
            # Validate audio file
            audio_path = Path(audio_file_path)
            if not audio_path.exists():
                raise TranscriptionError(f"Audio file not found: {audio_file_path}")
            
            # Load and preprocess audio
            audio_data, sample_rate = load_audio_file(audio_file_path)
            duration = len(audio_data) / sample_rate
            
            # Check for silence
            if self._is_audio_silent(audio_data, sample_rate):
                raise SilenceDetectedError("Audio contains only silence")
            
            # Prepare transcription options
            transcribe_options = {
                "fp16": False,  # Use FP32 for better CPU compatibility
                "verbose": False
            }
            
            # Set language if not auto-detect
            if language and language != "auto":
                transcribe_options["language"] = language
            
            # Transcribe with local model
            result = self._local_whisper_model.transcribe(
                str(audio_path),
                **transcribe_options
            )
            
            # Extract results
            transcription_text = result.get("text", "").strip()
            detected_language = result.get("language", language if language != "auto" else "en")
            
            # Validate transcription
            if not transcription_text:
                raise EmptyTranscriptionError("Local Whisper returned empty transcription")
            
            # Calculate latency
            latency = time.time() - start_time
            
            # Update statistics
            self.stats["total_transcriptions"] += 1
            self.stats["successful_transcriptions"] += 1
            self.stats["language_detections"][detected_language] = \
                self.stats["language_detections"].get(detected_language, 0) + 1
            
            logger.info(
                f"Local Whisper transcription successful: "
                f"duration={duration:.2f}s, language={detected_language}, "
                f"latency={latency:.2f}s, text_length={len(transcription_text)}"
            )
            
            return transcription_text, detected_language, duration
            
        except (SilenceDetectedError, EmptyTranscriptionError):
            raise
        except ImportError as e:
            logger.error("Local Whisper not available - install openai-whisper package")
            raise TranscriptionError(
                "Local Whisper model not installed. Install with: pip install openai-whisper"
            )
        except Exception as e:
            self.stats["failed_transcriptions"] += 1
            logger.error(f"Local Whisper transcription failed: {e}", exc_info=True)
            raise TranscriptionError(f"Local transcription failed: {e}")
    
    def get_supported_languages(self) -> list:
        """
        Get list of supported language codes.
        
        Returns:
            List of language codes supported by the service
        """
        return STT_CONFIG["supported_languages"]
    
    def get_model_info(self) -> dict:
        """
        Get information about the current transcription model.
        
        Returns:
            Dictionary with model information
        """
        return {
            "model": self.model,
            "supported_languages": STT_CONFIG["supported_languages"],
            "max_retries": STT_CONFIG["max_retries"],
            "timeout": STT_CONFIG["timeout"]
        }
    
    def get_circuit_breaker_status(self) -> dict:
        """
        Get the current status of the circuit breaker (Week 3 feature).
        
        Returns:
            Dictionary with circuit breaker status
        """
        status = {
            "state": self.circuit_breaker.get_state(),
            "failure_count": self.circuit_breaker.failure_count,
            "success_count": self.circuit_breaker.success_count,
            "last_failure_time": str(self.circuit_breaker.last_failure_time) if self.circuit_breaker.last_failure_time else None,
            "recovery_timeout": self.circuit_breaker.timeout_seconds,
            # Monitoring metrics
            "api_calls": self.stats.get("api_calls", 0),
            "average_api_latency": self.stats.get("average_api_latency", 0.0),
            "last_api_latency": self.stats.get("last_api_latency")
        }
        return status

