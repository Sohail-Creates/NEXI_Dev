"""
Audio Service API - Using PURE Resemblyzer

All audio processing uses Resemblyzer (your teammate's approach):
  Raw Audio → Validation → Preprocess → Resemblyzer Embedding → Return
  
Single source of truth: Resemblyzer VoiceEncoder
"""

import os
import tempfile
from typing import Optional
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import sys
import numpy as np

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.models import (
    APIResponse, ErrorCode, error_response, success_response, get_logger, setup_logging
)
from .audio_validation import AudioValidator, AudioValidationError

# Setup logging
setup_logging('INFO')
logger = get_logger('AudioService')

# Initialize app
app = FastAPI(title="Audio Service", version="2.0")

# Initialize validator only
audio_validator = AudioValidator()


@app.post("/process-voice")
async def process_voice(file: UploadFile = File(...)) -> APIResponse:
    """
    Process audio file using PURE Resemblyzer embedding extraction.
    
    Uses your teammate's proven approach:
    - Resemblyzer VoiceEncoder for embeddings
    - preprocess_wav for audio normalization
    - embed_utterance for 256D speaker embedding
    
    Expected:
    - WAV, MP3, or OGG audio file
    - 1-30 seconds duration
    - Non-silent content
    
    Returns:
    - embedding: 256D Resemblyzer speaker embedding
    - voice_detected: Boolean (from preprocessing)
    - quality_score: Float (RMS-based quality)
    - embedding_size: 256
    """
    
    trace_id = logger.generate_trace_id()
    
    try:
        # Step 1: Validate file
        logger.info("Starting Resemblyzer audio processing", trace_id=trace_id, filename=file.filename)
        
        if not file.filename:
            return error_response(
                code=ErrorCode.INVALID_INPUT,
                message="File must have a filename",
                trace_id=trace_id
            )
        
        # Step 2: Save temp file
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
                content = await file.read()
                tmp.write(content)
                temp_path = tmp.name
        except Exception as e:
            logger.error(f"Failed to save temp file: {str(e)}", error_code=ErrorCode.PROCESSING_FAILED)
            return error_response(
                code=ErrorCode.PROCESSING_FAILED,
                message="Failed to save uploaded file",
                details={"error": str(e)},
                trace_id=trace_id
            )
        
        try:
            # Step 3: Validate and load audio using librosa
            try:
                audio, sr = audio_validator.validate_and_load(temp_path)
                logger.info(f"Audio loaded: sr={sr}, duration={len(audio)/sr:.2f}s")
            except AudioValidationError as e:
                logger.error(f"Audio validation failed: {str(e)}", error_code=ErrorCode.INVALID_AUDIO)
                return error_response(
                    code=ErrorCode.INVALID_AUDIO,
                    message=str(e),
                    trace_id=trace_id
                )
            
            # Step 4: Calculate quality score (RMS-based, same as Resemblyzer preprocessor)
            try:
                rms = np.sqrt(np.mean(audio ** 2))
                # Normalize: 0.001 = 0%, 0.1 = 100%
                quality_score = min(1.0, max(0.0, (np.log10(rms + 1e-10) + 10) / 10))
                voice_detected = rms > 1e-6
                logger.info(f"Quality: {quality_score:.3f}, RMS: {rms:.6f}, Voice: {voice_detected}")
            except Exception as e:
                logger.error(f"Quality calculation failed: {str(e)}")
                quality_score = 0.0
                voice_detected = False
            
            # Step 5: Import and initialize Resemblyzer encoder
            try:
                from resemblyzer import VoiceEncoder, preprocess_wav
                logger.info("Resemblyzer imported successfully")
                
                # Initialize encoder
                encoder = VoiceEncoder()
                logger.info("VoiceEncoder initialized")
            except Exception as e:
                error_msg = f"Resemblyzer initialization failed: {str(e)}"
                logger.error(error_msg, error_code=ErrorCode.EXTRACTION_FAILED)
                return error_response(
                    code=ErrorCode.EXTRACTION_FAILED,
                    message=error_msg,
                    details={"error": str(e)},
                    trace_id=trace_id
                )
            
            # Step 6: Preprocess audio using Resemblyzer (resample to 16kHz for encoder compatibility)
            try:
                # Resample to 16kHz for Resemblyzer compatibility if needed
                if sr != 16000:
                    import librosa as lr
                    audio_16k = lr.resample(audio, orig_sr=sr, target_sr=16000)
                    logger.info(f"Resampled from {sr}Hz to 16kHz")
                else:
                    audio_16k = audio
                
                # Preprocess using Resemblyzer (handles normalization and framing)
                preprocessed = preprocess_wav(audio_16k, source_sr=16000)
                logger.info(f"Audio preprocessed: shape={preprocessed.shape}")
            except Exception as e:
                error_msg = f"Resemblyzer preprocessing failed: {str(e)}"
                logger.error(error_msg, error_code=ErrorCode.PROCESSING_FAILED)
                return error_response(
                    code=ErrorCode.PROCESSING_FAILED,
                    message=error_msg,
                    details={"error": str(e)},
                    trace_id=trace_id
                )
            
            # Step 7: Extract embedding using Resemblyzer
            try:
                embedding = encoder.embed_utterance(preprocessed)
                logger.info(f"Embedding extracted: shape={embedding.shape}, dtype={embedding.dtype}")
                
                # Validate embedding
                if embedding.shape != (256,):
                    raise ValueError(f"Expected embedding shape (256,), got {embedding.shape}")
                if not np.isfinite(embedding).all():
                    raise ValueError("Embedding contains NaN or Inf")
                    
            except Exception as e:
                error_msg = f"Resemblyzer embedding extraction failed: {str(e)}"
                logger.error(error_msg, error_code=ErrorCode.EXTRACTION_FAILED)
                return error_response(
                    code=ErrorCode.EXTRACTION_FAILED,
                    message=error_msg,
                    details={"error": str(e)},
                    trace_id=trace_id
                )
            
            # Step 8: Return success with Resemblyzer embedding
            response_data = {
                "embedding": embedding.tolist(),  # 256D Resemblyzer embedding
                "voice_detected": bool(voice_detected),
                "quality_score": float(quality_score),
                "embedding_size": 256,
                "metadata": {
                    "duration": float(len(audio) / sr),
                    "sample_rate": int(sr),
                    "model": "Resemblyzer",
                    "model_version": "0.1.4"
                }
            }
            
            logger.info("Resemblyzer audio processing completed successfully")
            return success_response(data=response_data, trace_id=trace_id)
        
        finally:
            # Clean up temp file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError as e:
                    logger.warning(f"Could not cleanup temp file {temp_path}: {e}")
    
    except Exception as e:
        logger.error(f"Unexpected error in process_voice: {str(e)}", error_code=ErrorCode.SERVICE_ERROR)
        return error_response(
            code=ErrorCode.SERVICE_ERROR,
            message="Internal service error",
            details={"error": str(e)},
            trace_id=trace_id
        )


