import tempfile
import uuid
import os
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from bson import ObjectId
from app.auth.auth import get_current_user
from app.models.file import FileInDB
from app.models.folder import FolderInDB
from app.models.user import UserInDB
from app.database import file_collection, folder_collection
from app.services.folder_service import propagate_size_change
from app.services.folder_service import get_all_nested_children
from app.services.telegram_service import telegram_service
from app.utils.exceptions import (
    not_found_exception,
    http_exception,
)

router = APIRouter()
TEMP_PREVIEW_DIR = "temp_previews"


class RenameRequest(BaseModel):
    new_name: str


class MoveRequest(BaseModel):
    new_parent_id: str | None = None


# Search files and folders
@router.get("/files/search/")
async def search_files_and_folders(
    q: str, current_user: UserInDB = Depends(get_current_user)
):
    # Search folders
    folders_cursor = folder_collection.find(
        {
            "owner_id": current_user.id,
            "is_deleted": False,
            "name": {"$regex": q, "$options": "i"},
        }
    )
    folders = await folders_cursor.to_list(None)

    # Search files
    files_cursor = file_collection.find(
        {
            "owner_id": current_user.id,
            "is_deleted": False,
            "name": {"$regex": q, "$options": "i"},
        }
    )
    files = await files_cursor.to_list(None)

    return {
        "folders": [FolderInDB(**f) for f in folders],
        "files": [FileInDB(**f) for f in files],
    }


@router.put("/{item_type}/{item_id}/rename")
async def rename_item(
    item_type: str,
    item_id: str,
    request: RenameRequest,
    current_user: UserInDB = Depends(get_current_user),
):
    collection = folder_collection if item_type == "folder" else file_collection
    field_to_update = "name"

    item = await collection.find_one(
        {"_id": ObjectId(item_id), "owner_id": current_user.id}
    )
    if not item:
        raise not_found_exception(f"{item_type.capitalize()} not found.")

    await collection.update_one(
        {"_id": ObjectId(item_id)}, {"$set": {field_to_update: request.new_name}}
    )

    # If it's a file, also update the caption in Telegram for consistency
    if item_type == "file":
        await telegram_service.edit_message_caption(
            item["tg_message_id"], request.new_name
        )

    return {"message": f"{item_type.capitalize()} renamed successfully."}


@router.put("/{item_type}/{item_id}/move")
async def move_item(
    item_type: str,
    item_id: str,
    request: MoveRequest,
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Moves a file or folder to a new parent folder (or to the root).
    Includes checks to prevent invalid moves and updates folder sizes.
    """
    collection = folder_collection if item_type == "folder" else file_collection
    field_to_update = "parent_id" if item_type == "folder" else "folder_id"

    # 1. Check if the item to be moved exists and belongs to the user
    item_to_move = await collection.find_one(
        {"_id": ObjectId(item_id), "owner_id": current_user.id}
    )
    if not item_to_move:
        raise not_found_exception(f"{item_type.capitalize()} not found.")

    # Capture the old parent ID before we change it
    old_parent_id = (
        item_to_move.get("parent_id")
        if item_type == "folder"
        else item_to_move.get("folder_id")
    )
    target_parent_id = request.new_parent_id

    # 2. Handle moving to a specific folder
    if target_parent_id:
        # 2a. Check if the target folder exists and belongs to the user
        target_folder = await folder_collection.find_one(
            {"_id": ObjectId(target_parent_id), "owner_id": current_user.id}
        )
        if not target_folder:
            raise not_found_exception("Target folder not found.")

        # 2b. CRITICAL: Prevent circular moves for folders
        if item_type == "folder":
            if item_id == target_parent_id:
                raise http_exception(400, "Cannot move a folder into itself.")

            # Get all sub-folders of the folder being moved
            subfolder_ids, _ = await get_all_nested_children(item_id, current_user.id)
            if target_parent_id in subfolder_ids:
                raise http_exception(
                    400, "Cannot move a folder into one of its own sub-folders."
                )

    # 3. Perform the update
    await collection.update_one(
        {"_id": ObjectId(item_id)}, {"$set": {field_to_update: target_parent_id}}
    )

    # 4. Fix Folder Sizes (Only if moving a FILE)
    # We must subtract size from the old folder and add it to the new folder
    if item_type == "file":
        file_size = item_to_move.get("size", 0)

        # Subtract from old folder (if it wasn't root)
        if old_parent_id:
            await propagate_size_change(old_parent_id, -file_size, current_user.id)

        # Add to new folder (if it's not root)
        if target_parent_id:
            await propagate_size_change(target_parent_id, file_size, current_user.id)

    return {"message": f"{item_type.capitalize()} moved successfully."}


# Preview a file
@router.get("/files/{file_id}/preview")
async def preview_file(
    file_id: str, current_user: UserInDB = Depends(get_current_user)
):
    # Fetch file metadata
    file_doc = await file_collection.find_one(
        {"_id": ObjectId(file_id), "owner_id": current_user.id}
    )
    if not file_doc:
        raise not_found_exception("File not found.")

    # Generator to stream the file safely
    async def file_iterator(chunk_size: int = 1024 * 1024):
        temp_path = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4()}.tmp")

        try:
            # Download Telegram media to temp file
            await telegram_service.download_file_for_preview(
                file_doc["tg_message_id"],
                dest_path=temp_path,
                user_id=current_user.username,
            )

            # Stream file in chunks
            with open(temp_path, "rb") as f:
                while chunk := f.read(chunk_size):
                    yield chunk
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)

    headers = {"Content-Disposition": f'inline; filename="{file_doc["name"]}"'}
    return StreamingResponse(
        file_iterator(), media_type=file_doc["mime_type"], headers=headers
    )


#  Helper function to toggle the star status
async def _toggle_star_status(
    item_type: str, item_id: str, star_status: bool, current_user: UserInDB
):
    collection = folder_collection if item_type == "folder" else file_collection

    # Find the item to ensure it exists and belongs to the user
    item = await collection.find_one(
        {"_id": ObjectId(item_id), "owner_id": current_user.id}
    )
    if not item:
        raise not_found_exception(f"{item_type.capitalize()} not found.")

    # Update the is_starred field in the database
    await collection.update_one(
        {"_id": ObjectId(item_id)}, {"$set": {"is_starred": star_status}}
    )
    action = "starred" if star_status else "unstarred"
    return {"message": f"{item_type.capitalize()} {action} successfully."}


#  Endpoint to Star an Item
@router.put("/{item_type}s/{item_id}/star")
async def star_item(
    item_type: str, item_id: str, current_user: UserInDB = Depends(get_current_user)
):
    return await _toggle_star_status(item_type, item_id, True, current_user)


#  Endpoint to Unstar an Item
@router.put("/{item_type}s/{item_id}/unstar")
async def unstar_item(
    item_type: str, item_id: str, current_user: UserInDB = Depends(get_current_user)
):
    return await _toggle_star_status(item_type, item_id, False, current_user)
