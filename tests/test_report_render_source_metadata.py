from __future__ import annotations

from types import SimpleNamespace

from src.generators.report_render_generator import _public_source_note


def test_public_source_note_discloses_unavailable_public_url() -> None:
    runtime = SimpleNamespace(
        source_url="",
        source_identity=SimpleNamespace(
            canonical_title="Publisher Evidence Report",
            publisher_name="Acme Research",
            canonical_landing_page_url="",
            source_page_url="",
            identity_status="resolved",
        ),
    )

    assert _public_source_note(runtime) == (
        "Source: Acme Research — Publisher Evidence Report — Source URL: Not available"
    )
