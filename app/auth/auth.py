from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.auth.schemas import TokenData

from app.config import settings
from app.database import user_collection
from app.models.user import UserInDB
from app.utils.exceptions import credentials_exception

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

# --- REFRESH TOKEN SETTINGS ---
REFRESH_SECRET_KEY = settings.secret_key + "_refresh"
REFRESH_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, settings.secret_key, algorithm=settings.algorithm
    )
    return encoded_jwt


def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=REFRESH_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, REFRESH_SECRET_KEY, algorithm=settings.algorithm
    )
    return encoded_jwt


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> UserInDB:
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception

    user = await user_collection.find_one({"username": token_data.username})
    if user is None:
        raise credentials_exception

    return UserInDB(**user)
