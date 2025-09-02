from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from app.services.transfer_manager import transfer_manager
from app.database import progress_collection

router = APIRouter(prefix="/tasks")


# -----------------------------
# Get active tasks (from memory)
# -----------------------------
@router.get("/", summary="Get all tasks for a user")
async def get_all_tasks(user_id: str):
    return transfer_manager.get_tasks_for_ui(user_id)


# -----------------------------
# Cancel a task
# -----------------------------
@router.post("/cancel/{task_id}", summary="Cancel a transfer task")
async def cancel_task(task_id: str):
    if task_id not in transfer_manager.tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    await transfer_manager.cancel_task(task_id)

    return {"task_id": task_id, "status": "cancelled"}


# -----------------------------
# Get task history (from MongoDB)
# -----------------------------
@router.get("/history", summary="Get finished tasks for a user")
async def get_task_history(
    user_id: str,
    status: Optional[str] = Query(
        None, description="Filter by status (finished, in_progress, cancelled, failed)"
    ),
    limit: int = Query(50, description="Limit number of results"),
    skip: int = Query(0, description="Skip number of results (for pagination)"),
):
    query = {"user_id": user_id}
    if status:
        query["status"] = status

    cursor = (
        progress_collection.find(query).sort("updated_at", -1).skip(skip).limit(limit)
    )
    history = await cursor.to_list(length=limit)

    # Convert ObjectId to str
    for h in history:
        h["_id"] = str(h["_id"])

    return history
