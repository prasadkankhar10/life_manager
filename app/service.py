from __future__ import annotations

from datetime import datetime
from html import escape

from app.config import Settings
from app.database import AppDatabase
from app.models import ParsedItem
from app.notion import (
    NotionClient,
    NotionError,
    date_value,
    extract_page_title,
    multi_select,
    number,
    select,
    text,
    title,
)
from app.parser import MessageParser
from app.telegram import TelegramClient


HELP_TEXT = """<b>Life Manager</b>

Write naturally, for example:
• Buy milk tomorrow
• Spent ₹450 on dinner
• Journal: I felt calm after my walk
• Remind me to renew insurance on 2026-08-02

Useful commands:
/task Pay electricity bill
/expense ₹450 dinner
/note An idea worth keeping
/journal A reflection
/goal Run a half marathon
/today  /summary  /reminders"""


class LifeManager:
    def __init__(self, settings: Settings, database: AppDatabase) -> None:
        self.settings = settings
        self.database = database
        self.notion = NotionClient(settings.notion_token)
        self.telegram = TelegramClient(settings.telegram_bot_token)
        self.parser = MessageParser(settings)

    async def process_text(self, raw_text: str) -> str:
        item = await self.parser.parse(raw_text)
        if item.item_type == "help":
            reply = HELP_TEXT
        elif item.needs_clarification:
            reply = f"I need one detail first: {escape(item.clarification)}"
        elif item.item_type == "query":
            reply = await self.answer_query(item)
        else:
            reply = await self.store_item(item)
            
        self.database.log_message(raw_text, reply)
        return reply

    async def store_item(self, item: ParsedItem) -> str:
        if not self.settings.notion_ready:
            return "Notion is not connected yet. Complete the Notion setup in the project README, then try again."
        data_source_id = self.settings.data_sources[item.item_type]
        try:
            page = await self.notion.create_page(
                data_source_id=data_source_id,
                properties=self._properties_for(item),
                body=item.body,
            )
        except NotionError as error:
            return f"I could not save that to Notion: {escape(str(error))}"
        page_id, page_url = page.get("id", ""), page.get("url", "")
        self.database.record_capture(item.item_type, item.title, page_id, page_url)
        if item.reminder_at:
            self.database.add_reminder(item.reminder_at, item.title, item.body, page_id)
        return self._stored_reply(item, page_url)

    def _properties_for(self, item: ParsedItem) -> dict:
        if item.item_type == "task":
            return {
                "Name": title(item.title), "Status": select("Inbox"), "Due": date_value(item.date),
                "Reminder": date_value(item.reminder_at), "Priority": select(item.priority),
                "Category": select(item.category), "Notes": text(item.body), "Source": select("Telegram"),
            }
        if item.item_type == "expense":
            return {
                "Name": title(item.title), "Amount": number(item.amount), "Date": date_value(item.date),
                "Category": select(item.category), "Notes": text(item.body), "Source": select("Telegram"),
            }
        if item.item_type == "note":
            return {
                "Name": title(item.title), "Type": select("Idea" if "idea" in item.title.lower() else "Note"),
                "Tags": multi_select(item.tags), "Date": date_value(item.date), "Source": select("Telegram"),
            }
        if item.item_type == "journal":
            return {
                "Name": title(item.title), "Date": date_value(item.date), "Mood": select(item.mood),
                "Tags": multi_select(item.tags), "Source": select("Telegram"),
            }
        if item.item_type == "goal":
            return {
                "Name": title(item.title), "Status": select("Active"), "Target date": date_value(item.date),
                "Area": select(item.category), "Notes": text(item.body), "Source": select("Telegram"),
            }
        raise ValueError(f"Unsupported item type: {item.item_type}")

    def _stored_reply(self, item: ParsedItem, page_url: str) -> str:
        labels = {"task": "Task", "expense": "Expense", "note": "Note", "journal": "Journal entry", "goal": "Goal"}
        lines = [f"Saved <b>{labels[item.item_type]}</b>: {escape(item.title)}"]
        if item.amount is not None:
            lines.append(f"Amount: ₹{item.amount:,.2f}")
        if item.date:
            lines.append(f"Date: {escape(item.date)}")
        if item.reminder_at:
            lines.append(f"Reminder: {escape(item.reminder_at)}")
        if page_url:
            lines.append(f'<a href="{escape(page_url, quote=True)}">Open in Notion</a>')
        return "\n".join(lines)

    async def answer_query(self, item: ParsedItem) -> str:
        if item.query_kind == "reminders":
            reminders = self.database.upcoming_reminders()
            if not reminders:
                return "You have no unsent reminders."
            return "<b>Upcoming reminders</b>\n" + "\n".join(
                f"• {escape(row['title'])} — {escape(row['remind_at'])}" for row in reminders
            )
        if not self.settings.notion_ready:
            return "Notion is not connected yet."
        if item.query_kind in {"today", "tasks"}:
            return await self.today_tasks()
        if item.query_kind == "expenses_month":
            return await self.monthly_expenses()
        return HELP_TEXT

    async def today_tasks(self) -> str:
        today = datetime.now(self.settings.tzinfo).date().isoformat()
        payload = {
            "filter": {
                "and": [
                    {"property": "Due", "date": {"on_or_before": today}},
                    {"property": "Status", "select": {"does_not_equal": "Done"}},
                ]
            },
            "sorts": [{"property": "Due", "direction": "ascending"}],
            "page_size": 25,
        }
        try:
            result = await self.notion.query_data_source(self.settings.notion_tasks_data_source_id, payload)
        except NotionError as error:
            return f"I could not read your tasks: {escape(str(error))}"
        tasks = result.get("results", [])
        if not tasks:
            return "<b>Today</b>\nNo overdue or due-today tasks."
        lines = ["<b>Today</b>"]
        for task in tasks:
            due = task.get("properties", {}).get("Due", {}).get("date") or {}
            due_text = due.get("start", "No date")
            lines.append(f"• {escape(extract_page_title(task))} — {escape(due_text)}")
        return "\n".join(lines)

    async def monthly_expenses(self) -> str:
        today = datetime.now(self.settings.tzinfo).date()
        month_start = today.replace(day=1).isoformat()
        payload = {
            "filter": {"and": [
                {"property": "Date", "date": {"on_or_after": month_start}},
                {"property": "Date", "date": {"on_or_before": today.isoformat()}},
            ]},
            "page_size": 100,
        }
        try:
            result = await self.notion.query_data_source(self.settings.notion_expenses_data_source_id, payload)
        except NotionError as error:
            return f"I could not read your expenses: {escape(str(error))}"
        expenses = result.get("results", [])
        total = sum((page.get("properties", {}).get("Amount", {}).get("number") or 0) for page in expenses)
        return f"<b>This month</b>\n{len(expenses)} expenses · ₹{total:,.2f}"

    async def send_daily_summary(self) -> None:
        if not self.settings.telegram_ready:
            return
        await self.telegram.send_message(self.settings.telegram_allowed_user_id, await self.today_tasks())
