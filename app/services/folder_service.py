from datetime import datetime
from bson import ObjectId
from app.database import folder_collection, file_collection
from app.utils.exceptions import not_found_exception, forbidden_exception


# --- Function to get all nested children ---
async def get_all_nested_children(
    folder_id: str, owner_id: ObjectId
) -> tuple[list[str], list[str]]:
    """
    Recursively finds all subfolder IDs and file IDs within a given folder.

    Args:
        folder_id: The ID of the starting folder.
        owner_id: The ObjectId of the user who owns the folders.

    Returns:
        A tuple containing two lists: one for all subfolder IDs and one for all file IDs.
    """
    folder_ids_to_process = [ObjectId(folder_id)]
    all_subfolder_ids = []
    all_file_ids = []

    # Use a while loop to process folders iteratively, which is efficient for async operations
    while folder_ids_to_process:
        current_folder_id = folder_ids_to_process.pop(0)

        # Don't add the starting folder_id to the list of its own children
        if str(current_folder_id) != folder_id:
            all_subfolder_ids.append(str(current_folder_id))

        # Find subfolders of the current folder
        subfolders_cursor = folder_collection.find(
            {"parent_id": str(current_folder_id), "owner_id": owner_id}
        )
        async for folder in subfolders_cursor:
            folder_ids_to_process.append(folder["_id"])

        # Find files within the current folder
        files_cursor = file_collection.find(
            {"folder_id": str(current_folder_id), "owner_id": owner_id}
        )
        async for file in files_cursor:
            all_file_ids.append(str(file["_id"]))

    return all_subfolder_ids, all_file_ids


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
