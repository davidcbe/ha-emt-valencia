"""Regression checks for every supported EMT arrival time shape."""

import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "emt_valencia" / "arrival_utils.py"
SPEC = importlib.util.spec_from_file_location("arrival_utils", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
arrival_sort_key = MODULE.arrival_sort_key


class ArrivalSortKeyTest(unittest.TestCase):
    def test_numeric_estimates_are_ordered_numerically(self) -> None:
        rows = [{"minutes": 20}, {"minutes": 2}, {"minutes": 11}]
        self.assertEqual([2, 11, 20], [row["minutes"] for row in sorted(rows, key=arrival_sort_key)])

    def test_scheduled_clock_rows_are_ordered_after_estimates(self) -> None:
        rows = [
            {"scheduled_arrival": "2026-10-22T19:30:00+02:00"},
            {"minutes": 8},
            {"scheduled_arrival": "2026-10-22T19:05:00+02:00"},
        ]
        ordered = sorted(rows, key=arrival_sort_key)
        self.assertEqual(8, ordered[0]["minutes"])
        self.assertEqual("2026-10-22T19:05:00+02:00", ordered[1]["scheduled_arrival"])

    def test_malformed_and_error_rows_never_break_mixed_responses(self) -> None:
        rows = [{"error": "invalid"}, {"scheduled_arrival": "2026-10-22T19:20:00+02:00"}, {"minutes": 4}]
        ordered = sorted(rows, key=arrival_sort_key)
        self.assertEqual(4, ordered[0]["minutes"])
        self.assertIn("error", ordered[-1])


if __name__ == "__main__":
    unittest.main()
