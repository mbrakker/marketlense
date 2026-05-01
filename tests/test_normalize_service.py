import unittest
from typing import Any

from src.contracts.report_models import Figure, Quote, ReportFigureAsset, ReportPayload
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

    def test_normalize_coerces_figure_assets(self) -> None:
        asset_row: Any = {
            "image_path": "report/slices/primary.png",
            "page": "2",
            "candidate_id": "chart-1",
            "kind": "chart",
            "is_primary": True,
            "detected_caption": "Detected",
            "preview_text": "Preview",
            "generated_caption": "Generated",
            "display_caption": "Generated",
            "caption_source": "generated",
            "schema_version": "1.0",
        }
        payload = ReportPayload(
            tldr="tldr",
            title="My Report",
            insights=["a", "b", "c", "d", "e"],
            quote=Quote(text="q", author="a"),
            figure=Figure(title="t", evidence="e"),
            commentary="c",
            source="s",
            _figure_assets=[asset_row],
        )
        ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")
        normalized = normalize_report(payload, ctx)

        self.assertEqual(1, len(normalized._figure_assets))
        self.assertIsInstance(normalized._figure_assets[0], ReportFigureAsset)
        self.assertEqual(2, normalized._figure_assets[0].page)
        self.assertEqual("Generated", normalized._figure_assets[0].display_caption)

    def test_normalize_backfills_enabled_figure_contract_from_primary_asset(
        self,
    ) -> None:
        asset = ReportFigureAsset(
            image_path="report/slices/primary.png",
            page=2,
            candidate_id="chart-1",
            kind="chart",
            is_primary=True,
            detected_caption="Detected caption",
            preview_text="Preview evidence",
            display_caption="Display caption",
            caption_source="detected",
        )
        payload = ReportPayload(
            tldr="tldr",
            title="Market Outlook",
            insights=["a", "b", "c", "d", "e"],
            quote=Quote(text="q", author="a"),
            figure=Figure(title="", evidence=""),
            commentary="c",
            source="s",
            _figure_assets=[asset],
            _figure_section_enabled=True,
        )
        ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")

        normalized = normalize_report(payload, ctx)

        self.assertEqual("Display caption", normalized.figure.title)
        self.assertEqual("Preview evidence", normalized.figure.evidence)

    def test_normalize_backfills_enabled_figure_contract_from_top_image(
        self,
    ) -> None:
        payload = ReportPayload(
            tldr="tldr",
            title="Market Outlook",
            insights=["a", "b", "c", "d", "e"],
            quote=Quote(text="q", author="a"),
            figure=Figure(title="", evidence=""),
            commentary="c",
            source="s",
            _figure_top="assets/primary.png",
            _figure_section_enabled=True,
        )
        ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")

        normalized = normalize_report(payload, ctx)

        self.assertEqual("Figure from Market Outlook", normalized.figure.title)
        self.assertEqual(
            "Visual asset primary.png extracted from the Market Outlook.",
            normalized.figure.evidence,
        )

    def test_normalize_does_not_backfill_disabled_figure_contract(self) -> None:
        payload = ReportPayload(
            tldr="tldr",
            title="Market Outlook",
            insights=["a", "b", "c", "d", "e"],
            quote=Quote(text="q", author="a"),
            figure=Figure(title="", evidence=""),
            commentary="c",
            source="s",
            _figure_top="assets/primary.png",
            _figure_section_enabled=False,
        )
        ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")

        normalized = normalize_report(payload, ctx)

        self.assertEqual("", normalized.figure.title)
        self.assertEqual("", normalized.figure.evidence)

    def test_normalize_preserves_internal_analysis_metadata(self) -> None:
        payload = ReportPayload(
            tldr="tldr",
            title="My Report",
            insights=["a", "b", "c", "d", "e"],
            quote=Quote(text="q", author="a"),
            figure=Figure(title="t", evidence="e"),
            commentary="c",
            source="s",
            _vector_store_id="vs_123",
            _evidence_packs={"doc_map": "out/report_analysis/doc_map.json"},
            _text_density=12.5,
            _text_pages_sampled=3,
            _text_char_count=450,
            _text_not_available=True,
        )
        ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")

        normalized = normalize_report(payload, ctx)

        self.assertEqual("vs_123", normalized._vector_store_id)
        self.assertEqual(
            {"doc_map": "out/report_analysis/doc_map.json"},
            normalized._evidence_packs,
        )
        self.assertEqual(12.5, normalized._text_density)
        self.assertEqual(3, normalized._text_pages_sampled)
        self.assertEqual(450, normalized._text_char_count)
        self.assertTrue(normalized._text_not_available)


if __name__ == "__main__":
    unittest.main()
