from __future__ import annotations

import asyncio
from pathlib import Path

from app.config import PROJECT_ROOT, load_settings
from app.notion import NotionClient, database_schemas


DATABASES = {
    "task": ("Tasks", "✓"),
    "expense": ("Expenses", "₹"),
    "note": ("Notes", "✦"),
    "journal": ("Journal", "☷"),
    "goal": ("Goals", "◎"),
}


def upsert_env(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    found: set[str] = set()
    rewritten: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in values:
            rewritten.append(f"{key}={values[key]}")
            found.add(key)
        else:
            rewritten.append(line)
    for key, value in values.items():
        if key not in found:
            rewritten.append(f"{key}={value}")
    path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")


async def main() -> None:
    settings = load_settings()
    if not settings.notion_token or not settings.notion_parent_page_id:
        raise SystemExit("Set NOTION_TOKEN and NOTION_PARENT_PAGE_ID in .env before running this command.")
    if any(settings.data_sources.values()):
        raise SystemExit("Some Notion data source IDs are already set. Stop to prevent duplicate databases.")

    client = NotionClient(settings.notion_token)
    created: dict[str, str] = {}
    for item_type, (name, icon) in DATABASES.items():
        print(f"Creating {name}…")
        database = await client.create_database(settings.notion_parent_page_id, name, database_schemas()[item_type], icon)
        sources = database.get("data_sources", [])
        if not sources:
            raise RuntimeError(f"Notion created {name}, but did not return its data source ID.")
        created[item_type] = sources[0]["id"]

    env_values = {
        "NOTION_TASKS_DATA_SOURCE_ID": created["task"],
        "NOTION_EXPENSES_DATA_SOURCE_ID": created["expense"],
        "NOTION_NOTES_DATA_SOURCE_ID": created["note"],
        "NOTION_JOURNAL_DATA_SOURCE_ID": created["journal"],
        "NOTION_GOALS_DATA_SOURCE_ID": created["goal"],
    }
    upsert_env(PROJECT_ROOT / ".env", env_values)
    print("\nDone. Five Notion databases were created and their IDs were saved to .env.")


if __name__ == "__main__":
    asyncio.run(main())

