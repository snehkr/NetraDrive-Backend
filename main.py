from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.services.telegram_service import telegram_service
from app.routes import (
    auth,
    download,
    files,
    folders,
    tasks,
    file_actions,
    users,
    ws_tasks,
)


# Lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    await telegram_service.start()
    yield
    await telegram_service.stop()


# FastAPI app initialization
app = FastAPI(
    title="NetraDrive API",
    description="A Google Drive-like backend using Telegram for file storage.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Root endpoint
@app.get("/", tags=["Root"])
def read_root():
    return {"message": "Welcome to NetraDrive API"}


# Include Routers
app.include_router(tasks.router, prefix="/api/v1", tags=["Tasks"])
app.include_router(ws_tasks.router, prefix="/api/v1", tags=["WebSocket Tasks"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(folders.router, prefix="/api/v1/folders", tags=["Folders"])
app.include_router(files.router, prefix="/api/v1/files", tags=["Files"])
app.include_router(file_actions.router, prefix="/api/v1", tags=["File Actions"])
app.include_router(download.router, prefix="/api/v1", tags=["File Download"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
