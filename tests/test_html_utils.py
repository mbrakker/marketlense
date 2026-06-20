import unittest

from src.utils.html_utils import (
    build_publish_html_snapshot,
    extract_publish_entity_metadata,
    extract_body_html,
    extract_file_id,
    extract_image_sources,
    extract_preview_image,
    extract_title,
    replace_image_sources,
    strip_image_srcset_and_sizes,
)


class TestHtmlUtils(unittest.TestCase):
    def test_extract_title_and_body(self) -> None:
        html = "<html><head><title>Doc</title></head><body><h1>Doc</h1><p>Hi</p></body></html>"
        self.assertEqual("Doc", extract_title(html))
        self.assertIn("<p>Hi</p>", extract_body_html(html))

    def test_extract_file_id(self) -> None:
        html = "Drive fileId: abc123"
        self.assertEqual("abc123", extract_file_id(html))

    def test_image_sources_and_replace(self) -> None:
        html = '<img src="a.png" srcset="a.png 1x, a@2x.png 2x"><img src="b.png">'
        sources = extract_image_sources(html)
        self.assertEqual(["a.png", "b.png"], sources)
        replaced = replace_image_sources(
            html,
            {
                "a.png": "https://cdn.example/x.png",
                "a@2x.png": "https://cdn.example/x@2x.png",
            },
        )
        self.assertIn('src="https://cdn.example/x.png"', replaced)
        self.assertIn(
            'srcset="https://cdn.example/x.png 1x, https://cdn.example/x@2x.png 2x"',
            replaced,
        )

    def test_extract_preview_image(self) -> None:
        html = '<div class="preview"><img src="prev.png"></div>'
        self.assertEqual("prev.png", extract_preview_image(html))

    def test_strip_image_srcset_and_sizes(self) -> None:
        html = (
            '<img src="cover.png" srcset="cover.png 1x, cover@2x.png 2x" '
            'sizes="100vw" alt="cover">'
        )
        stripped = strip_image_srcset_and_sizes(html)
        self.assertIn('src="cover.png"', stripped)
        self.assertNotIn("srcset=", stripped)
        self.assertNotIn("sizes=", stripped)

    def test_extract_publish_entity_metadata(self) -> None:
        html = (
            '<script type="application/json" '
            'data-market-lense-publish-entity="true">'
            '{"schema_version":"1.0","entity_type":"signal",'
            '"source_artifact_id":"signal:checkout-trust",'
            '"canonical_route_intent":"wordpress:ml_signal",'
            '"publish_eligible":true}'
            "</script>"
        )

        metadata = extract_publish_entity_metadata(html)

        self.assertIsNotNone(metadata)
        assert metadata is not None
        self.assertEqual(metadata.entity_type, "signal")
        self.assertEqual(metadata.source_artifact_id, "signal:checkout-trust")
        self.assertEqual(metadata.canonical_route_intent, "wordpress:ml_signal")
        self.assertTrue(metadata.publish_eligible)

    def test_snapshot_extracts_embedded_briefing_card(self) -> None:
        html = (
            '<html><body><script type="application/json" '
            'data-market-lense-cross-report-metadata="true">'
            '{"briefing_card":{"schema_version":"1.0",'
            '"summary_compact":"Compact summary.",'
            '"summary_standard":"Standard summary.",'
            '"decision_focus":"Prioritize the verified signal.",'
            '"takeaways":["First takeaway.","Second takeaway."],'
            '"source_count":4,"evidence_count":32,'
            '"covers":{"small":"covers/small.png",'
            '"medium":"covers/medium.png","large":"covers/large.png"}}}'
            '</script></body></html>'
        )

        snapshot = build_publish_html_snapshot(html)

        self.assertEqual(snapshot.briefing_card["schema_version"], "1.0")
        self.assertEqual(snapshot.briefing_card["source_count"], 4)
        self.assertEqual(snapshot.briefing_card["evidence_count"], 32)
        self.assertEqual(
            snapshot.briefing_card["covers"]["large"], "covers/large.png"
        )


if __name__ == "__main__":
    unittest.main()
