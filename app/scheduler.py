from __future__ import annotations

import asyncio
from datetime import datetime

from app.service import LifeManager


class Scheduler:
    def __init__(self, manager: LifeManager) -> None:
        self.manager = manager
        self._running = True

    async def run(self) -> None:
        while self._running:
            try:
                await self.tick()
            except Exception:
                # A later tick retries unsent reminders. Deliberately avoid logging personal content.
                pass
            await asyncio.sleep(30)

    async def tick(self) -> None:
        now = datetime.now(self.manager.settings.tzinfo)
        if self.manager.settings.telegram_ready:
            for reminder in self.manager.database.due_reminders(now):
                message = f"<b>Reminder</b>\n{reminder['title']}"
                if reminder["detail"]:
                    message += f"\n{reminder['detail']}"
                await self.manager.telegram.send_message(self.manager.settings.telegram_allowed_user_id, message)
                self.manager.database.mark_reminder_sent(reminder["id"])
        if now.strftime("%H:%M") == self.manager.settings.daily_summary_time:
            key = f"daily-summary:{now.date().isoformat()}"
            if self.manager.database.get_setting(key) is None:
                await self.manager.send_daily_summary()
                self.manager.database.set_setting(key, "sent")
        if now.strftime("%H:%M") == "21:00":
            key = f"habit-reminder:{now.date().isoformat()}"
            if self.manager.database.get_setting(key) is None:
                if self.manager.settings.telegram_ready:
                    reply_markup = {
                        "inline_keyboard": [
                            [{"text": "Log Habits Now", "callback_data": "log_habit_menu"}],
                        ]
                    }
                    await self.manager.telegram.send_message(
                        self.manager.settings.telegram_allowed_user_id, 
                        "Good evening! Time to log your daily habits.",
                        reply_markup=reply_markup
                    )
                self.manager.database.set_setting(key, "sent")
        if now.strftime("%H:%M") in ["00:00", "06:00", "12:00", "18:00"]:
            key = f"process-notes:{now.date().isoformat()}-{now.hour}"
            if self.manager.database.get_setting(key) is None:
                try:
                    await self.manager.process_unprocessed_notes()
                except Exception:
                    pass
                self.manager.database.set_setting(key, "sent")

    def stop(self) -> None:
        self._running = False

