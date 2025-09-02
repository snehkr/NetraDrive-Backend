from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional
from bson import ObjectId
from .user import PyObjectId


class FolderBase(BaseModel):
    name: str
    parent_id: Optional[str] = None


class FolderCreate(FolderBase):
    pass


class FolderInDB(FolderBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    size: Optional[int] = 0
    owner_id: PyObjectId
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_deleted: bool = False
    is_starred: bool = False
    deleted_at: Optional[datetime] = None

    class Config:
        json_encoders = {ObjectId: str}
        arbitrary_types_allowed = True


class FolderTree(BaseModel):
    id: str = Field(..., alias="_id")
    name: str
    size: Optional[int] = 0
    parent_id: Optional[str] = None
    children: List["FolderTree"] = []

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
    )


class Breadcrumb(BaseModel):
    """A single piece of the breadcrumb path (id and name)."""

    id: str
    name: str
