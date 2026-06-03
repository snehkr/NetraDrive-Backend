import json
import uuid
import asyncio
import time
from datetime import datetime
from typing import Dict
from app.services.ws_manager import ws_manager
from app.services.cancel_manager import cancel_manager
from app.services.progress_manager import progress_manager
from app.utils.format_utils import format_bytes, format_eta
from app.database import progress_collection


class TransferManager:
    def __init__(self, max_concurrent: int = 2, max_preview: int = 3):
        self.tasks: Dict[str, dict] = {}
        self.queue = asyncio.Queue()
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.preview_queue = asyncio.Queue()
        self.preview_semaphore = asyncio.Semaphore(max_preview)
        self.bg_tasks = set()

    # -------------------------
    # Background task runner
    # -------------------------
    def fire_bg_task(self, coro):
        """Safely executes background tasks without blocking the main event loop."""
        task = asyncio.create_task(coro)
        self.bg_tasks.add(task)
        task.add_done_callback(self.bg_tasks.discard)

    # -------------------------
    # Start main task
    # -------------------------
    def start_task(self, file_name: str, user_id: str) -> str:
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "file_name": file_name,
            "status": "queued",
            "start_time": None,
            "type": "main",
            "transferred": 0,
            "total": 0,
            "user_id": user_id,
            "last_db_update": 0,  # Used for throttling
            "last_ws_update": 0,  # Used for throttling
        }
        progress_manager.start(task_id, file_name)
        cancel_manager.start(task_id)
        self.queue.put_nowait(task_id)
        return task_id

    # -------------------------
    # Start preview task
    # -------------------------
    def start_preview_task(self, file_name: str, user_id: str) -> str:
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "file_name": file_name,
            "status": "queued",
            "start_time": None,
            "type": "preview",
            "transferred": 0,
            "total": 0,
            "user_id": user_id,
            "last_db_update": 0,
            "last_ws_update": 0,
        }
        progress_manager.start(task_id, file_name)
        cancel_manager.start(task_id)
        self.preview_queue.put_nowait(task_id)
        return task_id

    # -------------------------
    # Run main task
    # -------------------------
    async def run_task(self, task_id: str, coro):
        async with self.semaphore:
            return await self._execute_task(task_id, coro)

    # -------------------------
    # Run preview task
    # -------------------------
    async def run_preview_task(self, task_id: str, coro):
        async with self.preview_semaphore:
            return await self._execute_task(task_id, coro)

    # -------------------------
    # Core task executor
    # -------------------------
    async def _execute_task(self, task_id: str, coro):
        task = self.tasks.get(task_id)
        if not task:
            return {"task_id": task_id, "status": "not_found"}

        # If already cancelled before start
        if cancel_manager.is_cancelled(task_id):
            task["status"] = "cancelled"
            progress_manager.finish(task_id)
            cancel_manager.finish(task_id)
            await self._save_progress_db(task_id)
            return {"task_id": task_id, "status": "cancelled"}

        task["status"] = "in_progress"
        task["start_time"] = time.time()
        await self._save_progress_db(task_id)

        try:
            result = await coro
            task["status"] = "completed"
            result = {"task_id": task_id, "status": "completed", "result": result}

            # Push WS event
            message = json.dumps({"event": "completed", "task": task})
            self.fire_bg_task(ws_manager.send_to_user(task["user_id"], message))
        except Exception as e:
            if (
                cancel_manager.is_cancelled(task_id)
                or "cancelled" in str(e).lower()
                or "NoneType" in str(e)
            ):
                task["status"] = "cancelled"
                result = {"task_id": task_id, "status": "cancelled"}

                # Push WS event
                message = json.dumps({"event": "cancelled", "task": task})
                self.fire_bg_task(ws_manager.send_to_user(task["user_id"], message))
            else:
                task["status"] = "failed"
                result = {"task_id": task_id, "status": "failed", "error": str(e)}

                # Push WS event
                message = json.dumps({"event": "failed", "task": task})
                self.fire_bg_task(ws_manager.send_to_user(task["user_id"], message))

        finally:
            progress_manager.finish(task_id)
            cancel_manager.finish(task_id)
            await self._save_progress_db(task_id)
            # schedule cleanup
            self.fire_bg_task(self._cleanup_task(task_id))

        return result

    # -------------------------
    # Cleanup finished tasks after delay
    # -------------------------
    async def _cleanup_task(self, task_id: str, delay: int = 600):
        """Remove a finished task from memory after `delay` seconds (default 10 min)."""
        await asyncio.sleep(delay)
        if task_id in self.tasks and self.tasks[task_id]["status"] in [
            "completed",
            "cancelled",
            "failed",
        ]:
            self.tasks.pop(task_id, None)

    # -------------------------------------------------------------
    # THROTTLE PROGRESS TO PREVENT EVENT LOOP DEADLOCK
    # -------------------------------------------------------------
    async def update_progress(
        self, task_id: str, transferred: int, total: int, user_id: str
    ):
        task = self.tasks.get(task_id)
        if not task:
            return

        task["transferred"] = transferred
        task["total"] = total
        task["user_id"] = user_id

        now = time.time()

        # 1. Throttle DB updates to once per second (or when 100% complete)
        if now - task.get("last_db_update", 0) > 1.0 and transferred < total:
            task["last_db_update"] = now
            self.fire_bg_task(self._save_progress_db(task_id))

        # 2. Throttle WebSockets to once per 0.5 seconds
        if now - task.get("last_ws_update", 0) > 0.5 or transferred == total:
            task["last_ws_update"] = now
            message = json.dumps({"event": "progress", "task": task})
            self.fire_bg_task(ws_manager.send_to_user(task["user_id"], message))

    # -------------------------
    # Save progress to DB
    # -------------------------
    async def _save_progress_db(self, task_id: str):
        task = self.tasks.get(task_id)
        if not task:
            return

        transferred = task.get("transferred", 0)
        total = task.get("total", 0)
        percent = (transferred / total * 100) if total else 0
        elapsed = time.time() - task.get("start_time", time.time())
        speed = transferred / elapsed if elapsed > 0 else 0
        remaining_bytes = max(total - transferred, 0)
        eta_seconds = remaining_bytes / speed if speed > 0 else None

        await progress_collection.update_one(
            {"task_id": task_id, "user_id": task["user_id"]},
            {
                "$set": {
                    "file_name": task["file_name"],
                    "type": task.get("type", "main"),
                    "status": task["status"],
                    "transferred": transferred,
                    "total": total,
                    "progress_percent": round(percent, 2),
                    "speed_bytes_per_sec": round(speed, 2),
                    "eta_seconds": round(eta_seconds, 2) if eta_seconds else None,
                    "eta_friendly": format_eta(eta_seconds),
                    "updated_at": datetime.utcnow(),
                },
                "$setOnInsert": {"started_at": datetime.utcnow()},
            },
            upsert=True,
        )

    # -------------------------
    # Cancel task safely
    # -------------------------
    async def cancel_task(self, task_id: str):
        """
        Marks a task as cancelled.
        Updates DB status and leaves it in memory for _execute_task to clean up.
        """
        cancel_manager.cancel(task_id)
        task = self.tasks.get(task_id)
        if task:
            task["status"] = "cancelled"
            await progress_collection.update_one(
                {"task_id": task_id},
                {"$set": {"status": "cancelled", "updated_at": datetime.utcnow()}},
            )
            message = json.dumps({"event": "cancelled", "task": task})
            self.fire_bg_task(ws_manager.send_to_user(task["user_id"], message))

    # -------------------------
    # List all tasks
    # -------------------------
    def list_all_tasks(self, user_id: str = None):
        return self.get_tasks_for_ui(user_id)

    # -------------------------
    # Get tasks for UI
    # -------------------------
    def get_tasks_for_ui(self, user_id: str = None):
        ui_tasks = []
        for task_id, task in self.tasks.items():
            if user_id and task.get("user_id") != user_id:
                continue
            transferred = task.get("transferred", 0)
            total = task.get("total", 0)
            start_time = task.get("start_time")
            percent = (transferred / total * 100) if total else 0
            elapsed = time.time() - start_time if start_time else 0
            speed = transferred / elapsed if elapsed > 0 else 0
            remaining_bytes = max(total - transferred, 0)
            eta_seconds = remaining_bytes / speed if speed > 0 else None
            ui_tasks.append(
                {
                    "task_id": task_id,
                    "file_name": task["file_name"],
                    "status": task["status"],
                    "type": task.get("type", "main"),
                    "progress_percent": round(percent, 2),
                    "transferred": transferred,
                    "transferred_hr": format_bytes(transferred),
                    "total": total,
                    "total_hr": format_bytes(total),
                    "speed_bytes_per_sec": round(speed, 2),
                    "eta_seconds": round(eta_seconds, 2) if eta_seconds else None,
                    "eta_friendly": format_eta(eta_seconds),
                    "can_cancel": task["status"] in ["queued", "in_progress"],
                }
            )
        return ui_tasks


transfer_manager = TransferManager()
