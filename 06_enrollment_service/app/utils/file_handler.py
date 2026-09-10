import os
from pathlib import Path
import uuid
from fastapi import UploadFile, HTTPException
from typing import Tuple

ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/jpg", "image/png"]
ALLOWED_AUDIO_TYPES = ["audio/wav", "audio/mpeg", "audio/mp3"]

async def save_uploaded_file(
    file: UploadFile, 
    upload_dir: str, 
    allowed_types: list,
    max_size: int
) -> str:

    # Validate file type
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid file type. Allowed: {allowed_types}"
        )
    
    # Starlette supplies the parsed part size without another full read.
    if file.size is not None and file.size > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size: {max_size} bytes"
        )
    content = await file.read(max_size + 1)
    if len(content) > max_size:
        raise HTTPException(status_code=413, detail=f"File too large. Max size: {max_size} bytes")
    
    # Generate unique filename
    extensions = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
                  "audio/wav": ".wav", "audio/mpeg": ".mp3", "audio/mp3": ".mp3"}
    file_ext = extensions[file.content_type]
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    filepath = str(Path(upload_dir).resolve() / unique_filename)
    
    # Ensure directory exists
    os.makedirs(upload_dir, exist_ok=True)
    
    # Save file
    with open(filepath, 'wb') as f:
        f.write(content)
    
    return filepath
