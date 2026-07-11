from __future__ import annotations

from typing import Any

from app.config import Settings
from app.database import AppDatabase
from app.service import LifeManager


class TelegramUpdateHandler:
    """Shared Telegram delivery logic for webhook and local long-polling modes."""

    def __init__(self, settings: Settings, database: AppDatabase, manager: LifeManager) -> None:
        self.settings = settings
        self.database = database
        self.manager = manager

    async def handle(self, update: dict[str, Any]) -> None:
        message = update.get("message") or {}
        sender = message.get("from") or {}
        chat = message.get("chat") or {}
        text = message.get("text")
        update_id = update.get("update_id")
        if not isinstance(text, str) or not isinstance(update_id, int):
            return
        if not self.settings.telegram_allowed_user_id or sender.get("id") != self.settings.telegram_allowed_user_id:
            return
        if not self.database.update_is_new(update_id):
            return
        try:
            reply = await self.manager.process_text(text)
        except Exception:
            self.database.forget_update(update_id)
            raise
        try:
            await self.manager.telegram.send_message(int(chat["id"]), reply)
        except Exception:
            # Saving to Notion succeeded. A Telegram delivery retry must not create a duplicate record.
            pass

