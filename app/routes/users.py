from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.auth import get_current_user
from app.models.user import UserInDB
from app.database import file_collection

router = APIRouter()


class StorageUsage(BaseModel):
    """Pydantic model for the storage usage response."""

    total_usage_bytes: int


@router.get("/me/storage", response_model=StorageUsage)
async def get_user_storage_usage(current_user: UserInDB = Depends(get_current_user)):
    """
    Calculates the total storage space used by all of a user's files
    by querying the file_collection directly.
    """
    # Define an aggregation pipeline to sum the sizes of all files for a user.
    pipeline = [
        {
            # Match all documents belonging to the current user.
            "$match": {"owner_id": current_user.id}
        },
        {
            # Group the matched documents and calculate the sum of the 'size' field.
            "$group": {
                "_id": None,  # Group all matched documents into a single result
                "total_size": {"$sum": "$size"},
            }
        },
    ]

    # Execute the aggregation query on the file_collection.
    result = await file_collection.aggregate(pipeline).to_list(1)

    # If the user has files, the result will contain the total size. Otherwise, it's 0.
    total_usage = result[0]["total_size"] if result else 0

    return {"total_usage_bytes": total_usage}
