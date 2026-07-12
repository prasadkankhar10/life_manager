from __future__ import annotations

import asyncio
import base64
import hmac
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from app.config import PROJECT_ROOT, load_settings
from app.database import AppDatabase
from app.notion import NotionError
from app.poller import TelegramPoller
from app.scheduler import Scheduler
from app.service import LifeManager
from app.updates import TelegramUpdateHandler


settings = load_settings()
database = AppDatabase(settings.database_url)
manager = LifeManager(settings, database)
scheduler = Scheduler(manager)
update_handler = TelegramUpdateHandler(settings, database, manager)
poller = TelegramPoller(manager.telegram, update_handler)


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.initialize()
    scheduler_task = asyncio.create_task(scheduler.run())
    if manager.telegram.configured:
        try:
            await manager.telegram.set_my_commands([
                {"command": "habit", "description": "Log a habit or check progress"},
                {"command": "review", "description": "Get an AI review of your Notion data"},
                {"command": "today", "description": "View today's tasks"},
                {"command": "summary", "description": "View this month's expenses"},
            ])
        except Exception as e:
            import logging
            logging.error(f"Failed to set Telegram commands: {e}")

    poller_task = (
        asyncio.create_task(poller.run())
        if settings.telegram_mode == "polling" and manager.telegram.configured
        else None
    )
    yield
    scheduler.stop()
    poller.stop()
    scheduler_task.cancel()
    if poller_task:
        poller_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    if poller_task:
        try:
            await poller_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Life Manager", version="1.0.0", lifespan=lifespan)
STATIC_DIR = PROJECT_ROOT / "app" / "static"


class CaptureRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10000)


def _dashboard_authorized(request: Request) -> bool:
    if not settings.dashboard_password:
        return settings.app_env != "production"
    header = request.headers.get("authorization", "")
    if not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:]).decode("utf-8")
        _, password = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError):
        return False
    return hmac.compare_digest(password, settings.dashboard_password)


@app.middleware("http")
async def secure_dashboard(request: Request, call_next):
    if request.url.path == "/dashboard" or request.url.path.startswith("/api/"):
        if not _dashboard_authorized(request):
            return FileResponse(STATIC_DIR / "unauthorized.html", status_code=401, headers={"WWW-Authenticate": 'Basic realm="Life Manager"'})
    return await call_next(request)


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse("/dashboard")


@app.get("/dashboard", include_in_schema=False)
async def dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/assets/{asset_name}", include_in_schema=False)
async def assets(asset_name: str) -> FileResponse:
    safe_name = Path(asset_name).name
    return FileResponse(STATIC_DIR / safe_name)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "environment": settings.app_env}


@app.get("/api/status")
async def dashboard_status() -> dict[str, Any]:
    return {
        "readiness": settings.readiness(),
        "environment": settings.app_env,
        "base_url": settings.base_url,
        "timezone": settings.timezone,
        "daily_summary_time": settings.daily_summary_time,
        "recent_captures": database.recent_captures(),
        "upcoming_reminders": database.upcoming_reminders(),
    }


@app.post("/api/capture")
async def dashboard_capture(capture: CaptureRequest) -> dict[str, str]:
    return {"reply": await manager.process_text(capture.text)}


@app.get("/api/logs")
async def dashboard_logs() -> list[dict]:
    return database.get_message_logs(50)


@app.post("/api/test-connections")
async def test_connections() -> dict[str, Any]:
    result: dict[str, Any] = {"telegram": {"configured": settings.telegram_ready}, "notion": {"configured": settings.notion_ready}}
    if settings.telegram_ready:
        try:
            bot = await manager.telegram.get_me()
            result["telegram"].update({"ok": True, "bot": bot.get("username", "connected")})
        except Exception as error:
            result["telegram"].update({"ok": False, "error": str(error)})
    if settings.notion_ready:
        try:
            source = await manager.notion.retrieve_data_source(settings.notion_tasks_data_source_id)
            result["notion"].update({"ok": True, "source": source.get("id", "connected")})
        except NotionError as error:
            result["notion"].update({"ok": False, "error": str(error)})
    return result


@app.post("/api/register-webhook")
async def register_webhook() -> dict[str, str]:
    if not settings.telegram_ready:
        raise HTTPException(400, "Add TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USER_ID first.")
    if not settings.base_url.startswith("https://"):
        raise HTTPException(400, "BASE_URL must be a public HTTPS URL before registering a Telegram webhook.")
    if not settings.telegram_webhook_secret:
        raise HTTPException(400, "Set TELEGRAM_WEBHOOK_SECRET before registering a webhook.")
    await manager.telegram.set_webhook(f"{settings.base_url}/webhook/telegram", settings.telegram_webhook_secret)
    return {"message": "Telegram webhook registered."}


@app.post("/webhook/telegram", include_in_schema=False)
async def telegram_webhook(
    update: dict[str, Any],
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    if settings.telegram_webhook_secret and not hmac.compare_digest(
        x_telegram_bot_api_secret_token or "", settings.telegram_webhook_secret
    ):
        raise HTTPException(401, "Invalid Telegram webhook secret")
    if settings.app_env == "production" and not settings.telegram_webhook_secret:
        raise HTTPException(503, "Telegram webhook secret is required in production")

    try:
        await update_handler.handle(update)
    except Exception as error:
        raise HTTPException(500, "Message processing failed") from error
    return {"ok": True}
