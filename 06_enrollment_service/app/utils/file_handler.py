import os
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
    
    # Read file content
    content = await file.read()
    
    # Validate file size
    if len(content) > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max size: {max_size} bytes"
        )
    
    # Generate unique filename
    file_ext = file.filename.split('.')[-1]
    unique_filename = f"{uuid.uuid4()}.{file_ext}"
    filepath = os.path.join(upload_dir, unique_filename)
    
    # Ensure directory exists
    os.makedirs(upload_dir, exist_ok=True)
    
    # Save file
    with open(filepath, 'wb') as f:
        f.write(content)
    
    return filepath