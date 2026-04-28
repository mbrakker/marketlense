from __future__ import annotations

from src.utils.tag_utils import normalize_slug_tag


def test_normalize_slug_tag_normalizes_spacing_punctuation_and_case() -> None:
    assert (
        normalize_slug_tag(" Generative AI and AI agents ")
        == "generative_ai_and_ai_agents"
    )


def test_normalize_slug_tag_handles_unicode_width_and_symbols() -> None:
    assert normalize_slug_tag("ＡI / Retail & Commerce") == "ai_retail_commerce"
