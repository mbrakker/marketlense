from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = ROOT / "Wordpress" / "scripts" / "audit-report-card-contracts.php"


def test_report_card_audit_script_checks_complete_published_contract() -> None:
    source = AUDIT_SCRIPT.read_text(encoding="utf-8")

    required_keys = (
        "ml_card_schema_version",
        "ml_card_title_scale",
        "ml_card_tldr_compact",
        "ml_card_tldr_standard",
        "ml_card_key_insights",
        "ml_card_geography_scope",
        "ml_card_cover_fingerprint",
        "ml_card_cover_small_id",
        "ml_card_cover_medium_id",
        "ml_card_cover_large_id",
    )
    for key in required_keys:
        assert f"'{key}'" in source
    assert "$required_keys" in source
    assert "wp_attachment_is_image" in source
    assert "post_id" in source
    assert "post_title" in source
    assert "0 invalid published reports" in source
    assert "exit(1)" in source
