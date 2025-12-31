import unittest

from src.contracts.report_models import Figure, Quote, ReportPayload
from src.contracts.run_context import RunContext
from src.generators.normalize_generator import normalize_report


class TestNormalizeService(unittest.TestCase):
    def test_normalize_pads_insights(self) -> None:
        payload = ReportPayload(
            tldr="tldr",
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


if __name__ == "__main__":
    unittest.main()
