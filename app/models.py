from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Literal


ItemType = Literal["task", "expense", "note", "journal", "goal", "query", "help"]


@dataclass
class ParsedItem:
    item_type: ItemType
    title: str
    body: str = ""
    date: str = ""
    reminder_at: str = ""
    amount: float | None = None
    category: str = ""
    priority: str = ""
    mood: str = ""
    tags: list[str] = field(default_factory=list)
    query_kind: str = ""
    needs_clarification: bool = False
    clarification: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StoredItem:
    id: int
    item_type: str
    title: str
    notion_page_id: str
    notion_url: str
    created_at: datetime

