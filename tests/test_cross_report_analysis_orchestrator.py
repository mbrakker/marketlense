from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisOrchestratorRequest,
    CrossReportAnalysisRequest,
    CrossReportEvidenceReference,
    CrossReportProjectedDataReadRequest,
    CrossReportProjectedDataReadResponse,
    CrossReportPublishResultSummary,
    CrossReportRawMetricReference,
    CrossReportSourceReportCandidate,
)
from src.contracts.analytics_projection import ClaimEmbeddingReadResponse
from src.contracts.openai import OpenAIResponseResult
from src.contracts.prompts import PromptRenderResponse, PromptSet, PromptTemplate
from src.orchestrators.cross_report_analysis_orchestrator import (
    run_cross_report_analysis,
)
from src.utils.errors import AppError


class FakePromptClient:
    def load_prompt_set(self, request, ctx):
        return PromptSet(
            schema_version="1.0",
            system=PromptTemplate(
                schema_version="1.0",
                path="src/prompts/cross_report_analysis/synthesis/system.yaml",
                text="system",
                sha256="system-hash",
            ),
            user=PromptTemplate(
                schema_version="1.0",
                path="src/prompts/cross_report_analysis/synthesis/user.yaml",
                text="user {{ evidence_json }}",
                sha256="user-hash",
            ),
        )

    def render_prompt(self, request, ctx):
        text = request.template.text
        for key, value in request.variables.items():
            text = text.replace("{{ " + key + " }}", str(value))
        return PromptRenderResponse(schema_version="1.0", text=text)


class CountingOpenAIClient:
    def __init__(self) -> None:
        self.calls = 0

    def openai_chat_json(self, request, ctx):
        self.calls += 1
        payload = {
            "analysis_id": "analysis-orchestrated-ai",
            "title": "AI Commerce Adoption Across Retail Reports",
            "slug": "ai-commerce-adoption-across-retail-reports",
            "executive_summary": "AI commerce adoption is visible across selected reports.",
            "decision_focus": "Prioritize the shared AI commerce adoption signal.",
            "executive_takeaways": [
                "AI appears across both selected reports.",
                "Raw metrics remain source-specific for decision review.",
            ],
            "sections": [
                {
                    "section_id": "key-cross-report-signals",
                    "heading": "Key cross-report signals",
                    "body": "AI appears across both selected reports.",
                    "evidence_ids": ["report-b:claim:1", "report-a:claim:1"],
                    "raw_metric_ids": [],
                },
                {
                    "section_id": "raw-metric-appendix",
                    "heading": "Raw metric appendix",
                    "body": "Raw metrics are kept source-specific.",
                    "evidence_ids": ["report-a:claim:1"],
                    "raw_metric_ids": ["report-a:metric:1"],
                },
            ],
            "evidence_map": {
                "signals": ["report-b:claim:1", "report-a:claim:1"],
            },
            "source_notes": ["Two projected reports were selected."],
        }
        return OpenAIResponseResult(
            schema_version="1.0",
            text=json.dumps(payload),
            parsed_json=payload,
            input_tokens=1000,
            output_tokens=300,
            total_tokens=1300,
            model=request.model,
            request_id=f"provider-{self.calls}",
        )


def _analysis_request() -> CrossReportAnalysisRequest:
    return _analysis_request_with_mode("generate_only")


def _analysis_request_with_mode(publication_mode: str) -> CrossReportAnalysisRequest:
    return CrossReportAnalysisRequest(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        request_id="orchestrator-request",
        topic="AI commerce adoption",
        auto_theme=True,
        category_filters=["Retail"],
        tag_filters=["AI"],
        publisher_filters=[],
        date_range_start="2026-05-01",
        date_range_end="2026-05-31",
        max_source_reports=2,
        diagnostic=False,
        override_publishability=False,
        publication_mode=publication_mode,
    )


def _orchestrator_request(tmp_path) -> CrossReportAnalysisOrchestratorRequest:
    return _orchestrator_request_with_mode(tmp_path, "generate_only")


