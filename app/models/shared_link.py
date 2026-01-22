# app/models/shared_link.py
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from bson import ObjectId
from .user import PyObjectId


class SharedLinkBase(BaseModel):
    file_id: str
    is_active: bool = True


class SharedLinkCreate(SharedLinkBase):
    pass


class SharedLinkInDB(SharedLinkBase):
    id: str = Field(alias="_id")
    owner_id: PyObjectId
    created_at: datetime = Field(default_factory=datetime.utcnow)
    views: int = 0

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
    )
