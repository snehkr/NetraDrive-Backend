import os
from pyrogram import Client
from pyrogram.types import Message
from app.config import settings
from app.utils.progress import progress
from app.services.transfer_manager import transfer_manager

# Create the working directory if it doesn't exist
os.makedirs(settings.telegram_workdir, exist_ok=True)

# Initialize the Telegram client
app = Client(
    settings.telegram_session_name,
    api_id=settings.telegram_api_id,
    api_hash=settings.telegram_api_hash,
    workdir=settings.telegram_workdir,
)


# Telegram service class
class TelegramService:
    def __init__(self, client: Client):
        self.client = client
        self.chat_id = settings.telegram_storage_chat_id

    async def start(self):
        if not self.client.is_connected:
            await self.client.start()

    async def stop(self):
        if self.client.is_connected:
            await self.client.stop()

    # -------------------------
    # Upload file to Telegram
    # -------------------------
    async def upload_file(self, file_path: str, file_name: str, user_id: str) -> dict:
        task_id = transfer_manager.start_task(file_name, user_id)

        async def coro():
            msg: Message = await self.client.send_document(
                chat_id=self.chat_id,
                document=file_path,
                caption=file_name,
                file_name=file_name,
                progress=progress,
                progress_args=(
                    transfer_manager.tasks[task_id]["start_time"],
                    task_id,
                    user_id,
                    "[UPLOAD]",
                ),
            )
            return {"task_id": task_id, "chat_id": msg.chat.id, "message_id": msg.id}

        return await transfer_manager.run_task(task_id, coro())

    # -------------------------
    # Full download (for user)
    # -------------------------
    async def download_file(
        self, message_id: int, dest_path: str, file_name: str, user_id: str
    ) -> dict:
        task_id = transfer_manager.start_task(file_name, user_id)

        async def coro():
            message = await self.client.get_messages(self.chat_id, message_id)
            await self.client.download_media(
                message,
                file_name=dest_path,
                progress=progress,
                progress_args=(
                    transfer_manager.tasks[task_id]["start_time"],
                    task_id,
                    user_id,
                    "[DOWNLOAD]",
                ),
            )
            return {"task_id": task_id, "download_path": dest_path}

        return await transfer_manager.run_task(task_id, coro())

    # -------------------------
    # Preview download (small file or temp storage)
    # -------------------------
    async def download_file_for_preview(
        self, message_id: int, dest_path: str, user_id: str
    ) -> dict:
        """
        Directly downloads a Telegram file for preview without tracking in TransferManager.
        """
        message = await self.client.get_messages(self.chat_id, message_id)
        await self.client.download_media(message, file_name=dest_path)

        return {"download_path": dest_path}

    # -------------------------
    # Edit message caption
    # -------------------------
    async def edit_message_caption(self, message_id: int, new_caption: str):
        await self.client.edit_message_caption(
            chat_id=self.chat_id, message_id=message_id, caption=new_caption
        )

    # -------------------------
    # Delete file(s) from Telegram
    # -------------------------
    async def delete_messages(self, message_ids: list[int]):
        await self.client.delete_messages(self.chat_id, message_ids)

    # --- Task Management ---
    def list_all_tasks(self, user_id: str = None):
        return transfer_manager.get_tasks_for_ui(user_id)

    def cancel_task(self, task_id: str):
        transfer_manager.cancel_task(task_id)


telegram_service = TelegramService(app)
