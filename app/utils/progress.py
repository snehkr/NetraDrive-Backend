# app/utils/progress.py
import time
from app.services.cancel_manager import cancel_manager
from app.services.transfer_manager import transfer_manager


async def progress(current, total, start_time, task_id, user_id, prefix=""):
    if cancel_manager.is_cancelled(task_id):
        raise Exception("Transfer cancelled by user")

    await transfer_manager.update_progress(task_id, current, total, user_id)

    elapsed = time.time() - start_time
    percent = (current / total * 100) if total > 0 else 0
    print(f"{prefix} {current}/{total} bytes ({percent:.2f}%) - {elapsed:.2f}s")
