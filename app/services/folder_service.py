from datetime import datetime
from typing import Optional
from bson import ObjectId
from app.database import folder_collection, file_collection
from app.utils.exceptions import not_found_exception, forbidden_exception


# --- Function to get all nested children (folders and files) ---
async def get_all_nested_children(
    folder_id: str, owner_id: ObjectId
) -> tuple[list[str], list[str]]:
    """
    Optimized version using MongoDB $graphLookup.
    """
    pipeline = [
        {"$match": {"_id": ObjectId(folder_id), "owner_id": owner_id}},
        {
            "$graphLookup": {
                "from": "folders",
                "startWith": "$_id",
                "connectFromField": "_id",
                "connectToField": "parent_id",
                "as": "descendants",
                "restrictSearchWithMatch": {"owner_id": owner_id},
            }
        },
    ]

    result = await folder_collection.aggregate(pipeline).to_list(1)

    if not result:
        return [], []

    # Extract all folder IDs (the root + all descendants)
    folder_ids = [str(result[0]["_id"])]
    folder_ids.extend([str(f["_id"]) for f in result[0]["descendants"]])

    # Prepare list of subfolder IDs (excluding the root folder)
    subfolder_ids = [fid for fid in folder_ids if fid != folder_id]

    # Fetch all files that are in ANY of these folders
    files = await file_collection.find(
        {"folder_id": {"$in": folder_ids}, "owner_id": owner_id}, projection={"_id": 1}
    ).to_list(None)

    file_ids = [str(f["_id"]) for f in files]

    return subfolder_ids, file_ids


# --- Function to check folder ownership ---
async def check_folder_ownership(folder_id: str, owner_id: ObjectId):
    folder = await folder_collection.find_one({"_id": ObjectId(folder_id)})
    if not folder:
        raise not_found_exception("Folder not found")
    if folder["owner_id"] != owner_id:
        raise forbidden_exception("You do not own this folder")
    return folder


# --- Function to update the deleted status of items ---
async def update_item_deleted_status(
    collection, item_ids: list[str], owner_id: ObjectId, is_deleted: bool
):
    if not item_ids:
        return

    object_ids = [ObjectId(id_str) for id_str in item_ids]
    update_data = {
        "$set": {
            "is_deleted": is_deleted,
            "deleted_at": datetime.utcnow() if is_deleted else None,
        }
    }
    await collection.update_many(
        {"_id": {"$in": object_ids}, "owner_id": owner_id}, update_data
    )


# --- Function to calculate the total size of a folder ---
async def calculate_folder_size(folder_id: str, owner_id: ObjectId) -> int:
    """
    Calculates the total size of all files within a folder and its subfolders
    using a highly efficient single aggregation query.
    """
    # Use $graphLookup to find all descendant folders in a single query
    folder_tree_pipeline = [
        {"$match": {"_id": ObjectId(folder_id), "owner_id": owner_id}},
        {
            "$graphLookup": {
                "from": "folders",
                "startWith": "$_id",
                "connectFromField": "_id",
                "connectToField": "parent_id",
                "as": "descendants",
                "restrictSearchWithMatch": {"owner_id": owner_id},
            }
        },
    ]
    result = await folder_collection.aggregate(folder_tree_pipeline).to_list(1)

    if not result:
        return 0

    # Collect all folder IDs from the tree (the starting folder + all its children)
    main_folder = result[0]
    all_folder_ids_in_tree = [main_folder["_id"]] + [
        desc["_id"] for desc in main_folder["descendants"]
    ]

    # Find all files that belong to any of these folders
    all_file_docs = await file_collection.find(
        {"folder_id": {"$in": [str(fid) for fid in all_folder_ids_in_tree]}}
    ).to_list(None)

    if not all_file_docs:
        return 0

    total_size = 0
    storage_ids_to_lookup = []

    # Separate legacy files from new files (same logic as before)
    for doc in all_file_docs:
        if "storage_object_id" in doc:
            storage_ids_to_lookup.append(doc["storage_object_id"])
        elif "size" in doc:
            total_size += doc["size"]

    return total_size


async def propagate_size_change(
    folder_id: Optional[str], size_delta: int, owner_id: str
):
    """
    Recursively updates the size of a folder and all its parents.
    """
    if not folder_id or size_delta == 0:
        return

    current_folder_id = folder_id

    # Traverse up the tree until we hit the root
    while current_folder_id:
        # Update the current folder's size
        await folder_collection.update_one(
            {"_id": ObjectId(current_folder_id), "owner_id": owner_id},
            {"$inc": {"size": size_delta}},
        )

        # Get parent ID to continue traversal
        folder = await folder_collection.find_one(
            {"_id": ObjectId(current_folder_id)}, {"parent_id": 1}
        )

        if not folder:
            break

        current_folder_id = folder.get("parent_id")
