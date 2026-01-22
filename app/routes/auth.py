from datetime import datetime, timedelta, timezone
from fastapi.security import OAuth2PasswordRequestForm
from typing import Annotated
from jose import JWTError, jwt
from fastapi import APIRouter, Depends, HTTPException, status, Body, BackgroundTasks
from app.auth.auth import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
    REFRESH_SECRET_KEY,
    settings,
)
from app.auth.schemas import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    Token,
    UserCreate,
)
from app.config import settings
from app.database import user_collection
from app.models.user import UserBase, UserInDB
from app.services.resend_service import (
    send_reset_password_email,
    send_verification_email,
)
from app.utils.exceptions import http_exception, credentials_exception

router = APIRouter()


# --- Helper to create email verification token ---
def create_verification_token(email: str):
    expire = datetime.now(timezone.utc) + timedelta(minutes=30)
    to_encode = {"sub": email, "type": "verification", "exp": expire}
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


# --- Helper for Reset Token ---
def create_reset_token(email: str):
    expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode = {"sub": email, "type": "reset", "exp": expire}
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, background_tasks: BackgroundTasks):
    # Check if user exists
    existing_user = await user_collection.find_one({"username": user.username})
    existing_email = await user_collection.find_one({"email": user.email})

    if existing_user:
        raise http_exception(status.HTTP_409_CONFLICT, "Username already registered")
    if existing_email:
        raise http_exception(status.HTTP_409_CONFLICT, "Email already registered")

    hashed_password = get_password_hash(user.password)

    # Create user with is_verified = False
    user_in_db = UserInDB(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
        is_verified=False,
    )

    user_dict = user_in_db.model_dump(by_alias=True, exclude=["id"])
    await user_collection.insert_one(user_dict)

    # Generate Token and Send Email
    verification_token = create_verification_token(user.email)
    background_tasks.add_task(
        send_verification_email, user.email, user.username, verification_token
    )

    return {
        "message": "Registration successful! Please check your email to verify your account."
    }


# --- VERIFY EMAIL ---
@router.get("/verify-email")
async def verify_email(token: str):
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        email: str = payload.get("sub")
        token_type: str = payload.get("type")

        if not email or token_type != "verification":
            raise HTTPException(status_code=400, detail="Invalid token")

    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user = await user_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.get("is_verified"):
        return {"message": "Email already verified. You can login now."}

    # Verify the user
    await user_collection.update_one({"email": email}, {"$set": {"is_verified": True}})

    return {"message": "Email verified successfully! You may now login."}


# --- LOGIN & TOKEN GENERATION ---
@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
):
    user = await user_collection.find_one({"username": form_data.username})

    # Validate Password
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise credentials_exception

    # Validate Verification Status
    if not user.get("is_verified", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email not verified. Please check your inbox.",
        )

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


# --- FORGOT PASSWORD ---
@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(
    request: ForgotPasswordRequest, background_tasks: BackgroundTasks
):
    """
    Initiates the password reset process.
    Always returns 200 to prevent email enumeration.
    """
    user = await user_collection.find_one({"email": request.email})

    if user:
        # Generate a specific reset token
        token = create_reset_token(request.email)

        # Send email in background
        background_tasks.add_task(
            send_reset_password_email, request.email, user["username"], token
        )

    return {"message": "If that email exists, a password reset link has been sent."}


# --- RESET PASSWORD ---
@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(request: ResetPasswordRequest):
    """
    Verifies the token and updates the user's password.
    """
    try:
        # Decode and validate token
        payload = jwt.decode(
            request.token, settings.secret_key, algorithms=[settings.algorithm]
        )
        email: str = payload.get("sub")
        token_type: str = payload.get("type")

        if not email or token_type != "reset":
            raise HTTPException(status_code=400, detail="Invalid token type")

    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    # Verify user exists
    user = await user_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Hash new password and update DB
    new_hashed_password = get_password_hash(request.new_password)

    await user_collection.update_one(
        {"email": email}, {"$set": {"hashed_password": new_hashed_password}}
    )

    return {"message": "Password has been reset successfully. You can now login."}
