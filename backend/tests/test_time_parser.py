from __future__ import annotations

import sys
from datetime import datetime
import importlib.util
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TIME_PARSER_PATH = PROJECT_ROOT / "app" / "services" / "time_parser.py"

spec = importlib.util.spec_from_file_location("time_parser", TIME_PARSER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load TimeParser from {TIME_PARSER_PATH}")
time_parser_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = time_parser_module
spec.loader.exec_module(time_parser_module)
TimeParser = time_parser_module.TimeParser


class TimeParserTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = TimeParser()
        self.tz = "Asia/Shanghai"
        self.base_time = datetime(2026, 5, 29, 15, 0, 0)

    def test_parse_week_range_current_week(self) -> None:
        result = self.parser.parse("本周一到本周日", self.base_time, self.tz)

        self.assertTrue(result.success)
        self.assertTrue(result.is_range)
        self.assertIsNotNone(result.start_datetime)
        self.assertIsNotNone(result.end_datetime)
        self.assertEqual(result.start_datetime.date().isoformat(), "2026-05-25")
        self.assertEqual(result.end_datetime.date().isoformat(), "2026-05-31")
        self.assertFalse(result.ambiguous)
        self.assertFalse(result.need_followup)

    def test_parse_week_range_next_week(self) -> None:
        result = self.parser.parse("下周一到下周日", self.base_time, self.tz)

        self.assertTrue(result.success)
        self.assertTrue(result.is_range)
        self.assertEqual(result.start_datetime.date().isoformat(), "2026-06-01")
        self.assertEqual(result.end_datetime.date().isoformat(), "2026-06-07")

    def test_parse_weekday_with_time(self) -> None:
        result = self.parser.parse("周五下午三点", self.base_time, self.tz)

        self.assertTrue(result.success)
        self.assertEqual(result.datetime.isoformat(), "2026-05-29T15:00:00+08:00")
        self.assertFalse(result.ambiguous)

    def test_parse_next_weekday_with_half_hour(self) -> None:
        result = self.parser.parse("下周三上午十点半", self.base_time, self.tz)

        self.assertTrue(result.success)
        self.assertEqual(result.datetime.isoformat(), "2026-06-03T10:30:00+08:00")

    def test_parse_relative_duration(self) -> None:
        one_hour = self.parser.parse("一小时后", self.base_time, self.tz)
        half_hour = self.parser.parse("半小时后", self.base_time, self.tz)

        self.assertTrue(one_hour.success)
        self.assertEqual(one_hour.datetime.isoformat(), "2026-05-29T16:00:00+08:00")
        self.assertTrue(half_hour.success)
        self.assertEqual(half_hour.datetime.isoformat(), "2026-05-29T15:30:00+08:00")

    def test_parse_ambiguous_expressions(self) -> None:
        for text in ["月底前", "周末", "睡前", "上班前"]:
            with self.subTest(text=text):
                result = self.parser.parse(text, self.base_time, self.tz)
                self.assertFalse(result.success)
                self.assertTrue(result.ambiguous)
                self.assertTrue(result.need_followup)
                self.assertEqual(result.reason, "ambiguous_expression")

    def test_parse_past_time_marks_followup(self) -> None:
        result = self.parser.parse("今天上午十点", self.base_time, self.tz)

        self.assertTrue(result.success)
        self.assertTrue(result.is_past)
        self.assertTrue(result.need_followup)
        self.assertEqual(result.reason, "parsed_time_in_past")
        self.assertEqual(result.datetime.isoformat(), "2026-05-29T10:00:00+08:00")


if __name__ == "__main__":
    unittest.main()
