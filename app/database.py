from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

client = AsyncIOMotorClient(settings.mongo_uri)
db = client[settings.db_name]

# Collections
user_collection = db["users"]
file_collection = db["files"]
folder_collection = db["folders"]
progress_collection = db["progress"]
upload_job_collection = db["upload_jobs"]
shared_link_collection = db["shared_links"]


# Indexes Initialization
async def init_indexes():
    """Create indexes to speed up queries."""
    # 1. Files: Frequent lookups by folder, owner, and hash (deduplication)
    await file_collection.create_index([("folder_id", 1), ("owner_id", 1)])
    await file_collection.create_index([("owner_id", 1), ("is_deleted", 1)])
    await file_collection.create_index("hash")

    # 2. Folders: Parent lookup and preventing duplicate names in same folder
    await folder_collection.create_index([("parent_id", 1), ("owner_id", 1)])
    await folder_collection.create_index([("owner_id", 1), ("is_deleted", 1)])
    # Unique constraint: No two folders with same name in the same parent folder
    await folder_collection.create_index(
        [("name", 1), ("parent_id", 1), ("owner_id", 1)],
        unique=True,
        partialFilterExpression={"is_deleted": False},
    )

    # 3. Users: Ensure usernames are unique
    await user_collection.create_index("username", unique=True)

    # 4. Shared Links: Fast lookups by file_id
    await shared_link_collection.create_index("file_id")

    print("Database indexes initialized.")