@app.post("/verify-speaker")
async def verify_speaker(
    file: UploadFile = File(...),
    enrolled_embeddings: list = None
) -> APIResponse:
    """
    Verify if audio matches enrolled embeddings using cosine similarity.
    
    Args:
    - file: Audio to verify
    - enrolled_embeddings: List of previously enrolled embeddings
    
    Returns:
    - similarity: Cosine similarity score [0, 1]
    - match: True if similarity >= threshold (0.75)
    """
    
    trace_id = logger.generate_trace_id()
    
    try:
        if not enrolled_embeddings:
            return error_response(
                code=ErrorCode.INVALID_INPUT,
                message="enrolled_embeddings required",
                trace_id=trace_id
            )
        
        # Process audio (reuse process_voice logic)
        response = await process_voice(file)
        
        if not response.success:
            return response
        
        # Extract embeddings from response
        test_embeddings = response.data["embeddings"]
        
        # Calculate cosine similarity
        import numpy as np
        test_vec = np.array(test_embeddings)
        
        similarities = []
        for enrolled in enrolled_embeddings:
            enrolled_vec = np.array(enrolled)
            # Cosine similarity
            cos_sim = np.dot(test_vec, enrolled_vec) / (
                np.linalg.norm(test_vec) * np.linalg.norm(enrolled_vec) + 1e-8
            )
            similarities.append(cos_sim)
        
        best_similarity = max(similarities)
        threshold = 0.75
        is_match = best_similarity >= threshold
        
        return success_response(
            data={
                "similarity": float(best_similarity),
                "match": is_match,
                "threshold": threshold,
                "reason": "Match" if is_match else f"Similarity too low ({best_similarity:.3f} < {threshold})"
            },
            trace_id=trace_id
        )
    
    except Exception as e:
        logger.error(f"Verification failed: {str(e)}", error_code=ErrorCode.SERVICE_ERROR)
        return error_response(
            code=ErrorCode.SERVICE_ERROR,
            message="Verification failed",
            details={"error": str(e)},
            trace_id=trace_id
        )


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "audio-service", "version": "2.0"}


@app.get("/")
async def root():
    """Service info"""
    return {
        "service": "Audio Service",
        "version": "2.0",
        "status": "running",
        "description": "Audio processing with speaker embeddings",
        "endpoints": {
            "POST /process-voice": "Extract speaker embeddings from audio",
            "POST /verify-speaker": "Verify audio matches enrolled embeddings",
            "GET /health": "Health check"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002, reload=False)
