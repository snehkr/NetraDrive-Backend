# app/utils/progress.py
import time
from app.services.cancel_manager import cancel_manager
from app.services.transfer_manager import transfer_manager


async def progress(current, total, start_time, task_id, user_id, prefix=""):
    if cancel_manager.is_cancelled(task_id):
        raise Exception("Transfer cancelled by user")

    # Safety catch: prevent NoneType math errors
    if not start_time:
        start_time = time.time()

    await transfer_manager.update_progress(task_id, current, total, user_id)

    # Safety catch: Prevent division by zero
    elapsed = max(time.time() - start_time, 0.1)
    percent = (current / total * 100) if total and total > 0 else 0

    # Optional: Only print every 10% to avoid flooding VPS console logs
    if current == total or int(percent) % 10 == 0:
        print(f"{prefix} {current}/{total} bytes ({percent:.2f}%) - {elapsed:.2f}s")
