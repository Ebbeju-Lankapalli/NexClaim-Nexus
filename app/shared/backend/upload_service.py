"""
NexClaim Upload Service.

Handles uploading files to Cloudinary for persistent storage.
"""

import logging
import uuid
import cloudinary
import cloudinary.uploader
from typing import Tuple, Optional
from fastapi import UploadFile

from app.shared.backend.config import settings

logger = logging.getLogger(__name__)

# Configure cloudinary if URL is present
if settings.CLOUDINARY_URL:
    cloudinary.config(url=settings.CLOUDINARY_URL)

class UploadService:
    @staticmethod
    async def upload_file(file: UploadFile, folder: str = "nexclaim") -> Tuple[Optional[str], Optional[str]]:
        """
        Uploads a FastAPI UploadFile to Cloudinary.
        Returns a tuple of (secure_url, public_id).
        If Cloudinary is not configured or fails, returns (None, None).
        """
        if not settings.CLOUDINARY_URL:
            logger.warning("CLOUDINARY_URL not set. Falling back to local storage.")
            
            # Read contents
            contents = await file.read()
            await file.seek(0)
            
            # Create local directory if it doesn't exist
            import os
            local_dir = os.path.join("app", "uploads", folder.split("/")[-1] if "/" in folder else folder)
            os.makedirs(local_dir, exist_ok=True)
            
            # Save file
            file_id = f"doc_{uuid.uuid4().hex[:8]}"
            ext = file.filename.split('.')[-1] if file.filename and '.' in file.filename else 'bin'
            local_path = os.path.join(local_dir, f"{file_id}.{ext}")
            
            with open(local_path, "wb") as f:
                f.write(contents)
                
            return local_path, file_id

        try:
            # Read file contents
            contents = await file.read()
            
            # Reset file pointer for any subsequent local operations if needed
            await file.seek(0)

            # Upload to Cloudinary
            logger.info("Uploading file to Cloudinary folder: %s", folder)
            response = cloudinary.uploader.upload(
                contents,
                folder=folder,
                resource_type="auto",  # Supports images and PDFs automatically
                public_id=f"doc_{uuid.uuid4().hex[:8]}"
            )
            
            return response.get("secure_url"), response.get("public_id")
        except Exception as e:
            logger.error("Cloudinary upload failed: %s", str(e))
            return None, None

upload_service = UploadService()
