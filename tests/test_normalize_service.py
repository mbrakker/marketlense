import unittest

from src.contracts.normalize import NormalizeRequest
from src.contracts.report_models import Figure, Quote, ReportPayload
from src.contracts.run_context import RunContext
from src.services.normalize_service import normalize_report


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
        req = NormalizeRequest(schema_version="1.0", payload=payload)
        ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")
        resp = normalize_report(req, ctx)
        self.assertEqual(5, len(resp.payload.insights))

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
        req = NormalizeRequest(schema_version="1.0", payload=payload)
        ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")
        resp = normalize_report(req, ctx)
        self.assertEqual("img.png", resp.payload._figure_top)


if __name__ == "__main__":
    unittest.main()
