from __future__ import annotations

import psycopg2
from psycopg2.extras import DictCursor
from contextlib import contextmanager
from datetime import datetime, timezone


class AppDatabase:
    """Operational metadata only. Personal records live in Notion."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    @contextmanager
    def connect(self):
        conn = psycopg2.connect(self.dsn, cursor_factory=DictCursor)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        if not self.dsn:
            return
            
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS processed_updates (
                        update_id BIGINT PRIMARY KEY,
                        processed_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS captures (
                        id SERIAL PRIMARY KEY,
                        item_type TEXT NOT NULL,
                        title TEXT NOT NULL,
                        notion_page_id TEXT NOT NULL,
                        notion_url TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS reminders (
                        id SERIAL PRIMARY KEY,
                        remind_at TEXT NOT NULL,
                        title TEXT NOT NULL,
                        detail TEXT NOT NULL DEFAULT '',
                        notion_page_id TEXT NOT NULL DEFAULT '',
                        sent_at TEXT
                    );
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS message_logs (
                        id SERIAL PRIMARY KEY,
                        user_message TEXT NOT NULL,
                        bot_reply TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    """
                )

    def update_is_new(self, update_id: int) -> bool:
        if not self.dsn:
            return True
            
        try:
            with self.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO processed_updates (update_id, processed_at) VALUES (%s, %s)",
                        (update_id, self._now()),
                    )
            return True
        except psycopg2.IntegrityError:
            return False

    def forget_update(self, update_id: int) -> None:
        if not self.dsn:
            return
            
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM processed_updates WHERE update_id = %s", (update_id,))

    def record_capture(self, item_type: str, title: str, notion_page_id: str, notion_url: str) -> None:
        if not self.dsn:
            return
            
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO captures (item_type, title, notion_page_id, notion_url, created_at)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (item_type, title, notion_page_id, notion_url, self._now()),
                )

    def recent_captures(self, limit: int = 8) -> list[dict]:
        if not self.dsn:
            return []
            
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT item_type, title, notion_url, created_at FROM captures ORDER BY id DESC LIMIT %s", (limit,)
                )
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def add_reminder(self, remind_at: str, title: str, detail: str, notion_page_id: str) -> None:
        if not self.dsn:
            return
            
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO reminders (remind_at, title, detail, notion_page_id) VALUES (%s, %s, %s, %s)",
                    (remind_at, title, detail, notion_page_id),
                )

    def due_reminders(self, now: datetime) -> list[dict]:
        if not self.dsn:
            return []
            
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, remind_at, title, detail, notion_page_id FROM reminders
                       WHERE sent_at IS NULL AND remind_at <= %s ORDER BY remind_at ASC""",
                    (now.isoformat(),),
                )
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def mark_reminder_sent(self, reminder_id: int) -> None:
        if not self.dsn:
            return
            
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE reminders SET sent_at = %s WHERE id = %s", (self._now(), reminder_id))

    def upcoming_reminders(self, limit: int = 10) -> list[dict]:
        if not self.dsn:
            return []
            
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, remind_at, title, detail FROM reminders
                       WHERE sent_at IS NULL ORDER BY remind_at ASC LIMIT %s""",
                    (limit,),
                )
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def get_setting(self, key: str) -> str | None:
        if not self.dsn:
            return None
            
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
                row = cur.fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        if not self.dsn:
            return
            
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                    (key, value),
                )

    def log_message(self, user_message: str, bot_reply: str) -> None:
        if not self.dsn:
            return
            
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO message_logs (user_message, bot_reply, created_at) VALUES (%s, %s, %s)",
                    (user_message, bot_reply, self._now()),
                )

    def get_message_logs(self, limit: int = 50) -> list[dict]:
        if not self.dsn:
            return []
            
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, user_message, bot_reply, created_at FROM message_logs ORDER BY id DESC LIMIT %s", (limit,)
                )
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
