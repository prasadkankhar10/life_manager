from __future__ import annotations

import asyncio

from app.telegram import TelegramClient
from app.updates import TelegramUpdateHandler


class TelegramPoller:
    def __init__(self, client: TelegramClient, handler: TelegramUpdateHandler) -> None:
        self.client = client
        self.handler = handler
        self._running = True
        self._offset: int | None = None

    async def run(self) -> None:
        # Telegram does not allow polling while a webhook is active. Keep queued messages intact.
        await self.client.delete_webhook()
        while self._running:
            try:
                updates = await self.client.get_updates(self._offset)
                for update in updates:
                    update_id = update.get("update_id")
                    if isinstance(update_id, int):
                        self._offset = update_id + 1
                    await self.handler.handle(update)
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(3)

    def stop(self) -> None:
        self._running = False

