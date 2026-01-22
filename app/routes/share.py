# app/routes/share.py
import uuid
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse
from bson import ObjectId

from app.auth.auth import get_current_user
from app.database import file_collection, shared_link_collection
from app.models.user import UserInDB
from app.models.shared_link import SharedLinkInDB
from app.services.telegram_service import telegram_service
from app.utils.exceptions import not_found_exception, forbidden_exception

router = APIRouter()


# --- Authenticated: Create a Share Link ---
@router.post("/generate/{file_id}", response_model=SharedLinkInDB)
async def generate_share_link(
    file_id: str, current_user: UserInDB = Depends(get_current_user)
):
    # Check ownership
    file_doc = await file_collection.find_one(
        {"_id": ObjectId(file_id), "owner_id": current_user.id}
    )
    if not file_doc:
        raise not_found_exception("File not found")

    # Check if link already exists
    existing = await shared_link_collection.find_one({"file_id": file_id})
    if existing:
        return SharedLinkInDB(**existing)

    # Create new link
    link_id = str(uuid.uuid4())[:8]  # Short UUID
    new_link = SharedLinkInDB(_id=link_id, file_id=file_id, owner_id=current_user.id)

    await shared_link_collection.insert_one(new_link.model_dump(by_alias=True))
    return new_link


# --- Public: Access Shared File (Supports Streaming!) ---
@router.get("/{link_id}")
async def access_shared_file(link_id: str, request: Request):
    # 1. Lookup Link
    link_doc = await shared_link_collection.find_one({"_id": link_id})
    if not link_doc or not link_doc["is_active"]:
        raise not_found_exception("Link not found or expired")

    # 2. Increment Views (optional, background task is better but this is simple)
    await shared_link_collection.update_one({"_id": link_id}, {"$inc": {"views": 1}})

    # 3. Lookup File (Bypass Owner Check)
    file_doc = await file_collection.find_one({"_id": ObjectId(link_doc["file_id"])})
    if not file_doc:
        raise not_found_exception("Original file has been deleted")

    # 4. Reuse Streaming Logic (Copy-Paste from files.py or refactor into a util)
    file_size = file_doc["size"]
    range_header = request.headers.get("range")
    start_byte = 0
    end_byte = file_size - 1
    status_code = 200

    if range_header:
        try:
            unit, ranges = range_header.split("=")
            if unit == "bytes":
                start_str, end_str = ranges.split("-")
                start_byte = int(start_str) if start_str else 0
                end_byte = int(end_str) if end_str else file_size - 1
                if start_byte >= file_size:
                    return Response(
                        status_code=416,
                        headers={"Content-Range": f"bytes */{file_size}"},
                    )
                status_code = 206
        except:
            pass

    content_length = end_byte - start_byte + 1
    headers = {
        "Content-Disposition": f'inline; filename="{file_doc["name"]}"',
        "Content-Length": str(content_length),
        "Content-Range": f"bytes {start_byte}-{end_byte}/{file_size}",
        "Accept-Ranges": "bytes",
    }

    return StreamingResponse(
        telegram_service.stream_file(
            file_doc["tg_message_id"], file_size, start_byte, end_byte
        ),
        status_code=status_code,
        media_type=file_doc["mime_type"],
        headers=headers,
    )
