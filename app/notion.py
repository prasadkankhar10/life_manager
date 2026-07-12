from __future__ import annotations

from datetime import date
from typing import Any

import httpx


NOTION_VERSION = "2026-03-11"


class NotionError(RuntimeError):
    pass


class NotionClient:
    def __init__(self, token: str) -> None:
        self.token = token

    @property
    def configured(self) -> bool:
        return bool(self.token)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if not self.token:
            raise NotionError("Notion is not configured. Add NOTION_TOKEN to .env.")
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.request(method, f"https://api.notion.com/v1{path}", headers=self._headers(), **kwargs)
        if response.is_error:
            message = response.text[:700]
            raise NotionError(f"Notion returned {response.status_code}: {message}")
        return response.json()

    async def retrieve_data_source(self, data_source_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/data_sources/{data_source_id}")

    async def create_database(self, parent_page_id: str, title: str, properties: dict[str, Any], icon: str = "") -> dict[str, Any]:
        payload = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": rich_text(title),
            "initial_data_source": {"title": rich_text(title), "properties": properties},
        }
        return await self._request("POST", "/databases", json=payload)

    async def create_page(
        self, data_source_id: str, properties: dict[str, Any], body: str = ""
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "parent": {"type": "data_source_id", "data_source_id": data_source_id},
            "properties": properties,
        }
        if body:
            payload["children"] = paragraph_blocks(body)
        return await self._request("POST", "/pages", json=payload)

    async def update_page(self, page_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {"properties": properties}
        return await self._request("PATCH", f"/pages/{page_id}", json=payload)

    async def query_data_source(self, data_source_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", f"/data_sources/{data_source_id}/query", json=payload)


def rich_text(value: str) -> list[dict[str, Any]]:
    if not value:
        return []
    return [{"type": "text", "text": {"content": value[:2000]}}]


def paragraph_blocks(value: str) -> list[dict[str, Any]]:
    chunks = [value[index : index + 1900] for index in range(0, len(value), 1900)]
    return [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": rich_text(chunk)}} for chunk in chunks[:100]]


def title(value: str) -> dict[str, Any]:
    return {"title": rich_text(value)}


def text(value: str) -> dict[str, Any]:
    return {"rich_text": rich_text(value)}


def select(value: str) -> dict[str, Any]:
    return {"select": {"name": value} if value else None}


def status(value: str) -> dict[str, Any]:
    return {"status": {"name": value} if value else None}


def date_value(value: str) -> dict[str, Any]:
    return {"date": {"start": value} if value else None}


def number(value: float | None) -> dict[str, Any]:
    return {"number": value}


def multi_select(values: list[str]) -> dict[str, Any]:
    return {"multi_select": [{"name": value[:100]} for value in values[:20]]}


def today_iso() -> str:
    return date.today().isoformat()


def extract_page_title(page: dict[str, Any]) -> str:
    for property_value in page.get("properties", {}).values():
        if property_value.get("type") == "title":
            return "".join(part.get("plain_text", "") for part in property_value.get("title", [])) or "Untitled"
    return "Untitled"


def database_schemas() -> dict[str, dict[str, Any]]:
    """Schemas intentionally stay compact; richer content is stored in page bodies."""
    source = {"type": "select", "select": {"options": [{"name": "Telegram", "color": "blue"}, {"name": "Notion", "color": "gray"}]}}
    return {
        "task": {
            "Name": {"type": "title", "title": {}},
            "Status": {"type": "select", "select": {"options": [{"name": "Inbox", "color": "gray"}, {"name": "Next", "color": "blue"}, {"name": "Done", "color": "green"}]}},
            "Due": {"type": "date", "date": {}},
            "Reminder": {"type": "date", "date": {}},
            "Priority": {"type": "select", "select": {"options": [{"name": "High", "color": "red"}, {"name": "Medium", "color": "yellow"}, {"name": "Low", "color": "gray"}]}},
            "Category": {"type": "select", "select": {"options": []}},
            "Notes": {"type": "rich_text", "rich_text": {}},
            "Source": source,
        },
        "expense": {
            "Name": {"type": "title", "title": {}},
            "Amount": {"type": "number", "number": {"format": "number"}},
            "Date": {"type": "date", "date": {}},
            "Category": {"type": "select", "select": {"options": []}},
            "Notes": {"type": "rich_text", "rich_text": {}},
            "Source": source,
        },
        "note": {
            "Name": {"type": "title", "title": {}},
            "Type": {"type": "select", "select": {"options": [{"name": "Note", "color": "blue"}, {"name": "Idea", "color": "purple"}, {"name": "Reference", "color": "gray"}]}},
            "Tags": {"type": "multi_select", "multi_select": {"options": [{"name": "Processed", "color": "green"}]}},
            "Date": {"type": "date", "date": {}},
            "Source": source,
        },
        "journal": {
            "Name": {"type": "title", "title": {}},
            "Date": {"type": "date", "date": {}},
            "Mood": {"type": "select", "select": {"options": [{"name": "Great", "color": "green"}, {"name": "Good", "color": "blue"}, {"name": "Okay", "color": "yellow"}, {"name": "Low", "color": "red"}]}},
            "Tags": {"type": "multi_select", "multi_select": {"options": []}},
            "Source": source,
        },
        "goal": {
            "Name": {"type": "title", "title": {}},
            "Status": {"type": "select", "select": {"options": [{"name": "Active", "color": "blue"}, {"name": "Paused", "color": "yellow"}, {"name": "Achieved", "color": "green"}]}},
            "Target date": {"type": "date", "date": {}},
            "Area": {"type": "select", "select": {"options": []}},
            "Notes": {"type": "rich_text", "rich_text": {}},
            "Source": source,
        },
        "habit": {
            "Name": {"type": "title", "title": {}},
            "Date": {"type": "date", "date": {}},
            "Creative Skill": {"type": "number", "number": {"format": "number"}},
            "DSA / Software Engineering": {"type": "number", "number": {"format": "number"}},
            "Deep Work": {"type": "number", "number": {"format": "number"}},
            "English Practice / Reading": {"type": "number", "number": {"format": "number"}},
            "Exercise Time": {"type": "number", "number": {"format": "number"}},
            "Exercise Type": {"type": "rich_text", "rich_text": {}},
            "Game Dev": {"type": "number", "number": {"format": "number"}},
            "Energy Level": {"type": "select", "select": {"options": [{"name": "good", "color": "green"}, {"name": "low", "color": "red"}, {"name": "middle", "color": "yellow"}, {"name": "high", "color": "blue"}]}},
            "Fab / Impulse Urge": {"type": "select", "select": {"options": [{"name": "none", "color": "green"}, {"name": "low", "color": "yellow"}, {"name": "middle", "color": "orange"}, {"name": "high", "color": "red"}, {"name": "failed", "color": "gray"}]}},
            "Mood": {"type": "multi_select", "multi_select": {"options": []}},
            "Source": source,
        },
    }
