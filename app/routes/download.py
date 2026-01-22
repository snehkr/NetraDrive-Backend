import hashlib
import time
import uuid
import os
import aiofiles
import httpx
import magic
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from urllib.parse import urlparse
from app.services.folder_service import propagate_size_change
from app.utils.format_utils import format_bytes, format_eta
from app.auth.auth import get_current_user
from app.models.file import FileInDB, URLUploadRequest, UploadJob, URLUploadResponse
from app.models.user import UserInDB
from app.database import file_collection, upload_job_collection
from app.services.telegram_service import telegram_service

router = APIRouter()
TEMP_DOWNLOAD_DIR = "temp_downloads"
os.makedirs(TEMP_DOWNLOAD_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# The Core Background Worker Function (Simplified)
# ---------------------------------------------------------------------------
async def process_url_download(
    url: str, job_id: str, owner_id: str, username: str, folder_id: Optional[str] = None
):
    """
    Downloads a file in the background, updating the DB with download progress.
    """
    try:
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path) or f"{uuid.uuid4()}.file"
    except Exception:
        filename = f"{uuid.uuid4()}.file"

    file_path = os.path.join(TEMP_DOWNLOAD_DIR, f"{uuid.uuid4()}-{filename}")

    try:
        # --- Download Phase with Progress Tracking ---
        hash_sha256 = hashlib.sha256()
        downloaded_bytes = 0
        last_update_time = time.time()
        start_time = last_update_time

        async with httpx.AsyncClient(follow_redirects=True, timeout=300.0) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("Content-Length", 0))

                async with aiofiles.open(file_path, "wb") as out_file:
                    async for chunk in response.aiter_bytes():
                        await out_file.write(chunk)
                        hash_sha256.update(chunk)
                        downloaded_bytes += len(chunk)

                        # --- Progress Calculation and DB Update (once per second) ---
                        current_time = time.time()
                        if current_time - last_update_time >= 1:
                            elapsed_time = current_time - start_time
                            speed_bps = (
                                downloaded_bytes / elapsed_time
                                if elapsed_time > 0
                                else 0
                            )
                            eta_seconds = (
                                ((total_size - downloaded_bytes) / speed_bps)
                                if speed_bps > 0
                                else None
                            )

                            progress_data = {
                                "status": "downloading",
                                "transferred_bytes": downloaded_bytes,
                                "total_bytes": total_size,
                                "total_friendly": (
                                    format_bytes(total_size) if total_size else None
                                ),
                                "progress_percent": (
                                    (downloaded_bytes / total_size * 100)
                                    if total_size
                                    else 0
                                ),
                                "eta_seconds": (
                                    round(eta_seconds)
                                    if eta_seconds is not None
                                    else None
                                ),
                                "eta_friendly": (
                                    format_eta(eta_seconds)
                                    if eta_seconds is not None
                                    else None
                                ),
                                "updated_at": datetime.utcnow(),
                            }
                            await upload_job_collection.update_one(
                                {"job_id": job_id}, {"$set": progress_data}
                            )
                            last_update_time = current_time

        # --- Post-Download Processing ---
        await upload_job_collection.update_one(
            {"job_id": job_id},
            {"$set": {"status": "processing", "progress_percent": 100}},
        )

        file_hash = hash_sha256.hexdigest()
        existing_file = await file_collection.find_one(
            {"hash": file_hash, "owner_id": owner_id}
        )
        if existing_file:
            raise ValueError("Duplicate file content already exists in your storage.")

        actual_mime_type = magic.from_file(file_path, mime=True)
        actual_file_size = os.path.getsize(file_path)

        tg_response = await telegram_service.upload_file(file_path, filename, username)

        file_metadata = FileInDB(
            name=filename,
            mime_type=actual_mime_type,
            hash=file_hash,
            size=actual_file_size,
            folder_id=folder_id,
            owner_id=owner_id,
            tg_chat_id=tg_response["result"]["chat_id"],
            tg_message_id=tg_response["result"]["message_id"],
        )
        file_dict = file_metadata.model_dump(by_alias=True, exclude=["id"])
        result = await file_collection.insert_one(file_dict)

        # Propagate size change to parent folders
        if folder_id:
            await propagate_size_change(folder_id, actual_file_size, owner_id)

        await upload_job_collection.update_one(
            {"job_id": job_id},
            {"$set": {"status": "completed", "file_id": result.inserted_id}},
        )

    except Exception as e:
        await upload_job_collection.update_one(
            {"job_id": job_id}, {"$set": {"status": "failed", "error_message": str(e)}}
        )

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


# ---------------------------------------------------------------------------
# API Endpoints (No WebSocket or Cancel Endpoint)
# ---------------------------------------------------------------------------


# URL Upload
@router.post(
    "/upload/from-url",
    response_model=URLUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_from_url(
    request: URLUploadRequest,
    background_tasks: BackgroundTasks,
    folder_id: Optional[str] = None,
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Accepts a URL and initiates a background download process.
    """
    job = UploadJob(owner_id=current_user.id, url=str(request.url))
    await upload_job_collection.insert_one(
        job.model_dump(by_alias=True, exclude=["id"])
    )

    background_tasks.add_task(
        process_url_download,
        url=str(request.url),
        job_id=job.job_id,
        owner_id=current_user.id,
        username=current_user.username,
        folder_id=folder_id,
    )

    return URLUploadResponse(
        message="File download accepted and is being processed in the background.",
        job_id=job.job_id,
    )


# Get Upload Status
@router.get("/upload/status/{job_id}", response_model=UploadJob)
async def get_upload_status(
    job_id: str,
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Retrieves the status and download progress of a background job.
    """
    job = await upload_job_collection.find_one({"job_id": job_id})
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found."
        )
    if job["owner_id"] != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this job.",
        )
    return job
