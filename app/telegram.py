from __future__ import annotations

from typing import Any

import httpx


class TelegramError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, token: str) -> None:
        self.token = token

    @property
    def configured(self) -> bool:
        return bool(self.token)

    async def call(self, method: str, payload: dict[str, Any] | None = None, timeout: int = 20) -> Any:
        if not self.token:
            raise TelegramError("Telegram is not configured. Add TELEGRAM_BOT_TOKEN to .env.")
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"https://api.telegram.org/bot{self.token}/{method}", json=payload or {})
        if response.is_error:
            raise TelegramError(f"Telegram returned {response.status_code}: {response.text[:500]}")
        body = response.json()
        if not body.get("ok"):
            raise TelegramError(body.get("description", "Telegram request failed"))
        return body.get("result")

    async def send_message(self, chat_id: int, text: str, reply_markup: dict[str, Any] | None = None) -> Any:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text[:4096], "parse_mode": "HTML", "disable_web_page_preview": True}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return await self.call("sendMessage", payload)

    async def get_me(self) -> Any:
        return await self.call("getMe")

    async def set_webhook(self, url: str, secret_token: str) -> Any:
        payload: dict[str, Any] = {"url": url, "allowed_updates": ["message", "callback_query"]}
        if secret_token:
            payload["secret_token"] = secret_token
        return await self.call("setWebhook", payload)

    async def delete_webhook(self) -> Any:
        return await self.call("deleteWebhook", {"drop_pending_updates": False})
        
    async def set_my_commands(self, commands: list[dict[str, str]]) -> Any:
        return await self.call("setMyCommands", {"commands": commands})

    async def get_updates(self, offset: int | None) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": 25, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            payload["offset"] = offset
        return await self.call("getUpdates", payload, timeout=35)
