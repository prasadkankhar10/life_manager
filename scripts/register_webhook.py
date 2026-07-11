from __future__ import annotations

import asyncio

from app.config import load_settings
from app.telegram import TelegramClient


async def main() -> None:
    settings = load_settings()
    if not settings.telegram_bot_token or not settings.base_url.startswith("https://"):
        raise SystemExit("Set TELEGRAM_BOT_TOKEN and a public HTTPS BASE_URL in .env first.")
    if not settings.telegram_webhook_secret:
        raise SystemExit("Set TELEGRAM_WEBHOOK_SECRET in .env first.")
    await TelegramClient(settings.telegram_bot_token).set_webhook(
        f"{settings.base_url}/webhook/telegram", settings.telegram_webhook_secret
    )
    print("Webhook registered successfully.")


if __name__ == "__main__":
    asyncio.run(main())

