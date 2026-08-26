# ruff: noqa: F401,F403,F405
from __future__ import annotations

from dataclasses import replace

from src.utils.errors import AppError

from ._shared import *  # noqa: F401,F403


def test_publish_cohort_manifest_limits_selection_to_cohort_members(
    publish_settings_factory, run_context, wordpress_http, tmp_path, caplog
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_html(settings.output_dir, "other.html", "Drive fileId: other-file")
    target_path = _write_html(
        settings.output_dir, "target.html", "Drive fileId: target-file"
    )
    _record_processed(settings.state_db, "other-file", run_context)
    _record_processed(settings.state_db, "target-file", run_context)
    cohort_manifest = tmp_path / "cohort.json"
    cohort_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "cohort_id": "cohort-target-only",
                "validation_run_id": "validation:cohort-target-only",
                "configuration_hash": "configuration-hash",
                "policy_hash": "policy-hash",
                "members": [
                    {
                        "schema_version": "1.0",
                        "file_id": "target-file",
                        "source_identity_id": "target-file",
                        "md5_checksum": "target-md5",
                        "html_path": str(target_path),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    create_validation_run_manifest(
        ValidationRunManifestCreateRequest(
            schema_version="1.0",
            db_path=settings.reports_db,
            validation_run_id="validation:cohort-target-only",
            cohort_id="cohort-target-only",
            workflow_run_id=run_context.run_id,
            configuration_hash="configuration-hash",
            policy_hash="policy-hash",
            producer_build_identity="workspace",
            created_at_utc="2026-07-26T12:00:00Z",
        ),
        run_context,
    )
    _record_final_validation_attempt(
        settings,
        validation_run_id="validation:cohort-target-only",
        cohort_id="cohort-target-only",
        file_id="target-file",
        ctx=run_context,
    )
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 10, "link": "https://example.com/post/10", "status": "publish"},
    )

    def readback(_call: RecordedHttpRequest) -> FakeHttpResponse:
        payload = wordpress_http.calls_for(
            "POST", "https://example.com/wp-json/wp/v2/ml_report"
        )[0].json_data
        return FakeHttpResponse.from_payload(
            status_code=200,
            payload={
                "id": 10,
                "type": "ml_report",
                "status": payload["status"],
                "link": "https://example.com/post/10",
                "featured_media": payload.get("featured_media", 0),
                "categories": payload.get("categories", []),
                "tags": payload.get("tags", []),
                "content": {"raw": payload["content"], "rendered": payload["content"]},
                "meta": payload["meta"],
            },
        )

    wordpress_http.add(
        "GET", "https://example.com/wp-json/wp/v2/ml_report/10", readback
    )
    with caplog.at_level(logging.INFO, logger=orch.logger.name):
        outcomes = orch.run_publish(
            settings, ctx=run_context, cohort_manifest=str(cohort_manifest)
        )
    assert [(outcome.file_id, outcome.status) for outcome in outcomes] == [
        ("target-file", "published")
    ]
    assert (
        len(
            wordpress_http.calls_for(
                "POST", "https://example.com/wp-json/wp/v2/ml_report"
            )
        )
        == 1
    )
    assert (
        len(
            wordpress_http.calls_for(
                "GET", "https://example.com/wp-json/wp/v2/ml_report"
            )
        )
        == 1
    )
    assert (
        len(
            wordpress_http.calls_for(
                "GET", "https://example.com/wp-json/wp/v2/ml_report/10"
            )
        )
        == 1
    )
    assert outcomes[0].authenticated_readback_verified is True
    events = _json_events(caplog, orch.logger.name)
    assert not any(
        event.get("event") == "publish_auto_discovery_ordered" for event in events
    )
    cohort_event = next(
        event
        for event in events
        if event.get("event") == "publish_cohort_selection_applied"
    )
    assert cohort_event["fields"] == {
        "cohort_member_count": 1,
        "candidates_before_filter": 1,
        "selected_candidates": 1,
        "excluded_candidates": 0,
    }
    binding_event = next(
        event
        for event in events
        if event.get("event") == "publish_cohort_binding_resolved"
    )
    assert binding_event["fields"]["silent_exclusion_count"] == 0
    assert binding_event["fields"]["unrelated_candidate_count"] == 0
    binding_payload = json.loads(
        Path(binding_event["fields"]["binding_path"]).read_text(encoding="utf-8")
    )
    assert (
        binding_payload["candidate_set_hash"]
        == binding_event["fields"]["candidate_set_hash"]
    )
    assert [candidate["file_id"] for candidate in binding_payload["candidates"]] == [
        "target-file"
    ]


def test_publish_cohort_manifest_rejects_a_missing_member_before_wordpress_write(
    publish_settings_factory, run_context, wordpress_http, tmp_path
) -> None:
    """Removing an admitted artifact must block the entire cohort, not skip it."""
    settings = publish_settings_factory(validation_policy="warn")
    target_path = _write_html(
        settings.output_dir, "target.html", "Drive fileId: target-file"
    )
    _record_processed(settings.state_db, "target-file", run_context)
    cohort_manifest = tmp_path / "cohort.json"
    cohort_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "cohort_id": "cohort-two-members",
                "validation_run_id": "validation:cohort-two-members",
                "configuration_hash": "configuration-hash",
                "policy_hash": "policy-hash",
                "members": [
                    {
                        "file_id": "target-file",
                        "report_id": "target-file",
                        "source_identity_id": "target-file",
                        "html_path": str(target_path),
                    },
                    {
                        "file_id": "missing-file",
                        "report_id": "missing-file",
                        "source_identity_id": "missing-file",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    create_validation_run_manifest(
        ValidationRunManifestCreateRequest(
            schema_version="1.0",
            db_path=settings.reports_db,
            validation_run_id="validation:cohort-two-members",
            cohort_id="cohort-two-members",
            workflow_run_id=run_context.run_id,
            configuration_hash="configuration-hash",
            policy_hash="policy-hash",
            producer_build_identity="workspace",
            created_at_utc="2026-07-26T12:00:00Z",
        ),
        run_context,
    )
    _record_final_validation_attempt(
        settings,
        validation_run_id="validation:cohort-two-members",
        cohort_id="cohort-two-members",
        file_id="target-file",
        ctx=run_context,
    )

    with pytest.raises(AppError, match="artifact") as exc_info:
        orch.run_publish(
            settings, ctx=run_context, cohort_manifest=str(cohort_manifest)
        )

    assert exc_info.value.code == "validation_cohort_publication_artifact_missing"
    assert not wordpress_http.calls


def test_publish_cohort_rejects_changed_artifact_mapping_before_wordpress_write(
    publish_settings_factory, run_context, wordpress_http, tmp_path
) -> None:
    """A member cannot switch from its retained artifact to another report's HTML."""
    settings = publish_settings_factory(validation_policy="warn")
    changed_path = _write_html(
        settings.output_dir, "changed.html", "Drive fileId: changed-file"
    )
    _record_processed(settings.state_db, "target-file", run_context)
    cohort_manifest = tmp_path / "cohort.json"
    cohort_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "cohort_id": "cohort-changed-mapping",
                "validation_run_id": "validation:cohort-changed-mapping",
                "configuration_hash": "configuration-hash",
                "policy_hash": "policy-hash",
                "members": [
                    {
                        "file_id": "target-file",
                        "report_id": "target-file",
                        "source_identity_id": "target-file",
                        "html_path": str(changed_path),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    create_validation_run_manifest(
        ValidationRunManifestCreateRequest(
            schema_version="1.0",
            db_path=settings.reports_db,
            validation_run_id="validation:cohort-changed-mapping",
            cohort_id="cohort-changed-mapping",
            workflow_run_id=run_context.run_id,
            configuration_hash="configuration-hash",
            policy_hash="policy-hash",
            producer_build_identity="workspace",
            created_at_utc="2026-07-26T12:00:00Z",
        ),
        run_context,
    )
    _record_final_validation_attempt(
        settings,
        validation_run_id="validation:cohort-changed-mapping",
        cohort_id="cohort-changed-mapping",
        file_id="target-file",
        ctx=run_context,
    )

    with pytest.raises(AppError, match="identity") as exc_info:
        orch.run_publish(
            settings, ctx=run_context, cohort_manifest=str(cohort_manifest)
        )

    assert exc_info.value.code == "validation_cohort_publication_identity_mismatch"
    assert not wordpress_http.calls


def test_publish_cohort_rejects_duplicate_artifact_mapping_before_wordpress_write(
    publish_settings_factory, run_context, wordpress_http, tmp_path
) -> None:
    """A manifest path and a different report-store path are an ambiguous binding."""
    settings = publish_settings_factory(validation_policy="warn")
    manifest_path = _write_html(
        settings.output_dir, "manifest.html", "Drive fileId: target-file"
    )
    metadata_path = _write_html(
        settings.output_dir, "metadata.html", "Drive fileId: target-file"
    )
    _seed_report_metadata(
        settings.reports_db, str(metadata_path), "target-file", run_context
    )
    _record_processed(settings.state_db, "target-file", run_context)
    cohort_manifest = tmp_path / "cohort.json"
    cohort_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "cohort_id": "cohort-duplicate-mapping",
                "validation_run_id": "validation:cohort-duplicate-mapping",
                "configuration_hash": "configuration-hash",
                "policy_hash": "policy-hash",
                "members": [
                    {
                        "file_id": "target-file",
                        "report_id": "target-file",
                        "source_identity_id": "target-file",
                        "html_path": str(manifest_path),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    create_validation_run_manifest(
        ValidationRunManifestCreateRequest(
            schema_version="1.0",
            db_path=settings.reports_db,
            validation_run_id="validation:cohort-duplicate-mapping",
            cohort_id="cohort-duplicate-mapping",
            workflow_run_id=run_context.run_id,
            configuration_hash="configuration-hash",
            policy_hash="policy-hash",
            producer_build_identity="workspace",
            created_at_utc="2026-07-26T12:00:00Z",
        ),
        run_context,
    )
    _record_final_validation_attempt(
        settings,
        validation_run_id="validation:cohort-duplicate-mapping",
        cohort_id="cohort-duplicate-mapping",
        file_id="target-file",
        ctx=run_context,
    )

    with pytest.raises(AppError, match="multiple") as exc_info:
        orch.run_publish(
            settings, ctx=run_context, cohort_manifest=str(cohort_manifest)
        )

    assert exc_info.value.code == "validation_cohort_publication_artifact_ambiguous"
    assert not wordpress_http.calls


def test_publish_cohort_manifest_rejects_stale_source_mapping_before_wordpress_write(
    publish_settings_factory, run_context, wordpress_http, tmp_path
) -> None:
    """A retained source checksum cannot be replaced by stale report metadata."""
    settings = publish_settings_factory(validation_policy="warn")
    target_path = _write_html(
        settings.output_dir, "target.html", "Drive fileId: target-file"
    )
    _seed_report_metadata(
        settings.reports_db, str(target_path), "target-file", run_context
    )
    _record_processed(settings.state_db, "target-file", run_context)
    cohort_manifest = tmp_path / "cohort.json"
    cohort_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "cohort_id": "cohort-stale-mapping",
                "validation_run_id": "validation:cohort-stale-mapping",
                "configuration_hash": "configuration-hash",
                "policy_hash": "policy-hash",
                "members": [
                    {
                        "file_id": "target-file",
                        "report_id": "target-file",
                        "source_identity_id": "target-md5",
                        "md5_checksum": "target-md5",
                        "html_path": str(target_path),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    create_validation_run_manifest(
        ValidationRunManifestCreateRequest(
            schema_version="1.0",
            db_path=settings.reports_db,
            validation_run_id="validation:cohort-stale-mapping",
            cohort_id="cohort-stale-mapping",
            workflow_run_id=run_context.run_id,
            configuration_hash="configuration-hash",
            policy_hash="policy-hash",
            producer_build_identity="workspace",
            created_at_utc="2026-07-26T12:00:00Z",
        ),
        run_context,
    )
    _record_final_validation_attempt(
        settings,
        validation_run_id="validation:cohort-stale-mapping",
        cohort_id="cohort-stale-mapping",
        file_id="target-file",
        ctx=run_context,
    )

    with pytest.raises(AppError, match="incompatible") as exc_info:
        orch.run_publish(
            settings, ctx=run_context, cohort_manifest=str(cohort_manifest)
        )

    assert exc_info.value.code == "validation_cohort_publication_mapping_incompatible"
    assert not wordpress_http.calls


def test_publish_cohort_manifest_binding_hash_is_deterministic_for_unchanged_artifacts(
    publish_settings_factory, run_context, tmp_path
) -> None:
    """The identical admitted mapping must retain the same candidate-set digest."""
    settings = publish_settings_factory(validation_policy="warn")
    target_path = _write_html(
        settings.output_dir, "target.html", "Drive fileId: target-file"
    )
    second_path = _write_html(
        settings.output_dir, "second.html", "Drive fileId: second-file"
    )
    _record_processed(settings.state_db, "target-file", run_context)
    _record_processed(settings.state_db, "second-file", run_context)
    members = {
        "target-file": {
            "file_id": "target-file",
            "report_id": "target-file",
            "source_identity_id": "target-file",
            "html_path": str(target_path),
        },
        "second-file": {
            "file_id": "second-file",
            "report_id": "second-file",
            "source_identity_id": "second-file",
            "html_path": str(second_path),
        },
    }
    cohort_manifest = tmp_path / "cohort.json"
    cohort_manifest.write_text(
        json.dumps({"members": list(members.values())}), encoding="utf-8"
    )
    binding_ctx = replace(
        run_context,
        configuration_hash="configuration-hash",
        policy_hash="policy-hash",
    )

    first_candidates, first_hash, binding_path = orch._bind_cohort_publish_candidates(
        settings=settings,
        cohort_manifest=str(cohort_manifest),
        cohort_id="cohort-hash",
        configuration_hash="configuration-hash",
        policy_hash="policy-hash",
        members=members,
        html_file_id_map={},
        metadata_by_file_id={},
        report_readiness_references=None,
        ctx=binding_ctx,
    )
    second_candidates, second_hash, _ = orch._bind_cohort_publish_candidates(
        settings=settings,
        cohort_manifest=str(cohort_manifest),
        cohort_id="cohort-hash",
        configuration_hash="configuration-hash",
        policy_hash="policy-hash",
        members=members,
        html_file_id_map={},
        metadata_by_file_id={},
        report_readiness_references=None,
        ctx=binding_ctx,
    )

    assert [candidate.file_id for candidate in first_candidates] == [
        "target-file",
        "second-file",
    ]
    assert [candidate.file_id for candidate in second_candidates] == [
        "target-file",
        "second-file",
    ]
    assert first_hash == second_hash
    assert (
        json.loads(Path(binding_path).read_text(encoding="utf-8"))["candidate_set_hash"]
        == first_hash
    )


def test_publish_cohort_manifest_rejects_not_ready_member_before_wordpress_write(
    publish_settings_factory, run_context, wordpress_http, tmp_path
) -> None:
    """A complete artifact still cannot be silently omitted when readiness fails."""
    settings = publish_settings_factory(validation_policy="warn")
    target_path = _write_html(
        settings.output_dir, "target.html", "Drive fileId: target-file"
    )
    cohort_manifest = tmp_path / "cohort.json"
    cohort_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "cohort_id": "cohort-not-ready",
                "validation_run_id": "validation:cohort-not-ready",
                "configuration_hash": "configuration-hash",
                "policy_hash": "policy-hash",
                "members": [
                    {
                        "file_id": "target-file",
                        "report_id": "target-file",
                        "source_identity_id": "target-file",
                        "html_path": str(target_path),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    create_validation_run_manifest(
        ValidationRunManifestCreateRequest(
            schema_version="1.0",
            db_path=settings.reports_db,
            validation_run_id="validation:cohort-not-ready",
            cohort_id="cohort-not-ready",
            workflow_run_id=run_context.run_id,
            configuration_hash="configuration-hash",
            policy_hash="policy-hash",
            producer_build_identity="workspace",
            created_at_utc="2026-07-26T12:00:00Z",
        ),
        run_context,
    )
    _record_final_validation_attempt(
        settings,
        validation_run_id="validation:cohort-not-ready",
        cohort_id="cohort-not-ready",
        file_id="target-file",
        ctx=run_context,
    )

    with pytest.raises(AppError, match="publish-ready") as exc_info:
        orch.run_publish(
            settings, ctx=run_context, cohort_manifest=str(cohort_manifest)
        )

    assert exc_info.value.code == "validation_cohort_publication_not_ready"
    assert not wordpress_http.calls
