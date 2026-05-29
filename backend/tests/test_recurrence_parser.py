from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RECURRENCE_PARSER_PATH = PROJECT_ROOT / "app" / "services" / "recurrence_parser.py"

spec = importlib.util.spec_from_file_location("recurrence_parser", RECURRENCE_PARSER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load RecurrenceParser from {RECURRENCE_PARSER_PATH}")
recurrence_parser_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = recurrence_parser_module
spec.loader.exec_module(recurrence_parser_module)
RecurrenceParser = recurrence_parser_module.RecurrenceParser


class RecurrenceParserTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = RecurrenceParser()

    def test_parse_daily(self) -> None:
        result = self.parser.parse("每天")

        self.assertTrue(result.success)
        self.assertEqual(result.recurrence_rule["freq"], "DAILY")
        self.assertEqual(result.recurrence_rule["rrule"], "RRULE:FREQ=DAILY")

    def test_parse_weekday(self) -> None:
        result = self.parser.parse("每周一")

        self.assertTrue(result.success)
        self.assertEqual(result.recurrence_rule["freq"], "WEEKLY")
        self.assertEqual(result.recurrence_rule["byday"], ["MO"])
        self.assertEqual(result.recurrence_rule["rrule"], "RRULE:FREQ=WEEKLY;BYDAY=MO")

    def test_parse_weekday_with_time(self) -> None:
        result = self.parser.parse("每周三下午三点")

        self.assertTrue(result.success)
        self.assertEqual(result.recurrence_rule["freq"], "WEEKLY")
        self.assertEqual(result.recurrence_rule["byday"], ["WE"])
        self.assertEqual(result.recurrence_rule["byhour"], [15])
        self.assertEqual(result.recurrence_rule["byminute"], [0])
        self.assertEqual(
            result.recurrence_rule["rrule"],
            "RRULE:FREQ=WEEKLY;BYDAY=WE;BYHOUR=15;BYMINUTE=0",
        )

    def test_parse_month_day(self) -> None:
        result = self.parser.parse("每月1号")

        self.assertTrue(result.success)
        self.assertEqual(result.recurrence_rule["freq"], "MONTHLY")
        self.assertEqual(result.recurrence_rule["bymonthday"], [1])

    def test_parse_workdays(self) -> None:
        result = self.parser.parse("工作日")

        self.assertTrue(result.success)
        self.assertEqual(result.recurrence_rule["byday"], ["MO", "TU", "WE", "TH", "FR"])

    def test_unrecognized_expression(self) -> None:
        result = self.parser.parse("每两天")

        self.assertFalse(result.success)
        self.assertTrue(result.need_followup)


if __name__ == "__main__":
    unittest.main()