def _orchestrator_request_with_mode(
    tmp_path,
    publication_mode: str,
) -> CrossReportAnalysisOrchestratorRequest:
    return CrossReportAnalysisOrchestratorRequest(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        analysis_request=_analysis_request_with_mode(publication_mode),
        projected_data_request=CrossReportProjectedDataReadRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            db_path=str(tmp_path / "reports.sqlite"),
            category_filters=["Retail"],
            tag_filters=["AI"],
            content_classes=["claim", "finding", "quote", "metric"],
            minimum_projection_status="projected",
        ),
        idempotency_db_path=str(tmp_path / "idempotency.sqlite"),
        output_root=str(tmp_path / "out"),
        max_evidence_items=6,
        max_signals=4,
        max_prompt_chars=60000,
        retry_retries=1,
        retry_base_delay_seconds=0.0,
        retry_backoff_step_seconds=0.0,
        retry_jitter_seconds=0.0,
    )


def _candidate(
    report_id: str, publisher: str, date: str
) -> CrossReportSourceReportCandidate:
    return CrossReportSourceReportCandidate(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        report_id=report_id,
        title=f"{report_id} title",
        publisher=publisher,
        publisher_id=publisher.lower().replace(" ", "-"),
        report_date=date,
        projection_status="projected",
        content_hash=f"{report_id}-hash",
        category_labels=["Retail"],
        tags=["AI"],
        evidence_count=3,
        claim_count=1,
        finding_count=1,
        quote_count=1,
        metric_count=1,
        recency_score=0.0,
        relevance_score=0.0,
        diversity_score=0.0,
        density_score=0.0,
        total_score=0.0,
        selection_reasons=["test"],
        rejection_reasons=[],
    )


def _evidence(
    evidence_id: str, report_id: str, text: str
) -> CrossReportEvidenceReference:
    return CrossReportEvidenceReference(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        evidence_id=evidence_id,
        report_id=report_id,
        publisher=f"{report_id} Publisher",
        title=f"{report_id} title",
        source_table="report_claims",
        entity_uid=evidence_id,
        content_class="claim",
        text=text,
        source_metadata={"page": 1},
    )


def _metric(report_id: str) -> CrossReportRawMetricReference:
    return CrossReportRawMetricReference(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        metric_id=f"{report_id}:metric:1",
        report_id=report_id,
        publisher=f"{report_id} Publisher",
        label="Adoption",
        raw_value="42",
        unit="percent",
        context="Source-specific survey response.",
        evidence_id=f"{report_id}:claim:1",
        source_metadata={"page": 2},
    )


def _projected_data() -> CrossReportProjectedDataReadResponse:
    return CrossReportProjectedDataReadResponse(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        source_candidates=[
            _candidate("report-a", "Publisher A", "2026-05-01"),
            _candidate("report-b", "Publisher B", "2026-05-04"),
        ],
        evidence=[
            _evidence("report-a:claim:1", "report-a", "AI adoption is increasing."),
            _evidence("report-a:finding:1", "report-a", "Retail teams pilot AI."),
            _evidence("report-a:quote:1", "report-a", "AI is changing commerce."),
            _evidence("report-b:claim:1", "report-b", "AI adoption is declining."),
            _evidence("report-b:finding:1", "report-b", "Budget pressure slows AI."),
            _evidence("report-b:quote:1", "report-b", "AI remains a priority."),
        ],
        raw_metrics=[_metric("report-a"), _metric("report-b")],
        content_hashes={
            "report-a": {"report-a:claim:1": "hash-a"},
            "report-b": {"report-b:claim:1": "hash-b"},
        },
        excluded_report_counts={},
    )


def _settings(tmp_path):
    return SimpleNamespace(
        openai_api_key="test-key",
        openai_model="gpt-5-mini",
        openai_models={},
        openai_seed=42,
        cross_report_analysis_prompt_namespace="cross_report_analysis/synthesis",
        cross_report_analysis_model="gpt-5-mini",
        cross_report_analysis_temperature=1.0,
        cross_report_analysis_timeout_seconds=600.0,
        cross_report_analysis_cache_enabled=True,
        cross_report_analysis_max_prompt_chars=60000,
        cross_report_analysis_max_evidence_items=6,
        cross_report_analysis_signal_score_weights={
            "recurrence": 1.0,
            "diversity": 1.0,
            "recency": 1.0,
            "taxonomy_fit": 1.0,
            "support": 1.0,
            "contradiction": 0.5,
        },
        cross_report_analysis_enabled=True,
        cross_report_analysis_auto_theme_enabled=True,
        cross_report_analysis_theme_rotation_window_days=30,
        cross_report_analysis_min_theme_source_publishers=2,
        cross_report_analysis_publish_enabled=False,
        cross_report_analysis_publish_requires_validation_pass=True,
        cache_dir=str(tmp_path / "cache"),
        cost_ledger_path=str(tmp_path / "cost-ledger.jsonl"),
        cost_daily_path=str(tmp_path / "cost-daily.json"),
        model_pricing={},
    )


