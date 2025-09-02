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
