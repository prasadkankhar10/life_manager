from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.config import Settings
from app.models import ParsedItem


CAPTURE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "item_type": {"type": "string", "enum": ["task", "expense", "note", "journal", "goal", "query", "help"]},
        "title": {"type": "string"},
        "body": {"type": "string"},
        "date": {"type": "string"},
        "reminder_at": {"type": "string"},
        "amount": {"type": ["number", "null"]},
        "category": {"type": "string"},
        "priority": {"type": "string", "enum": ["", "High", "Medium", "Low"]},
        "mood": {"type": "string", "enum": ["", "Great", "Good", "Okay", "Low"]},
        "tags": {"type": "array", "items": {"type": "string"}},
        "query_kind": {"type": "string", "enum": ["", "today", "tasks", "expenses_month", "reminders"]},
        "needs_clarification": {"type": "boolean"},
        "clarification": {"type": "string"},
    },
    "required": [
        "item_type", "title", "body", "date", "reminder_at", "amount", "category", "priority", "mood", "tags",
        "query_kind", "needs_clarification", "clarification",
    ],
}


class GeminiExtractor:
    def __init__(self, api_key: str, model: str, timezone) -> None:
        self.api_key = api_key
        self.model = model
        self.timezone = timezone

    async def extract(self, message: str, now: datetime) -> ParsedItem:
        instructions = f"""You are a careful private life-manager message parser.
Today is {now.date().isoformat()} and the user's timezone is {now.tzinfo}.
Classify the message and return only the requested JSON schema. Convert relative dates into ISO dates.
For a task use date for its due date. For an explicit “remind me” request, set reminder_at to an ISO 8601 datetime with timezone; if the user gave a date but no time, use 09:00 in their timezone. If no date can be inferred, ask one brief clarification question.
For expenses, extract a numeric amount without currency symbols and use today's date if the user says today or gives no date.
For journal entries preserve the writing in body. For information requests use item_type=query and query_kind.
For tracking/logging habits (including imperative commands like 'mark habit', 'log habit', 'I ran', etc.), use item_type=habit. For questions or reviews about habits (e.g. 'how are my habits', 'what habits left today'), use item_type=query and query_kind=habit_review.
Never invent dates, amounts, priority, mood, or categories. If an essential ambiguity prevents an action, set needs_clarification=true and ask one brief question in clarification.
"""
        gemini_schema = {
            "type": "object",
            "properties": {
                "item_type": {"type": "string", "enum": ["task", "expense", "note", "journal", "goal", "query", "help", "habit"]},
                "title": {"type": "string"},
                "body": {"type": "string"},
                "date": {"type": "string"},
                "reminder_at": {"type": "string"},
                "amount": {"type": "number", "nullable": True},
                "category": {"type": "string"},
                "priority": {"type": "string", "enum": ["None", "High", "Medium", "Low"]},
                "mood": {"type": "string", "enum": ["None", "Great", "Good", "Okay", "Low"]},
                "tags": {"type": "array", "items": {"type": "string"}},
                "query_kind": {"type": "string", "enum": ["None", "today", "tasks", "expenses_month", "reminders", "habit_review", "process_notes", "review"]},
                "creative_skill_minutes": {"type": "number", "nullable": True},
                "dsa_minutes": {"type": "number", "nullable": True},
                "deep_work_minutes": {"type": "number", "nullable": True},
                "english_minutes": {"type": "number", "nullable": True},
                "exercise_minutes": {"type": "number", "nullable": True},
                "exercise_type": {"type": "string"},
                "game_dev_minutes": {"type": "number", "nullable": True},
                "energy_level": {"type": "string", "enum": ["None", "good", "low", "middle", "high"]},
                "impulse_urge": {"type": "string", "enum": ["None", "none", "low", "middle", "high", "failed"]},
                "mood_tags": {"type": "array", "items": {"type": "string"}},
                "needs_clarification": {"type": "boolean"},
                "clarification": {"type": "string"},
            },
            "required": [
                "item_type", "title", "body", "date", "reminder_at", "category", "priority", "mood", "tags",
                "query_kind", "needs_clarification", "clarification",
            ]
        }
        payload = {
            "system_instruction": {
                "parts": [{"text": instructions}]
            },
            "contents": [{
                "parts": [{"text": message}]
            }],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": gemini_schema,
            }
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        payload = response.json()
        
        try:
            output_text = payload["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as e:
            raise ValueError(f"AI response did not include structured text: {e}")
            
        item = ParsedItem(**json.loads(output_text))
        if item.priority == "None": item.priority = ""
        if item.mood == "None": item.mood = ""
        if item.query_kind == "None": item.query_kind = ""
        if item.energy_level == "None": item.energy_level = ""
        if item.impulse_urge == "None": item.impulse_urge = ""
        if item.impulse_urge == "none": item.impulse_urge = "None" # Map the string literal 'none' to Notion Select 'None' if needed
        if item.reminder_at:
            item.reminder_at = _normalise_reminder(item.reminder_at, self.timezone)
        return item


class MessageParser:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.extractor = GeminiExtractor(settings.gemini_api_key, settings.gemini_model, settings.tzinfo) if settings.ai_ready else None

    async def parse(self, message: str) -> ParsedItem:
        clean = message.strip()
        command = self._command(clean)
        if command:
            return command
        if self.extractor:
            try:
                return await self.extractor.extract(clean, datetime.now(self.settings.tzinfo))
            except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError) as e:
                import logging
                logging.error(f"AI Extractor failed: {e}", exc_info=True)
                # Never reject a personal capture solely because an optional AI service failed.
                pass
        return self._rules(clean)

    def _command(self, message: str) -> ParsedItem | None:
        if not message.startswith("/"):
            return None
        head, _, rest = message.partition(" ")
        command = head.split("@", 1)[0].lower()
        rest = rest.strip()
        if command in {"/start", "/help"}:
            return ParsedItem("help", "Help")
        if command in {"/today", "/tasks"}:
            return ParsedItem("query", "Today's tasks", query_kind="today")
        if command == "/summary":
            return ParsedItem("query", "Monthly expenses", query_kind="expenses_month")
        if command == "/process_notes":
            return ParsedItem("query", "Process notes", query_kind="process_notes")
        if command == "/review":
            return ParsedItem("query", "Review", query_kind="review", body=rest)
        if command == "/reminders":
            return ParsedItem("query", "Upcoming reminders", query_kind="reminders")
        if command == "/task":
            return ParsedItem("task", rest or "Untitled task", body=rest)
        if command == "/note":
            return ParsedItem("note", _short_title(rest, "Note"), body=rest, date=_today(self.settings))
        if command == "/journal":
            return ParsedItem("journal", _short_title(rest, "Journal entry"), body=rest, date=_today(self.settings))
        if command == "/goal":
            return ParsedItem("goal", rest or "Untitled goal", body=rest)
        if command == "/habit":
            return ParsedItem("habit", "Habit log", body=rest, date=_today(self.settings))
        if command == "/expense":
            return self._expense(rest, force=True)
        return ParsedItem("help", "Help")

    def _rules(self, message: str) -> ParsedItem:
        lower = message.lower()
        if lower.startswith(("journal:", "journal -", "diary:")):
            body = message.split(":", 1)[-1].strip()
            return ParsedItem("journal", _short_title(body, "Journal entry"), body=body, date=_today(self.settings))
        if lower.startswith(("idea:", "note:", "note -")):
            body = message.split(":", 1)[-1].strip()
            return ParsedItem("note", _short_title(body, "Note"), body=body, date=_today(self.settings))
        if re.search(r"\b(spent|paid|cost|expense)\b", lower) and _amount(message) is not None:
            return self._expense(message)
        if lower.startswith(("remind me", "i need to", "todo:", "task:")):
            title = re.sub(r"^(remind me( to)?|i need to|todo:|task:)\s*", "", message, flags=re.I).strip()
            due_date = _simple_date(message, self.settings)
            is_reminder = lower.startswith("remind me")
            return ParsedItem(
                "task", title or "Untitled task", body=message, date=due_date,
                reminder_at=_default_reminder(due_date, self.settings) if is_reminder and due_date else "",
                needs_clarification=is_reminder and not due_date,
                clarification="When should I remind you?" if is_reminder and not due_date else "",
            )
        return ParsedItem("note", _short_title(message, "Note"), body=message, date=_today(self.settings))

    def _expense(self, message: str, force: bool = False) -> ParsedItem:
        amount = _amount(message, force=force)
        if amount is None and force:
            return ParsedItem(
                "expense", "Expense", body=message, needs_clarification=True,
                clarification="What amount should I record for this expense?",
            )
        
        remainder = re.sub(r"(?:₹|rs\.?|inr|\$)\s*[\d,]+(?:\.\d{1,2})?|[\d,]+(?:\.\d{1,2})?\s*(?:₹|rs\.?|inr|\$)", "", message, flags=re.I)
        if force and amount is not None:
            # Strip the raw number if we fell back to grabbing the first number
            remainder = re.sub(r"[\d,]+(?:\.\d{1,2})?", "", remainder, count=1)
        
        remainder = remainder.strip(" -:.")
        category = _category(remainder)
        return ParsedItem(
            "expense", _short_title(remainder or "Expense", "Expense"), body=message,
            amount=amount, category=category, date=_simple_date(message, self.settings) or _today(self.settings),
        )


