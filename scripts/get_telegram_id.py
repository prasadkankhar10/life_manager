from __future__ import annotations

import asyncio

from app.config import PROJECT_ROOT, load_settings
from app.telegram import TelegramClient
from scripts.setup_notion import upsert_env


async def main() -> None:
    settings = load_settings()
    if not settings.telegram_bot_token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env first.")
    client = TelegramClient(settings.telegram_bot_token)
    updates = await client.call("getUpdates", {"limit": 20, "timeout": 0, "allowed_updates": ["message"]})
    messages = [update.get("message", {}) for update in updates]
    messages = [message for message in messages if message.get("from", {}).get("id")]
    if not messages:
        raise SystemExit("Open your new bot in Telegram, press Start, send it 'hello', then run this command again.")
    last_message = messages[-1]
    user = last_message["from"]
    upsert_env(PROJECT_ROOT / ".env", {"TELEGRAM_ALLOWED_USER_ID": str(user["id"])})
    latest_update_id = max(update["update_id"] for update in updates if isinstance(update.get("update_id"), int))
    await client.call("getUpdates", {"offset": latest_update_id + 1, "timeout": 0, "allowed_updates": ["message"]})
    print("Telegram access is now restricted to the account that started the bot.")


if __name__ == "__main__":
    asyncio.run(main())
