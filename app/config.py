from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Tiny .env loader so the project has no configuration-library dependency."""
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _as_bool(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_env: str
    host: str
    port: int
    base_url: str
    timezone: str
    database_url: str
    daily_summary_time: str
    telegram_bot_token: str
    telegram_allowed_user_id: int | None
    telegram_mode: str
    telegram_webhook_secret: str
    notion_token: str
    notion_parent_page_id: str
    notion_tasks_data_source_id: str
    notion_expenses_data_source_id: str
    notion_notes_data_source_id: str
    notion_journal_data_source_id: str
    notion_goals_data_source_id: str
    gemini_api_key: str
    gemini_model: str
    gemini_enabled: bool
    dashboard_password: str

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def notion_ready(self) -> bool:
        return bool(self.notion_token and all(self.data_sources.values()))

    @property
    def telegram_ready(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_allowed_user_id)

    @property
    def ai_ready(self) -> bool:
        return self.gemini_enabled and bool(self.gemini_api_key)

    @property
    def data_sources(self) -> dict[str, str]:
        return {
            "task": self.notion_tasks_data_source_id,
            "expense": self.notion_expenses_data_source_id,
            "note": self.notion_notes_data_source_id,
            "journal": self.notion_journal_data_source_id,
            "goal": self.notion_goals_data_source_id,
        }

    def readiness(self) -> dict[str, bool]:
        return {
            "telegram": self.telegram_ready,
            "notion": self.notion_ready,
            "ai_parser": self.ai_ready,
            "dashboard_password": bool(self.dashboard_password),
        }


def load_settings() -> Settings:
    _load_dotenv()
    database_url = _env("DATABASE_URL")
    return Settings(
        app_env=_env("APP_ENV", "development"),
        host=_env("HOST", "127.0.0.1"),
        port=int(_env("PORT", "8000")),
        base_url=_env("BASE_URL").rstrip("/"),
        timezone=_env("TIMEZONE", "Asia/Kolkata"),
        database_url=database_url,
        daily_summary_time=_env("DAILY_SUMMARY_TIME", "08:00"),
        telegram_bot_token=_env("TELEGRAM_BOT_TOKEN"),
        telegram_allowed_user_id=(int(_env("TELEGRAM_ALLOWED_USER_ID")) if _env("TELEGRAM_ALLOWED_USER_ID").isdigit() else None),
        telegram_mode=_env("TELEGRAM_MODE", "webhook").lower(),
        telegram_webhook_secret=_env("TELEGRAM_WEBHOOK_SECRET"),
        notion_token=_env("NOTION_TOKEN"),
        notion_parent_page_id=_env("NOTION_PARENT_PAGE_ID"),
        notion_tasks_data_source_id=_env("NOTION_TASKS_DATA_SOURCE_ID"),
        notion_expenses_data_source_id=_env("NOTION_EXPENSES_DATA_SOURCE_ID"),
        notion_notes_data_source_id=_env("NOTION_NOTES_DATA_SOURCE_ID"),
        notion_journal_data_source_id=_env("NOTION_JOURNAL_DATA_SOURCE_ID"),
        notion_goals_data_source_id=_env("NOTION_GOALS_DATA_SOURCE_ID"),
        gemini_api_key=_env("GEMINI_API_KEY"),
        gemini_model=_env("GEMINI_MODEL", "gemini-2.5-flash"),
        gemini_enabled=_as_bool(_env("GEMINI_ENABLED", "true")),
        dashboard_password=_env("DASHBOARD_PASSWORD"),
    )
