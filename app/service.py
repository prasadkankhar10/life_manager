from __future__ import annotations

from datetime import datetime, timedelta
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
        
        if item.item_type == "habit":
            try:
                return await self._update_or_create_habit(item)
            except NotionError as error:
                return f"I could not save your habit to Notion: {escape(str(error))}"
                
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
        if item.query_kind == "habit_review":
            return await self.habit_review()
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

    async def habit_review(self) -> str:
        if not self.settings.ai_ready:
            return "AI is not enabled. Cannot generate habit review."
            
        today = datetime.strptime(self.settings.logical_today(), "%Y-%m-%d").date()
        week_ago = (today - timedelta(days=7)).isoformat()
        
        payload = {
            "filter": {"and": [
                {"property": "Date", "date": {"on_or_after": week_ago}},
                {"property": "Date", "date": {"on_or_before": today.isoformat()}},
            ]},
            "page_size": 14,
            "sorts": [{"property": "Date", "direction": "ascending"}],
        }
        try:
            result = await self.notion.query_data_source(self.settings.notion_habits_data_source_id, payload)
        except NotionError as error:
            return f"I could not read your habits: {escape(str(error))}"
            
        pages = result.get("results", [])
        if not pages:
            return "You haven't logged any habits in the past 7 days to review!"
            
        lines = []
        for p in pages:
            props = p.get("properties", {})
            date = props.get("Date", {}).get("date", {}).get("start", "")
            def get_num(prop): return props.get(prop, {}).get("number") or 0
            
            line = f"Date: {date}"
            cs = get_num("Creative Skill")
            dsa = get_num("DSA / Software Engineering")
            dw = get_num("Deep Work")
            eng = get_num("English Practice / Reading")
            ex = get_num("Exercise Time")
            gd = get_num("Game Dev")
            energy = props.get("Energy Level", {}).get("select", {}).get("name", "") if props.get("Energy Level", {}).get("select") else ""
            impulse = props.get("Fab / Impulse Urge", {}).get("select", {}).get("name", "") if props.get("Fab / Impulse Urge", {}).get("select") else ""
            
            if cs: line += f", Creative: {cs}m"
            if dsa: line += f", DSA: {dsa}m"
            if dw: line += f", DeepWork: {dw}m"
            if eng: line += f", English: {eng}m"
            if ex: line += f", Exercise: {ex}m"
            if gd: line += f", GameDev: {gd}m"
            if energy: line += f", Energy: {energy}"
            if impulse: line += f", Impulse: {impulse}"
            lines.append(line)
            
        habit_text = "\n".join(lines)
        prompt = f"Here is my habit tracking data for the last 7 days:\n{habit_text}\n\nAnalyze this data and provide a brief, encouraging review of my progress. Highlight 1 or 2 specific areas I can improve on. Keep it short (max 4 sentences)."
        
        import httpx
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.settings.gemini_model}:generateContent?key={self.settings.gemini_api_key}"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json={"contents": [{"parts": [{"text": prompt}]}]})
            resp.raise_for_status()
            ai_reply = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            return f"<b>Weekly Habit Review</b>\n\n{escape(ai_reply)}"
        except Exception as e:
            import logging
            logging.error(f"Habit review AI failed: {e}", exc_info=True)
            return "Sorry, I couldn't generate an AI review right now."

    async def _update_or_create_habit(self, item: ParsedItem) -> str:
        data_source_id = self.settings.data_sources["habit"]
        date_str = item.date or self.settings.logical_today()
        
        payload = {
            "filter": {"property": "Date", "date": {"equals": date_str}},
            "page_size": 1
        }
        result = await self.notion.query_data_source(data_source_id, payload)
        pages = result.get("results", [])
        
        new_props = {
            "Name": title(date_str), "Date": date_value(date_str), "Source": select("Telegram"),
        }
        
        if pages:
            page = pages[0]
            props = page.get("properties", {})
            page_id = page["id"]
            
            def add_num(prop_name, new_val):
                if new_val is not None:
                    old_val = props.get(prop_name, {}).get("number") or 0
                    new_props[prop_name] = number(old_val + new_val)
                    
            add_num("Creative Skill", item.creative_skill_minutes)
            add_num("DSA / Software Engineering", item.dsa_minutes)
            add_num("Deep Work", item.deep_work_minutes)
            add_num("English Practice / Reading", item.english_minutes)
            add_num("Exercise Time", item.exercise_minutes)
            add_num("Game Dev", item.game_dev_minutes)
            
            if item.exercise_type:
                old_ex = "".join(p.get("plain_text", "") for p in props.get("Exercise Type", {}).get("rich_text", []))
                merged_ex = f"{old_ex}, {item.exercise_type}" if old_ex else item.exercise_type
                new_props["Exercise Type"] = text(merged_ex)
                
            if item.energy_level:
                new_props["Energy Level"] = select(item.energy_level)
            if item.impulse_urge:
                new_props["Fab / Impulse Urge"] = select(item.impulse_urge)
            if item.mood_tags:
                old_tags = [t.get("name") for t in props.get("Mood", {}).get("multi_select", [])]
                merged_tags = list(set(old_tags + item.mood_tags))
                new_props["Mood"] = multi_select(merged_tags)
                
            updated_page = await self.notion.update_page(page_id, new_props)
            page_url = updated_page.get("url", "")
            return f"Updated your daily tracker for {date_str}. <a href=\"{page_url}\">View in Notion</a>"
        else:
            if item.creative_skill_minutes is not None: new_props["Creative Skill"] = number(item.creative_skill_minutes)
            if item.dsa_minutes is not None: new_props["DSA / Software Engineering"] = number(item.dsa_minutes)
            if item.deep_work_minutes is not None: new_props["Deep Work"] = number(item.deep_work_minutes)
            if item.english_minutes is not None: new_props["English Practice / Reading"] = number(item.english_minutes)
            if item.exercise_minutes is not None: new_props["Exercise Time"] = number(item.exercise_minutes)
            if item.game_dev_minutes is not None: new_props["Game Dev"] = number(item.game_dev_minutes)
            if item.exercise_type: new_props["Exercise Type"] = text(item.exercise_type)
            if item.energy_level: new_props["Energy Level"] = select(item.energy_level)
            if item.impulse_urge: new_props["Fab / Impulse Urge"] = select(item.impulse_urge)
            if item.mood_tags: new_props["Mood"] = multi_select(item.mood_tags)
            
            created_page = await self.notion.create_page(data_source_id, new_props)
            page_url = created_page.get("url", "")
            return f"Started a new daily tracker for {date_str}. <a href=\"{page_url}\">View in Notion</a>"

    async def send_daily_summary(self) -> None:
        if not self.settings.telegram_ready:
            return
        await self.telegram.send_message(self.settings.telegram_allowed_user_id, await self.today_tasks())
