import unittest

from src.contracts.validation import ValidationReport
from src.contracts.candidates import Candidate
from src.contracts.report_models import Figure, Quote, ReportPayload
from src.utils.validation import (
    parse_validation_report_payload,
    validate_candidate,
    validate_report_payload,
)


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

    def test_parse_validation_report_payload_normalizes_known_fields(self) -> None:
        report = parse_validation_report_payload(
            {
                "schema_version": "1.1",
                "status": "fail",
                "severity": "warning",
                "issues": [
                    {
                        "schema_version": "1.0",
                        "message": "bad data",
                        "severity": "error",
                        "affected_section": "insights",
                        "rule_id": "VAL-001",
                        "repair_target": "summary",
                        "entity_id": "item-1",
                    }
                ],
            },
            source_path="validation.json",
        )

        self.assertIsInstance(report, ValidationReport)
        self.assertEqual("fail", report.status)
        self.assertEqual("warning", report.severity)
        self.assertEqual("validation.json", report.source_path)
        self.assertEqual(1, len(report.issues))
        self.assertEqual("VAL-001", report.issues[0].rule_id)
        self.assertEqual("summary", report.issues[0].repair_target)
        self.assertEqual("item-1", report.issues[0].entity_id)

    def test_parse_validation_report_payload_falls_back_for_invalid_root(self) -> None:
        report = parse_validation_report_payload([], source_path="validation.json")

        self.assertEqual("fail", report.status)
        self.assertEqual("error", report.severity)
        self.assertEqual([], report.issues)


if __name__ == "__main__":
    unittest.main()