def _events(caplog) -> list[dict]:
    return [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.cross_report_analysis_orchestrator"
    ]


def test_cross_report_orchestrator_blocks_when_feature_disabled(
    tmp_path,
    run_context,
    assert_app_error,
) -> None:
    settings = _settings(tmp_path)
    settings.cross_report_analysis_enabled = False
    read_calls = []

    with pytest.raises(AppError) as exc_info:
        run_cross_report_analysis(
            _orchestrator_request(tmp_path),
            settings,
            run_context,
            read_projected_data_fn=lambda request, ctx: read_calls.append(request),
            prompt_client=FakePromptClient(),
            openai_client=CountingOpenAIClient(),
            sleep_fn=lambda seconds: None,
        )

    assert_app_error(
        exc_info.value,
        code="cross_report_analysis_disabled",
        retryable=False,
        severity="error",
    )
    assert read_calls == []


def test_cross_report_orchestrator_rejects_auto_theme_when_disabled(
    tmp_path,
    run_context,
    assert_app_error,
) -> None:
    settings = _settings(tmp_path)
    settings.cross_report_analysis_auto_theme_enabled = False
    request = replace(
        _orchestrator_request(tmp_path),
        analysis_request=replace(
            _analysis_request(),
            topic="",
            auto_theme=True,
        ),
    )

    with pytest.raises(AppError) as exc_info:
        run_cross_report_analysis(
            request,
            settings,
            run_context,
            read_projected_data_fn=lambda request, ctx: _projected_data(),
            prompt_client=FakePromptClient(),
            openai_client=CountingOpenAIClient(),
            sleep_fn=lambda seconds: None,
        )

    assert_app_error(
        exc_info.value,
        code="cross_report_auto_theme_disabled",
        retryable=False,
        severity="error",
    )
    assert exc_info.value.context["auto_theme"] is True


