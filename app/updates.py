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
        if "callback_query" in update:
            cb = update["callback_query"]
            data = cb.get("data", "")
            cb_id = cb.get("id")
            sender = cb.get("from", {})
            message = cb.get("message", {})
            chat = message.get("chat", {})
            
            if not self.settings.telegram_allowed_user_id or sender.get("id") != self.settings.telegram_allowed_user_id:
                return
                
            try:
                await self.manager.telegram.call("answerCallbackQuery", {"callback_query_id": cb_id})
            except Exception:
                pass
                
            if data == "log_habit_menu":
                text = "Select a habit to log:"
                reply_markup = {
                    "inline_keyboard": [
                        [{"text": "Creative Skill", "callback_data": "cat_Creative Skill"}, {"text": "DSA", "callback_data": "cat_DSA"}],
                        [{"text": "Deep Work", "callback_data": "cat_Deep Work"}, {"text": "English", "callback_data": "cat_English"}],
                        [{"text": "Exercise", "callback_data": "cat_Exercise"}, {"text": "Game Dev", "callback_data": "cat_Game Dev"}],
                        [{"text": "Energy Level", "callback_data": "cat_Energy"}, {"text": "Impulse Urge", "callback_data": "cat_Impulse"}],
                        [{"text": "Mood", "callback_data": "cat_Mood"}],
                    ]
                }
                await self.manager.telegram.send_message(int(chat["id"]), text, reply_markup=reply_markup)
            elif data.startswith("cat_"):
                cat = data.split("_", 1)[1]
                if cat in ["Creative Skill", "DSA", "Deep Work", "English", "Exercise", "Game Dev"]:
                    text = f"Logging time for <b>{cat}</b>:"
                    reply_markup = {
                        "inline_keyboard": [
                            [{"text": "+15m", "callback_data": f"log_{cat}_15"}, {"text": "+30m", "callback_data": f"log_{cat}_30"}],
                            [{"text": "+45m", "callback_data": f"log_{cat}_45"}, {"text": "+1h", "callback_data": f"log_{cat}_60"}],
                            [{"text": "+2h", "callback_data": f"log_{cat}_120"}],
                        ]
                    }
                elif cat == "Energy":
                    text = "Select Energy Level:"
                    reply_markup = {"inline_keyboard": [[{"text": l, "callback_data": f"log_Energy_{l.lower()}"} for l in ["Good", "Low", "Middle", "High"]]]}
                elif cat == "Impulse":
                    text = "Select Impulse Urge:"
                    reply_markup = {"inline_keyboard": [[{"text": l, "callback_data": f"log_Impulse_{l.lower()}"} for l in ["None", "Low", "Middle", "High", "Failed"]]]}
                elif cat == "Mood":
                    text = "Type your mood tags directly to the bot (e.g. 'Mood: happy, focused')."
                    reply_markup = None
                await self.manager.telegram.send_message(int(chat["id"]), text, reply_markup=reply_markup)
            elif data.startswith("log_"):
                _, cat, val = data.split("_", 2)
                if cat in ["Creative Skill", "DSA", "Deep Work", "English", "Exercise", "Game Dev"]:
                    msg = f"I did {val} minutes of {cat} today."
                else:
                    msg = f"My {cat} is {val} today."
                reply = await self.manager.process_text(msg)
                await self.manager.telegram.send_message(int(chat["id"]), reply)
            return

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
            pass

