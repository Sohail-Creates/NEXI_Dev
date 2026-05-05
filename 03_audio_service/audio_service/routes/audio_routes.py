"""
Audio recording API routes.
Handles all audio-related endpoints including recording, listing, and deletion.
"""

import logging
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from audio_service.models import (
    RecordRequest,
    RecordResponse,
    ErrorResponse,
    ListAudioResponse,
    AudioFileInfo,
    DeleteResponse
)
from audio_service.utils.audio_utils import (
    record_and_save_audio,
    list_audio_files,
    delete_audio_file,
    AudioRecorderError
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1",
    tags=["Audio"]
)


@router.post(
    "/record",
    response_model=RecordResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Audio recorded successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request parameters"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def record_audio_endpoint(request: RecordRequest):
    """
    Record audio from the system microphone and save to file.
    
    This endpoint captures real-time audio input using the default microphone
    and saves it as a WAV file with configurable parameters.
    
    Args:
        request: RecordRequest object containing recording parameters
        
    Returns:
        RecordResponse: Metadata about the recorded audio file
        
    Raises:
        HTTPException: If recording fails or parameters are invalid
    """
    try:
        logger.info(
            f"Recording request received: duration={request.duration}s, "
            f"sample_rate={request.sample_rate}Hz, channels={request.channels}"
        )
        
        # Record and save audio
        file_metadata = record_and_save_audio(
            duration=request.duration,
            sample_rate=request.sample_rate,
            channels=request.channels
        )
        
        # Prepare response
        response = RecordResponse(
            status="success",
            message="Audio recorded successfully",
            file_name=file_metadata["filename"],
            filepath=file_metadata["filepath"],
            duration=file_metadata["duration"],
            sample_rate=file_metadata["sample_rate"],
            channels=file_metadata["channels"],
            file_size=file_metadata["file_size"],
            timestamp=file_metadata["timestamp"]
        )
        
        logger.info(f"Audio recording successful: {file_metadata['filename']}")
        return response
        
    except ValueError as e:
        logger.error(f"Invalid recording parameters: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "status": "error",
                "message": str(e),
                "error_type": "ValidationError"
            }
        )
        
    except AudioRecorderError as e:
        logger.error(f"Audio recording failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": "Failed to record audio. Please check microphone availability.",
                "error_type": "AudioRecorderError"
            }
        )
        
    except Exception as e:
        logger.exception(f"Unexpected error during recording: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": "An unexpected error occurred",
                "error_type": "InternalServerError"
            }
        )


@router.get(
    "/list-audio",
    response_model=ListAudioResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Audio files retrieved successfully"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def list_audio_endpoint():
    """
    List all saved audio files.
    
    This endpoint retrieves metadata for all WAV files stored in the data directory.
    
    Returns:
        ListAudioResponse: List of audio files with their metadata
        
    Raises:
        HTTPException: If listing fails
    """
    try:
        logger.info("Listing audio files request received")
        
        # Get list of audio files
        audio_files = list_audio_files()
        
        # Convert to Pydantic models
        file_info_list = [
            AudioFileInfo(**file_data) for file_data in audio_files
        ]
        
        response = ListAudioResponse(
            status="success",
            count=len(file_info_list),
            files=file_info_list
        )
        
        logger.info(f"Listed {len(file_info_list)} audio files")
        return response
        
    except AudioRecorderError as e:
        logger.error(f"Failed to list audio files: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": "Failed to list audio files",
                "error_type": "AudioRecorderError"
            }
        )
        
    except Exception as e:
        logger.error(f"Unexpected error listing files: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": "An unexpected error occurred",
                "error_type": "InternalServerError"
            }
        )


@router.delete(
    "/delete-audio/{filename}",
    response_model=DeleteResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Audio file deleted successfully"},
        404: {"model": ErrorResponse, "description": "File not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def delete_audio_endpoint(filename: str):
    """
    Delete a specific audio file.
    
    This endpoint removes a WAV file from the data directory.
    
    Args:
        filename: Name of the audio file to delete
        
    Returns:
        DeleteResponse: Confirmation of deletion
        
    Raises:
        HTTPException: If file not found or deletion fails
    """
    try:
        logger.info(f"Delete request received for file: {filename}")
        
        # Delete the audio file
        delete_audio_file(filename)
        
        response = DeleteResponse(
            status="success",
            message="Audio file deleted successfully",
            filename=filename
        )
        
        logger.info(f"Audio file deleted: {filename}")
        return response
        
    except FileNotFoundError:
        logger.warning(f"File not found: {filename}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "status": "error",
                "message": f"Audio file not found: {filename}",
                "error_type": "FileNotFoundError"
            }
        )
        
    except AudioRecorderError as e:
        logger.error(f"Failed to delete audio file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": "Failed to delete audio file",
                "error_type": "AudioRecorderError"
            }
        )
        
    except Exception as e:
        logger.error(f"Unexpected error deleting file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "message": "An unexpected error occurred",
                "error_type": "InternalServerError"
            }
        )
