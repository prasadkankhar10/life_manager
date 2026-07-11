from __future__ import annotations

import asyncio
from pathlib import Path

from app.config import PROJECT_ROOT, load_settings
from app.notion import NotionClient, database_schemas


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
    
    if settings.notion_habits_data_source_id:
        print(f"Habits database already exists: {settings.notion_habits_data_source_id}")
        return

    client = NotionClient(settings.notion_token)
    
    print("Creating Habits…")
    database = await client.create_database(
        settings.notion_parent_page_id, "Habits", database_schemas()["habit"], "📅"
    )
    # The Notion API returns 'url' and 'id' for the database object.
    # The schema used by the project assumes 'data_sources' is returned, wait, let me check the mock/notion integration.
    # Actually, in `app/notion.py`: 
    #   "initial_data_source": {"title": rich_text(title), "properties": properties},
    #   ...
    #   and in `setup_notion.py`:
    #   sources = database.get("data_sources", [])
    # I'll replicate that exact logic.
    sources = database.get("data_sources", [])
    if not sources:
        raise RuntimeError("Notion created Habits, but did not return its data source ID.")
    habit_id = sources[0]["id"]

    env_values = {
        "NOTION_HABITS_DATA_SOURCE_ID": habit_id,
    }
    upsert_env(PROJECT_ROOT / ".env", env_values)
    print(f"\nDone. Habits Notion database created. ID {habit_id} saved to .env.")


if __name__ == "__main__":
    asyncio.run(main())
