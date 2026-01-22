import asyncio
from typing import List, Optional
from fastapi import HTTPException, status
from pymongo.collation import Collation

from bson import ObjectId
from fastapi import APIRouter, Depends, Query

from app.auth.auth import get_current_user
from app.database import file_collection, folder_collection
from app.models.folder import FolderCreate, FolderInDB, FolderTree, Breadcrumb
from app.models.user import UserInDB
from app.services.folder_service import (
    check_folder_ownership,
    get_all_nested_children,
    update_item_deleted_status,
)
from app.services.telegram_service import telegram_service

router = APIRouter()


# Create a new folder
@router.post("/", response_model=FolderInDB)
async def create_folder(
    folder_data: FolderCreate, current_user: UserInDB = Depends(get_current_user)
):
    # Ensure parent folder exists and is owned by the user
    if folder_data.parent_id:
        await check_folder_ownership(folder_data.parent_id, current_user.id)

    # Case-insensitive duplicate check
    existing_folder = await folder_collection.find_one(
        {
            "name": folder_data.name,
            "parent_id": folder_data.parent_id,
            "owner_id": current_user.id,
        },
        collation=Collation(locale="en", strength=2),
    )

    if existing_folder:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A folder with the same name already exists in this location.",
        )

    # Create new folder
    folder = FolderInDB(
        name=folder_data.name,
        parent_id=folder_data.parent_id,
        owner_id=current_user.id,
    )
    folder_dict = folder.model_dump(by_alias=True, exclude=["id"])
    result = await folder_collection.insert_one(folder_dict)
    created_folder = await folder_collection.find_one({"_id": result.inserted_id})
    return FolderInDB(**created_folder)


# List all folders
@router.get("/", response_model=List[FolderInDB])
async def list_folders(
    parent_id: Optional[str] = Query(
        None, description="ID of the parent folder to list contents of. Root if null."
    ),
    include_deleted: bool = False,
    is_starred: bool = False,
    current_user: UserInDB = Depends(get_current_user),
):

    query = {"owner_id": current_user.id}

    if include_deleted:
        # If including deleted, ignore parent_id filter to show all deleted
        query["is_deleted"] = True
    else:
        # Only filter by parent_id when not including deleted
        if parent_id == "root" or parent_id is None or parent_id == "":
            query["parent_id"] = None
        else:
            query["parent_id"] = parent_id
        query["is_deleted"] = False

    if is_starred:
        query["is_starred"] = True

    folders = await folder_collection.find(query).to_list(1000)

    return folders


# Get the folder tree structure
@router.get("/tree", response_model=List[FolderTree])
async def get_folder_tree(current_user: UserInDB = Depends(get_current_user)):
    """
    Retrieves all non-deleted folders for the current user and structures them
    into a nested tree hierarchy.
    """
    folders_cursor = folder_collection.find(
        {"owner_id": current_user.id, "is_deleted": False}
    )
    all_folders = await folders_cursor.to_list(None)

    folder_map = {}
    for folder in all_folders:
        folder["_id"] = str(folder["_id"])
        folder_id_str = folder["_id"]

        folder_map[folder_id_str] = folder
        folder_map[folder_id_str]["children"] = []

    root_folders = []
    for folder_id, folder in folder_map.items():
        parent_id = folder.get("parent_id")
        if parent_id and parent_id in folder_map:
            parent_folder = folder_map[parent_id]
            parent_folder["children"].append(folder)
        else:
            root_folders.append(folder)

    return root_folders


# Get the breadcrumb path for a specific folder
@router.get("/{folder_id}/path", response_model=List[Breadcrumb])
async def get_folder_path(
    folder_id: str, current_user: UserInDB = Depends(get_current_user)
):
    """
    Given a folder ID, traverses up the hierarchy to its root
    and returns the complete breadcrumb path.
    """
    path: List[Breadcrumb] = []
    current_folder_id: Optional[str] = folder_id

    while current_folder_id:
        folder = await folder_collection.find_one(
            {"_id": ObjectId(current_folder_id), "owner_id": current_user.id}
        )

        if not folder:
            raise HTTPException(
                status_code=404,
                detail=f"Folder with ID '{current_folder_id}' not found.",
            )

        path.insert(0, Breadcrumb(id=str(folder["_id"]), name=folder["name"]))

        current_folder_id = folder.get("parent_id")

    return path


# Move folder to bin
@router.put("/{folder_id}/bin")
async def move_folder_to_bin(
    folder_id: str, current_user: UserInDB = Depends(get_current_user)
):
    await check_folder_ownership(folder_id, current_user.id)

    # Recursively find all children
    subfolder_ids, file_ids = await get_all_nested_children(folder_id, current_user.id)

    # Mark main folder, all sub-folders, and all files as deleted
    await update_item_deleted_status(
        folder_collection, [folder_id] + subfolder_ids, current_user.id, True
    )
    await update_item_deleted_status(file_collection, file_ids, current_user.id, True)

    return {"message": "Folder and its contents moved to bin"}


# Restore folder from bin
@router.put("/{folder_id}/restore")
async def restore_folder_from_bin(
    folder_id: str, current_user: UserInDB = Depends(get_current_user)
):
    await check_folder_ownership(folder_id, current_user.id)

    # Recursively find all children
    subfolder_ids, file_ids = await get_all_nested_children(folder_id, current_user.id)

    # Restore main folder, all sub-folders, and all files
    await update_item_deleted_status(
        folder_collection, [folder_id] + subfolder_ids, current_user.id, False
    )
    await update_item_deleted_status(file_collection, file_ids, current_user.id, False)

    return {"message": "Folder and its contents restored"}


# Permanently delete folder
@router.delete("/{folder_id}")
async def permanently_delete_folder(
    folder_id: str, current_user: UserInDB = Depends(get_current_user)
):
    await check_folder_ownership(folder_id, current_user.id)

    subfolder_ids, file_ids = await get_all_nested_children(folder_id, current_user.id)

    # Collect Telegram message IDs
    files_to_delete = await file_collection.find(
        {
            "_id": {"$in": [ObjectId(fid) for fid in file_ids]},
            "owner_id": current_user.id,
        }
    ).to_list(None)

    message_ids = [f["tg_message_id"] for f in files_to_delete]

    # Delete from Telegram
    if message_ids:
        await telegram_service.delete_messages(message_ids)

    # Delete from DB
    if file_ids:
        await file_collection.delete_many(
            {"_id": {"$in": [ObjectId(fid) for fid in file_ids]}}
        )

    all_folder_ids_to_delete = [ObjectId(folder_id)] + [
        ObjectId(sid) for sid in subfolder_ids
    ]
    await folder_collection.delete_many({"_id": {"$in": all_folder_ids_to_delete}})

    return {"message": "Folder and its contents permanently deleted"}
