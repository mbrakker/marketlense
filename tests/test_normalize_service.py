import unittest

from src.contracts.report_models import Figure, Quote, ReportPayload
from src.contracts.run_context import RunContext
from src.generators.normalize_generator import normalize_report


class TestNormalizeService(unittest.TestCase):
    def test_normalize_pads_insights(self) -> None:
        payload = ReportPayload(
            tldr="tldr",
            title="My Report",
            insights=["a"],
            quote=Quote(text="q", author="a"),
            figure=Figure(title="t", evidence="e"),
            commentary="c",
            source="s",
        )
        ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")
        normalized = normalize_report(payload, ctx)
        self.assertEqual(5, len(normalized.insights))

    def test_normalize_sets_top_figure(self) -> None:
        payload = ReportPayload(
            tldr="tldr",
            title="My Report",
            insights=["a", "b", "c", "d", "e"],
            quote=Quote(text="q", author="a"),
            figure=Figure(title="t", evidence="e"),
            commentary="c",
            source="s",
            _figure_image="img.png",
            _figure_top="",
        )
        ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")
        normalized = normalize_report(payload, ctx)
        self.assertEqual("img.png", normalized._figure_top)

    def test_normalize_taxonomy_dedupes_and_strips(self) -> None:
        payload = ReportPayload(
            tldr="tldr",
            title="  My Report  ",
            insights=["a", "b", "c", "d", "e"],
            quote=Quote(text="q", author="a"),
            figure=Figure(title="t", evidence="e"),
            commentary="c",
            source="s",
            publisher="  Org ",
            taxonomy=["Ads", "ads", "  measurement "],
            region="  US ",
            time_period=" 2024E ",
        )
        ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")
        normalized = normalize_report(payload, ctx)
        self.assertEqual(["Ads", "measurement"], normalized.taxonomy)
        self.assertEqual("Org", normalized.publisher)
        self.assertEqual("US", normalized.region)
        self.assertEqual("2024E", normalized.time_period)
        self.assertEqual("My Report", normalized.title)

    def test_normalize_preserves_figure_section_enabled(self) -> None:
        payload = ReportPayload(
            tldr="tldr",
            title="My Report",
            insights=["a", "b", "c", "d", "e"],
            quote=Quote(text="q", author="a"),
            figure=Figure(title="t", evidence="e"),
            commentary="c",
            source="s",
            _figure_section_enabled=False,
        )
        ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")
        normalized = normalize_report(payload, ctx)
        self.assertFalse(normalized._figure_section_enabled)


if __name__ == "__main__":
    unittest.main()