def test_cross_report_orchestrator_wires_theme_rotation_settings(
    tmp_path,
    run_context,
    caplog,
) -> None:
    settings = _settings(tmp_path)
    settings.cross_report_analysis_theme_rotation_window_days = 30
    recent_artifact = (
        tmp_path / "out" / "cross_report_analysis" / "recent-ai" / "analysis.json"
    )
    recent_artifact.parent.mkdir(parents=True)
    recent_artifact.write_text(
        json.dumps(
            {
                "generated_at_utc": "2026-05-20T00:00:00Z",
                "generated_result": {
                    "selected_theme": {
                        "theme_id": "theme-tag-ai",
                        "matched_tags": ["AI"],
                        "matched_categories": ["Retail"],
                        "source_report_ids": ["report-old"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    request = replace(
        _orchestrator_request(tmp_path),
        analysis_request=replace(
            _analysis_request(),
            topic="",
            auto_theme=True,
            date_range_end="2026-05-21",
        ),
    )
    caplog.set_level(
        logging.INFO, logger="market_lense.cross_report_analysis_input_generator"
    )

    outcome = run_cross_report_analysis(
        request,
        settings,
        run_context,
        read_projected_data_fn=lambda request, ctx: _projected_data(),
        prompt_client=FakePromptClient(),
        openai_client=CountingOpenAIClient(),
        sleep_fn=lambda seconds: None,
    )

    assert outcome.generated_result.selected_theme.rejection_risks
    assert any(
        risk.startswith("recent_category_repetition:")
        for risk in outcome.generated_result.selected_theme.rejection_risks
    )
    events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.cross_report_analysis_input_generator"
    ]
    loaded = [
        event
        for event in events
        if event["event"] == "cross_report_recent_theme_metadata_loaded"
    ][0]
    assert loaded["fields"]["recent_artifacts_root"] == str(
        tmp_path / "out" / "cross_report_analysis"
    )
    assert loaded["fields"]["theme_rotation_window_days"] == 30
    assert loaded["fields"]["theme_rotation_reference_date"] == "2026-05-21"
    assert loaded["fields"]["loaded_recent_themes"] == 1


def test_cross_report_orchestrator_runs_pipeline_and_reuses_idempotency(
    tmp_path,
    run_context,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    openai_client = CountingOpenAIClient()
    calls = []

    def _read_projected(request, ctx):
        calls.append("read_projected_data")
        return _projected_data()

    caplog.set_level(
        logging.INFO, logger="market_lense.cross_report_analysis_orchestrator"
    )
    first = run_cross_report_analysis(
        _orchestrator_request(tmp_path),
        _settings(tmp_path),
        run_context,
        read_projected_data_fn=_read_projected,
        prompt_client=FakePromptClient(),
        openai_client=openai_client,
        sleep_fn=lambda seconds: None,
    )
    second = run_cross_report_analysis(
        _orchestrator_request(tmp_path),
        _settings(tmp_path),
        run_context,
        read_projected_data_fn=_read_projected,
        prompt_client=FakePromptClient(),
        openai_client=openai_client,
        sleep_fn=lambda seconds: None,
    )

    assert first.status == "validated"
    assert first.idempotency_reused is False
    assert second.idempotency_reused is True
    assert second.generated_result.analysis_id == first.generated_result.analysis_id
    assert openai_client.calls == 1
    assert first.idempotency_key == second.idempotency_key
    assert "generated" in first.state_transitions
    assert "artifact_persisted" in first.state_transitions
    assert "idempotency_recorded" in first.state_transitions
    assert "idempotency_reused" in second.state_transitions
    assert calls == ["read_projected_data", "read_projected_data"]
    artifact_path = Path(first.artifact_path)
    assert artifact_path == (
        tmp_path
        / "out"
        / "cross_report_analysis"
        / "ai-commerce-adoption-across-retail-reports"
        / "analysis.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["schema_version"] == CROSS_REPORT_ANALYSIS_SCHEMA_VERSION
    assert artifact["artifact_type"] == "cross_report_analysis"
    assert artifact["request_fingerprint"] == first.idempotency_key.split(":", 1)[1]
    assert artifact["selected_report_ids"] == ["report-b", "report-a"]
    assert (
        artifact["projection_content_hashes"]["report-a"]["report-a:claim:1"]
        == "hash-a"
    )
    assert artifact["prompt_hashes"] == {"system": "system-hash", "user": "user-hash"}
    assert artifact["validation_status"] == "pass"
    assert artifact["generated_result"]["analysis_id"] == "analysis-orchestrated-ai"
    assert second.artifact_path == first.artifact_path
    events = _events(caplog)
    assert_logs_have_required_fields(events)
    assert [
        event["event"]
        for event in events
        if event["event"].startswith("cross_report_orchestrator_")
    ][0] == "cross_report_orchestrator_start"
    idempotency_event = [
        event
        for event in events
        if event["event"] == "cross_report_orchestrator_transition"
        and event["fields"]["transition"] == "idempotency_checked"
    ][0]
    assert idempotency_event["fields"]["material_version"] == "2.1"
    assert "output_root" in idempotency_event["fields"]["material_fields"]
    assert "semantic_preselection" in idempotency_event["fields"]["material_fields"]


def test_cross_report_orchestrator_reads_claim_embeddings_for_preselection(
    tmp_path,
    run_context,
) -> None:
    read_embedding_calls = []

    def _read_claim_embeddings(request, ctx):
        read_embedding_calls.append(request)
        return ClaimEmbeddingReadResponse(schema_version="1.0", embeddings=[])

    outcome = run_cross_report_analysis(
        _orchestrator_request(tmp_path),
        _settings(tmp_path),
        run_context,
        read_projected_data_fn=lambda request, ctx: _projected_data(),
        read_claim_embeddings_fn=_read_claim_embeddings,
        prompt_client=FakePromptClient(),
        openai_client=CountingOpenAIClient(),
        sleep_fn=lambda seconds: None,
    )

    assert outcome.status == "validated"
    assert len(read_embedding_calls) == 1
    embedding_request = read_embedding_calls[0]
    assert embedding_request.db_path == str(tmp_path / "reports.sqlite")
    assert embedding_request.report_ids == ["report-b", "report-a"]
    assert embedding_request.topics == [
        "AI commerce adoption",
        "ai_commerce_adoption",
        "Retail",
        "AI",
    ]
    assert embedding_request.statuses == ["embedded"]
    assert embedding_request.limit == 24


def test_cross_report_orchestrator_idempotency_changes_for_output_controls(
    tmp_path,
    run_context,
) -> None:
    def _read_projected(request, ctx):
        return _projected_data()

    first_client = CountingOpenAIClient()
    second_client = CountingOpenAIClient()
    base_request = _orchestrator_request(tmp_path)
    changed_request = replace(
        base_request,
        output_root=str(tmp_path / "changed-out"),
        max_evidence_items=5,
        max_signals=3,
        max_prompt_chars=55000,
    )

    first = run_cross_report_analysis(
        base_request,
        _settings(tmp_path),
        run_context,
        read_projected_data_fn=_read_projected,
        prompt_client=FakePromptClient(),
        openai_client=first_client,
        sleep_fn=lambda seconds: None,
    )
    second = run_cross_report_analysis(
        changed_request,
        _settings(tmp_path),
        run_context,
        read_projected_data_fn=_read_projected,
        prompt_client=FakePromptClient(),
        openai_client=second_client,
        sleep_fn=lambda seconds: None,
    )

    assert first.idempotency_key != second.idempotency_key
    assert first_client.calls == 1
    assert second_client.calls == 1
    assert "changed-out" in second.artifact_path


def test_cross_report_orchestrator_blocks_prompt_budget_before_model_call(
    tmp_path,
    run_context,
    assert_app_error,
) -> None:
    openai_client = CountingOpenAIClient()
    request = replace(_orchestrator_request(tmp_path), max_prompt_chars=200)

    with pytest.raises(Exception) as exc:
        run_cross_report_analysis(
            request,
            _settings(tmp_path),
            run_context,
            read_projected_data_fn=lambda request_arg, ctx: _projected_data(),
            prompt_client=FakePromptClient(),
            openai_client=openai_client,
            sleep_fn=lambda seconds: None,
        )

    assert_app_error(
        exc.value,
        code="cross_report_prompt_budget_exceeded",
        retryable=False,
        severity="error",
    )
    assert exc.value.context["prompt_input_chars"] > 200
    assert exc.value.context["max_prompt_chars"] == 200
    assert openai_client.calls == 0
    assert not list((tmp_path / "out").glob("**/analysis.json"))


def test_cross_report_orchestrator_projection_hash_change_invalidates_cache(
    tmp_path,
    run_context,
) -> None:
    openai_client = CountingOpenAIClient()
    reads = {"count": 0}

    def _read_projected(request, ctx):
        reads["count"] += 1
        projected = _projected_data()
        if reads["count"] == 1:
            return projected
        return replace(
            projected,
            content_hashes={
                **projected.content_hashes,
                "report-a": {"report-a:claim:1": "hash-a-changed"},
            },
        )

    first = run_cross_report_analysis(
        _orchestrator_request(tmp_path),
        _settings(tmp_path),
        run_context,
        read_projected_data_fn=_read_projected,
        prompt_client=FakePromptClient(),
        openai_client=openai_client,
        sleep_fn=lambda seconds: None,
    )
    second = run_cross_report_analysis(
        _orchestrator_request(tmp_path),
        _settings(tmp_path),
        run_context,
        read_projected_data_fn=_read_projected,
        prompt_client=FakePromptClient(),
        openai_client=openai_client,
        sleep_fn=lambda seconds: None,
    )

    assert first.idempotency_reused is False
    assert second.idempotency_reused is False
    assert first.idempotency_key != second.idempotency_key
    assert openai_client.calls == 2


def test_cross_report_orchestrator_retries_retryable_service_errors(
    tmp_path,
    run_context,
) -> None:
    attempts = {"count": 0}
    sleeps = []

    def _read_projected(request, ctx):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise AppError(
                code="analytics_store_busy",
                message="Temporary analytics store lock",
                retryable=True,
                severity="warning",
            )
        return _projected_data()

    outcome = run_cross_report_analysis(
        _orchestrator_request(tmp_path),
        _settings(tmp_path),
        run_context,
        read_projected_data_fn=_read_projected,
        prompt_client=FakePromptClient(),
        openai_client=CountingOpenAIClient(),
        sleep_fn=lambda seconds: sleeps.append(seconds),
    )

    assert outcome.status == "validated"
    assert attempts["count"] == 2
    assert sleeps == [0.0]


def test_cross_report_orchestrator_dry_run_builds_package_without_live_publish(
    tmp_path,
    run_context,
) -> None:
    publish_calls = []

    def _publish_package(package, publish_settings, ctx, *, dry_run, sleep_fn):
        publish_calls.append(
            {
                "dry_run": dry_run,
                "package_id": package.package_id,
                "html_path": package.html_path,
                "has_source_map": "Source report map" in package.html_text,
            }
        )
        return CrossReportPublishResultSummary(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            publication_mode="publish_dry_run",
            status="dry_run",
            target_route="wordpress:ml_report",
            idempotency_reused=False,
        )

    outcome = run_cross_report_analysis(
        _orchestrator_request_with_mode(tmp_path, "publish_dry_run"),
        _settings(tmp_path),
        run_context,
        read_projected_data_fn=lambda request, ctx: _projected_data(),
        prompt_client=FakePromptClient(),
        openai_client=CountingOpenAIClient(),
        publish_cross_report_package_fn=_publish_package,
        sleep_fn=lambda seconds: None,
    )

    assert outcome.status == "validated"
    assert outcome.publish_result.status == "dry_run"
    assert publish_calls == [
        {
            "dry_run": True,
            "package_id": "cross-report:analysis-orchestrated-ai",
            "html_path": str(
                tmp_path
                / "out"
                / "cross_report_analysis"
                / "ai-commerce-adoption-across-retail-reports"
                / "publish.html"
            ),
            "has_source_map": True,
        }
    ]
    assert Path(publish_calls[0]["html_path"]).exists()
    publish_html = Path(publish_calls[0]["html_path"]).read_text(encoding="utf-8")
    assert "data-market-lense-cross-report-metadata" in publish_html


def test_cross_report_orchestrator_live_publish_requires_enabled_config(
    tmp_path,
    run_context,
    assert_app_error,
) -> None:
    with pytest.raises(Exception) as exc:
        run_cross_report_analysis(
            _orchestrator_request_with_mode(tmp_path, "publish_live"),
            _settings(tmp_path),
            run_context,
            read_projected_data_fn=lambda request, ctx: _projected_data(),
            prompt_client=FakePromptClient(),
            openai_client=CountingOpenAIClient(),
            sleep_fn=lambda seconds: None,
        )

    assert_app_error(
        exc.value,
        code="cross_report_publish_live_disabled",
        retryable=False,
        severity="error",
    )


def test_cross_report_orchestrator_live_publish_retries_and_reuses_idempotency(
    tmp_path,
    run_context,
) -> None:
    settings = _settings(tmp_path)
    settings.cross_report_analysis_publish_enabled = True
    openai_client = CountingOpenAIClient()
    publish_attempts = {"count": 0}
    sleeps = []

    def _publish_package(package, publish_settings, ctx, *, dry_run, sleep_fn):
        publish_attempts["count"] += 1
        if publish_attempts["count"] == 1:
            raise AppError(
                code="wp_post_create_failed",
                message="Temporary WordPress failure",
                retryable=True,
                severity="warning",
            )
        return CrossReportPublishResultSummary(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            publication_mode="publish_live",
            status="published",
            target_route="wordpress:ml_report",
            idempotency_reused=False,
            post_id=123,
            post_url="https://example.com/cross-report",
        )

    first = run_cross_report_analysis(
        _orchestrator_request_with_mode(tmp_path, "publish_live"),
        settings,
        run_context,
        read_projected_data_fn=lambda request, ctx: _projected_data(),
        prompt_client=FakePromptClient(),
        openai_client=openai_client,
        publish_settings=SimpleNamespace(marker="publish-settings"),
        publish_cross_report_package_fn=_publish_package,
        sleep_fn=lambda seconds: sleeps.append(seconds),
    )
    second = run_cross_report_analysis(
        _orchestrator_request_with_mode(tmp_path, "publish_live"),
        settings,
        run_context,
        read_projected_data_fn=lambda request, ctx: _projected_data(),
        prompt_client=FakePromptClient(),
        openai_client=openai_client,
        publish_settings=SimpleNamespace(marker="publish-settings"),
        publish_cross_report_package_fn=_publish_package,
        sleep_fn=lambda seconds: sleeps.append(seconds),
    )

    assert first.status == "published"
    assert first.publish_result.status == "published"
    assert first.publish_result.post_id == 123
    assert second.idempotency_reused is True
    assert second.publish_result.post_url == "https://example.com/cross-report"
    assert openai_client.calls == 1
    assert publish_attempts["count"] == 2
    assert sleeps == [0.0]
