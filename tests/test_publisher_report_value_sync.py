from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "src" / "contracts" / "_report_store" / "sources.py"
SERVICE = ROOT / "src" / "services" / "_report_store_service" / "sources.py"
SYNC = ROOT / "Wordpress" / "scripts" / "admin" / "sync_profiles.py"
TAXONOMIES = (
    ROOT
    / "Wordpress"
    / "wp-content"
    / "plugins"
    / "marketlense-core"
    / "includes"
    / "class-marketlense-core-taxonomies.php"
)


def test_publisher_report_value_aggregate_has_a_typed_service_contract() -> None:
    assert "PublicPublisherReportValueAggregateRequest" in CONTRACTS.read_text(
        encoding="utf-8"
    )
    assert "list_public_publisher_report_value_aggregates" in SERVICE.read_text(
        encoding="utf-8"
    )


def test_profile_sync_publishes_only_registered_public_report_value_meta() -> None:
    sync = SYNC.read_text(encoding="utf-8")
    taxonomy = TAXONOMIES.read_text(encoding="utf-8")

    for key in (
        "ml_publisher_report_value_score",
        "ml_publisher_report_value_band",
        "ml_publisher_report_value_sample_size",
    ):
        assert key in sync
        assert key in taxonomy


def test_profile_sync_can_update_quality_without_refetching_existing_logos() -> None:
    sync = SYNC.read_text(encoding="utf-8")

    assert 'PUBLISHER_ICON_INLINE_FETCH' in sync
    assert 'script_root.parent / "config"' in sync
    assert "retry_payload" in sync
    assert "ml_publisher_homepage" in sync
