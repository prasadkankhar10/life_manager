from __future__ import annotations

import asyncio
from app.config import load_settings
from app.telegram import TelegramClient

async def main():
    settings = load_settings()
    if not settings.telegram_bot_token:
        print("Telegram bot token not found in .env")
        return
        
    client = TelegramClient(settings.telegram_bot_token)
    commands = [
        {"command": "habit", "description": "Open habit tracker menu"},
        {"command": "task", "description": "Log a task"},
        {"command": "expense", "description": "Log an expense"},
        {"command": "note", "description": "Log a note or idea"},
        {"command": "journal", "description": "Log a journal entry"},
        {"command": "goal", "description": "Log a goal"},
        {"command": "review", "description": "AI review (all, habits, tasks, etc)"},
        {"command": "today", "description": "Show today's tasks"},
        {"command": "summary", "description": "Show monthly expenses"},
        {"command": "reminders", "description": "Show upcoming reminders"},
        {"command": "process_notes", "description": "Run AI Note Processor"},
        {"command": "help", "description": "Show help message"}
    ]
    
    print("Setting Telegram commands...")
    resp = await client.call("setMyCommands", {"commands": commands})
    print(f"Response: {resp}")

if __name__ == "__main__":
    asyncio.run(main())
