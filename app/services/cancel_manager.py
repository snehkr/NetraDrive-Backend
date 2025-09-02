# app/services/cancel_manager.py


class CancelManager:
    def __init__(self):
        self.tasks = {}  # task_id -> cancel flag

    def start(self, task_id: str):
        self.tasks[task_id] = False

    def cancel(self, task_id: str):
        self.tasks[task_id] = True

    def is_cancelled(self, task_id: str) -> bool:
        return self.tasks.get(task_id, False)

    def finish(self, task_id: str):
        self.tasks.pop(task_id, None)


cancel_manager = CancelManager()
