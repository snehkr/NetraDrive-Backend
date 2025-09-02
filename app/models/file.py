from datetime import datetime
import uuid
from pydantic import BaseModel, Field, HttpUrl
from typing import Literal, Optional
from bson import ObjectId
from .user import PyObjectId


class FileBase(BaseModel):
    name: str
    mime_type: str
    size: int
    folder_id: Optional[str] = None  # Files in root have no folder_id


class FileInDB(FileBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    hash: str
    owner_id: PyObjectId
    tg_chat_id: int
    tg_message_id: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_deleted: bool = False
    is_starred: bool = False
    deleted_at: Optional[datetime] = None

    class Config:
        json_encoders = {ObjectId: str}
        arbitrary_types_allowed = True


class URLUploadRequest(BaseModel):
    url: HttpUrl


class UploadJob(BaseModel):
    """
    Represents a background upload job in the database.
    """

    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    owner_id: PyObjectId
    status: Literal["pending", "processing", "completed", "failed"] = "pending"
    url: str
    file_id: Optional[PyObjectId] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Fields for download progress
    progress_percent: float = 0.0
    transferred_bytes: int = 0
    total_bytes: Optional[int] = None
    total_friendly: Optional[str] = None
    eta_seconds: Optional[float] = None
    eta_friendly: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class URLUploadResponse(BaseModel):
    """
    The initial response sent to the client after a job is accepted.
    """

    message: str
    job_id: str
