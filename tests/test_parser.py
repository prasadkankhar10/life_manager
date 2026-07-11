from __future__ import annotations

import asyncio
import os
import unittest

from app.config import load_settings
from app.parser import MessageParser


class ParserTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["OPENAI_ENABLED"] = "false"
        os.environ["TIMEZONE"] = "Asia/Kolkata"
        self.parser = MessageParser(load_settings())

    def test_expense_command_extracts_amount(self) -> None:
        item = asyncio.run(self.parser.parse("/expense ₹450 dinner"))
        self.assertEqual(item.item_type, "expense")
        self.assertEqual(item.amount, 450)

    def test_journal_capture(self) -> None:
        item = asyncio.run(self.parser.parse("Journal: I felt peaceful after a morning walk."))
        self.assertEqual(item.item_type, "journal")
        self.assertIn("peaceful", item.body)

    def test_relative_task_date(self) -> None:
        item = asyncio.run(self.parser.parse("I need to call Dad tomorrow"))
        self.assertEqual(item.item_type, "task")
        self.assertTrue(item.date)

    def test_reminder_without_date_asks(self) -> None:
        item = asyncio.run(self.parser.parse("Remind me to call Dad"))
        self.assertTrue(item.needs_clarification)


if __name__ == "__main__":
    unittest.main()

