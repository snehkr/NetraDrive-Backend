from fastapi import APIRouter, Depends, status, Body
from fastapi.security import OAuth2PasswordRequestForm
from typing import Annotated
from jose import JWTError, jwt

from app.auth.auth import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
    REFRESH_SECRET_KEY,
    settings,
)
from app.auth.schemas import Token, UserCreate
from app.config import settings
from app.database import user_collection
from app.models.user import UserBase, UserInDB
from app.utils.exceptions import http_exception, credentials_exception

router = APIRouter()


@router.post("/signup", response_model=UserBase)
async def create_user(user: UserCreate):
    existing_user = await user_collection.find_one({"username": user.username})
    if existing_user:
        raise http_exception(status.HTTP_409_CONFLICT, "Username already registered")

    hashed_password = get_password_hash(user.password)
    user_in_db = UserInDB(
        username=user.username, email=user.email, hashed_password=hashed_password
    )

    # Manually convert to dict for insertion
    user_dict = user_in_db.model_dump(by_alias=True, exclude=["id"])

    new_user = await user_collection.insert_one(user_dict)
    created_user = await user_collection.find_one({"_id": new_user.inserted_id})
    return UserBase(**created_user)


@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
):
    user = await user_collection.find_one({"username": form_data.username})
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise credentials_exception

    access_token = create_access_token(data={"sub": user["username"]})
    refresh_token = create_refresh_token(data={"sub": user["username"]})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/refresh_token", response_model=Token)
async def refresh_access_token(refresh_token: Annotated[str, Body(embed=True)]):
    try:
        payload = jwt.decode(
            refresh_token, REFRESH_SECRET_KEY, algorithms=[settings.algorithm]
        )
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await user_collection.find_one({"username": username})
    if user is None:
        raise credentials_exception

    new_access_token = create_access_token(data={"sub": username})
    new_refresh_token = create_refresh_token(data={"sub": username})

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }
