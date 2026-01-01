import unittest

from src.contracts.candidates import Candidate
from src.contracts.report_models import Figure, Quote, ReportPayload
from src.utils.validation import validate_candidate, validate_report_payload


class TestValidation(unittest.TestCase):
    def test_validate_report_payload_ok(self) -> None:
        payload = ReportPayload(
            tldr="tldr",
            title="My Report",
            insights=["a", "b", "c", "d", "e"],
            quote=Quote(text="q", author="a"),
            figure=Figure(title="t", evidence="e"),
            commentary="c",
            source="s",
        )
        validate_report_payload(payload)

    def test_validate_report_payload_bad_insights(self) -> None:
        payload = ReportPayload(
            tldr="tldr",
            title="My Report",
            insights=["a"],
            quote=Quote(text="q", author="a"),
            figure=Figure(title="t", evidence="e"),
            commentary="c",
            source="s",
        )
        with self.assertRaises(ValueError):
            validate_report_payload(payload)

    def test_validate_report_payload_requires_title(self) -> None:
        payload = ReportPayload(
            tldr="tldr",
            title="",
            insights=["a", "b", "c", "d", "e"],
            quote=Quote(text="q", author="a"),
            figure=Figure(title="t", evidence="e"),
            commentary="c",
            source="s",
        )
        with self.assertRaises(ValueError):
            validate_report_payload(payload)
    def test_validate_candidate_ok(self) -> None:
        cand = Candidate(
            schema_version="1.0",
            id="chart-0-1",
            kind="chart",
            page=0,
            bbox=(0.0, 0.0, 1.0, 1.0),
            preview_text="text",
        )
        validate_candidate(cand)

    def test_validate_candidate_bad_kind(self) -> None:
        cand = Candidate(
            schema_version="1.0",
            id="x",
            kind="other",
            page=0,
            bbox=(0.0, 0.0, 1.0, 1.0),
            preview_text="text",
        )
        with self.assertRaises(ValueError):
            validate_candidate(cand)


if __name__ == "__main__":
    unittest.main()
