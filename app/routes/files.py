import hashlib
import os
import tempfile
import uuid
import aiofiles
import magic
from datetime import datetime
from typing import List, Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from app.auth.auth import get_current_user

# MODIFIED: Added folder_collection to the import
from app.database import file_collection
from app.models.file import FileInDB

# ADDED: Import for the FolderInDB model
from app.models.user import UserInDB
from app.services.folder_service import check_folder_ownership
from app.services.telegram_service import telegram_service
from app.utils.exceptions import forbidden_exception, not_found_exception

router = APIRouter()
TEMP_DIR = "temp_uploads"
os.makedirs(TEMP_DIR, exist_ok=True)

# Define the file size limit in bytes
MAX_FILE_SIZE_BYTES = int(1.5 * 1024 * 1024 * 1024)


# Compute the hash of the uploaded file
def compute_file_hash(file_path: str) -> str:
    """Compute SHA256 hash of a file in chunks."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


# Upload file
@router.post("/upload", response_model=FileInDB)
async def upload_file(
    file: UploadFile = File(...),
    folder_id: Optional[str] = None,
    current_user: UserInDB = Depends(get_current_user),
):
    # Check file size
    if file.size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds the limit of {MAX_FILE_SIZE_BYTES / (1024**3):.1f} GB.",
        )

    # Verify folder ownership if folder_id is provided
    if folder_id:
        await check_folder_ownership(folder_id, current_user.id)

    # Temporary file path
    file_path = os.path.join(TEMP_DIR, f"{uuid.uuid4()}-{file.filename}")

    try:
        # Write file to disk and compute SHA256 hash in one pass
        hash_sha256 = hashlib.sha256()
        async with aiofiles.open(file_path, "wb") as out_file:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                await out_file.write(chunk)
                hash_sha256.update(chunk)
        file_hash = hash_sha256.hexdigest()

        # Duplicate check by hash
        existing_file = await file_collection.find_one(
            {"hash": file_hash, "owner_id": current_user.id}
        )
        if existing_file:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This file already exists in your storage (same content).",
            )

        # Detect MIME type
        actual_mime_type = magic.from_file(file_path, mime=True)
        actual_file_size = os.path.getsize(file_path)

        # Upload file to Telegram
        tg_response = await telegram_service.upload_file(
            file_path, file.filename, current_user.username
        )

        # Save metadata to DB
        file_metadata = FileInDB(
            name=file.filename,
            mime_type=actual_mime_type,
            hash=file_hash,
            size=actual_file_size,
            folder_id=folder_id,
            owner_id=current_user.id,
            tg_chat_id=tg_response["result"]["chat_id"],
            tg_message_id=tg_response["result"]["message_id"],
        )
        file_dict = file_metadata.model_dump(by_alias=True, exclude=["id"])
        result = await file_collection.insert_one(file_dict)
        created_file = await file_collection.find_one({"_id": result.inserted_id})

        return FileInDB(**created_file)

    finally:
        # Ensure temporary file is always removed
        if os.path.exists(file_path):
            os.remove(file_path)


# List files
@router.get("/", response_model=List[FileInDB])
async def list_files(
    folder_id: Optional[str] = Query(
        None, description="ID of the folder to list files from. Root if null."
    ),
    include_deleted: bool = False,
    is_starred: bool = False,
    current_user: UserInDB = Depends(get_current_user),
):
    query = {"owner_id": current_user.id}

    if include_deleted:
        # If including deleted, ignore folder_id filter to show all deleted
        query["is_deleted"] = True
    else:
        # Only filter by folder_id when not including deleted
        if folder_id == "root" or folder_id is None or folder_id == "":
            query["folder_id"] = None
        else:
            query["folder_id"] = folder_id
        query["is_deleted"] = False

    if is_starred:
        query["is_starred"] = True

    files = await file_collection.find(query).to_list(1000)
    return [FileInDB(**f) for f in files]


# Download file
@router.get("/{file_id}/download")
async def download_file(
    file_id: str, current_user: UserInDB = Depends(get_current_user)
):
    file_doc = await file_collection.find_one({"_id": ObjectId(file_id)})
    if not file_doc:
        raise not_found_exception("File not found")
    if file_doc["owner_id"] != current_user.id:
        raise forbidden_exception("You do not own this file")

    temp_file_path = os.path.join(
        tempfile.gettempdir(), f"{uuid.uuid4()}_{file_doc['name']}"
    )

    # Download file from Telegram
    await telegram_service.download_file(
        file_doc["tg_message_id"],
        temp_file_path,
        file_doc["name"],
        current_user.username,
    )

    # Generator to stream file in chunks safely
    def file_iterator(path, chunk_size=5 * 1024 * 1024):  # 5MB chunks
        try:
            with open(path, "rb") as f:
                while chunk := f.read(chunk_size):
                    yield chunk
        finally:
            if os.path.exists(path):
                os.remove(path)

    return StreamingResponse(
        file_iterator(temp_file_path),
        media_type=file_doc["mime_type"],
        headers={"Content-Disposition": f'attachment; filename="{file_doc["name"]}"'},
    )


# Move file to bin
@router.put("/{file_id}/bin")
async def move_file_to_bin(
    file_id: str, current_user: UserInDB = Depends(get_current_user)
):
    # Simple soft delete, just mark the flag
    await file_collection.update_one(
        {"_id": ObjectId(file_id), "owner_id": current_user.id},
        {"$set": {"is_deleted": True, "deleted_at": datetime.utcnow()}},
    )
    return {"message": "File moved to bin"}


# Restore file from bin
@router.put("/{file_id}/restore")
async def restore_file_from_bin(
    file_id: str, current_user: UserInDB = Depends(get_current_user)
):
    await file_collection.update_one(
        {"_id": ObjectId(file_id), "owner_id": current_user.id},
        {"$set": {"is_deleted": False, "deleted_at": None}},
    )
    return {"message": "File restored"}


@router.delete("/{file_id}")
async def permanently_delete_file(
    file_id: str, current_user: UserInDB = Depends(get_current_user)
):
    # Find the user's file document first
    file_doc = await file_collection.find_one(
        {"_id": ObjectId(file_id), "owner_id": current_user.id}
    )
    if not file_doc:
        raise not_found_exception("File not found or you do not have permission")

    message_id = file_doc.get("tg_message_id")

    # Attempt Telegram deletion first
    if message_id:
        try:
            await telegram_service.delete_messages([message_id])
        except Exception as e:
            return {"message": "Failed to delete file from Telegram. File not deleted."}

    # Only now delete the MongoDB document
    await file_collection.delete_one({"_id": ObjectId(file_id)})

    return {"message": "File permanently deleted"}