def _today(settings: Settings) -> str:
    return settings.logical_today()


def _simple_date(message: str, settings: Settings) -> str:
    match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", message)
    if match:
        return match.group(1)
    
    today_date = datetime.strptime(settings.logical_today(), "%Y-%m-%d").date()
    if re.search(r"\btomorrow\b", message, flags=re.I):
        return (today_date + timedelta(days=1)).isoformat()
    if re.search(r"\btoday\b", message, flags=re.I):
        return today_date.isoformat()
    return ""


def _default_reminder(day: str, settings: Settings) -> str:
    return datetime.fromisoformat(f"{day}T09:00:00").replace(tzinfo=settings.tzinfo).isoformat()


def _normalise_reminder(value: str, timezone) -> str:
    """Make an AI-supplied reminder safe for lexical SQLite comparison and scheduling."""
    if "T" not in value:
        return datetime.fromisoformat(f"{value}T09:00:00").replace(tzinfo=timezone).isoformat()
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    return parsed.isoformat()


def _amount(message: str, force: bool = False) -> float | None:
    match1 = re.search(r"(?:₹|rs\.?|inr|\$)\s*([\d,]+(?:\.\d{1,2})?)", message, flags=re.I)
    if match1:
        return float(match1.group(1).replace(",", ""))
        
    match2 = re.search(r"([\d,]+(?:\.\d{1,2})?)\s*(?:₹|rs\.?|inr|\$)", message, flags=re.I)
    if match2:
        return float(match2.group(1).replace(",", ""))
        
    if force:
        match3 = re.search(r"([\d,]+(?:\.\d{1,2})?)", message)
        if match3:
            return float(match3.group(1).replace(",", ""))
            
    return None


def _category(value: str) -> str:
    lowered = value.lower()
    for category, words in {
        "Food": ("lunch", "dinner", "breakfast", "coffee", "restaurant", "grocery", "groceries"),
        "Transport": ("uber", "ola", "fuel", "petrol", "metro", "bus", "train"),
        "Bills": ("rent", "electricity", "internet", "phone", "netflix"),
        "Health": ("doctor", "medicine", "gym", "pharmacy"),
    }.items():
        if any(word in lowered for word in words):
            return category
    return "Other"


def _short_title(value: str, fallback: str) -> str:
    compact = " ".join(value.split())
    return (compact[:117] + "...") if len(compact) > 120 else (compact or fallback)
