import unittest

from src.utils.time_period import normalize_time_period


class TestTimePeriodUtils(unittest.TestCase):
    def test_normalize_supported_formats(self) -> None:
        cases = {
            "2025": "2025",
            "2025 to 2026": "2025–2026",
            "2021-2025": "2021–2025",
            "Q2 2024": "Q2 2024",
            "2024 Q3": "Q3 2024",
            "Q1 to Q3 2026": "Q1–Q3 2026",
            "Q1-Q3 2026": "Q1–Q3 2026",
            "Q4 2025 to Q2 2026": "Q4 2025–Q2 2026",
            "H2 2025": "H2 2025",
            "Fiscal Year 2025": "FY2025",
            "June 2023": "June 2023",
            "2023 Sep": "September 2023",
            "June to November 2023": "June–November 2023",
            "June 2023 to November 2024": "June 2023–November 2024",
            "2026 (looking ahead / next 12 months, fieldwork Oct 2025)": "2026",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(expected, normalize_time_period(raw))

    def test_normalize_handles_empty_and_none(self) -> None:
        self.assertIsNone(normalize_time_period(None))
        self.assertIsNone(normalize_time_period("   "))

    def test_unrecognized_value_is_omitted(self) -> None:
        self.assertIsNone(normalize_time_period(" FY25 "))

    def test_long_malformed_model_value_is_omitted_with_multiple_years(
        self,
    ) -> None:
        value = (
            "2025 (primary coverage) with outlook into 2026 and beyond; "
            "return a valid JSON object with no text after it. "
            "The response must be complete and schema-valid."
        )

        self.assertIsNone(normalize_time_period(value))


if __name__ == "__main__":
    unittest.main()
