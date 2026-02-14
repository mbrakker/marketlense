import unittest

from src.utils.time_period import normalize_time_period


class TestTimePeriodUtils(unittest.TestCase):
    def test_normalize_supported_formats(self) -> None:
        cases = {
            "2025": "2025",
            "2025 to 2026": "2025-2026",
            "Q2 2024": "Q2 2024",
            "2024 Q3": "Q3 2024",
            "Q1 to Q3 2026": "Q1-Q3 2026",
            "Q4 2025 to Q2 2026": "Q4 2025-Q2 2026",
            "June 2023": "June 2023",
            "2023 Sep": "September 2023",
            "June to November 2023": "June-November 2023",
            "June 2023 to November 2023": "June-November 2023",
            "June 2023 to November 2024": "June 2023-November 2024",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(expected, normalize_time_period(raw))

    def test_normalize_handles_empty_and_none(self) -> None:
        self.assertIsNone(normalize_time_period(None))
        self.assertIsNone(normalize_time_period("   "))

    def test_unrecognized_value_is_trimmed_not_dropped(self) -> None:
        self.assertEqual("FY25", normalize_time_period(" FY25 "))


if __name__ == "__main__":
    unittest.main()
