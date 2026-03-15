from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from src.contracts.drive import DriveFile
from src.contracts.openai import OpenAIResponseResult
from src.contracts.prompts import PromptRenderResponse, PromptSet, PromptTemplate
from src.contracts.report_analysis import AnalysisStorePackResponse
from src.contracts.report_generation import ReportRuntimeState
from src.contracts.report_models import Figure, Quote, ReportFigureAsset, ReportPayload
from src.contracts.run_context import RunContext
from src.generators.figure_caption_generator import generate_figure_captions
from src.generators.report_generation_dependencies import ReportGeneratorDependencies


def _events(caplog) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for record in caplog.records:
        if record.name != "market_lense.figure_caption_generator":
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _render_prompt(request, _ctx):
    text = request.template.text
    for key, value in request.variables.items():
        text = text.replace("{{ " + key + " }}", str(value))
    return PromptRenderResponse(schema_version="1.0", text=text)


def _prompt_set() -> PromptSet:
    return PromptSet(
        schema_version="1.0",
        system=PromptTemplate(
            schema_version="1.0",
            path="src/prompts/report_vs/figure_caption/system.yaml",
            text='{"instruction":"limit {{ max_chars }}"}',
            sha256="system-sha",
        ),
        user=PromptTemplate(
            schema_version="1.0",
            path="src/prompts/report_vs/figure_caption/user.yaml",
            text='{"context": {{ context_json }}, "limit": {{ max_chars }}}',
            sha256="user-sha",
        ),
    )


def _runtime(ingest_settings, tmp_path: Path) -> ReportRuntimeState:
    settings = ingest_settings.__class__(
        **{
            **ingest_settings.__dict__,
            "output_dir": str(tmp_path / "out"),
            "figure_caption_enabled": True,
            "figure_caption_temperature": 0.2,
            "figure_caption_timeout_seconds": 123.0,
            "figure_caption_prompt_namespace": "report_vs/figure_caption",
            "figure_caption_max_chars": 120,
            "openai_models": {"report_vs/figure_caption": "gpt-5-caption"},
            "openai_seed": 7,
        }
    )
    return ReportRuntimeState(
        schema_version="1.0",
        file=DriveFile(
            schema_version="1.0",
            file_id="file-1",
            name="report.pdf",
            modified_time=None,
            md5_checksum="md5",
        ),
        local_pdf_path=str(tmp_path / "report.pdf"),
        settings=settings,
        md5="md5",
        ctx=RunContext(
            schema_version="1.0",
            run_id="run",
            task_id="task",
            span_id="span",
        ),
        file_name="report.pdf",
        report_name="report",
        report_title="Report",
        analysis_mode="vector_store",
        analysis_modes=["vector_store"],
        report_worker_limit=1,
        parallel_within_file=False,
    )


def _payload(*, assets: list[ReportFigureAsset]) -> ReportPayload:
    return ReportPayload(
        schema_version="1.1",
        tldr="Retail media budgets are shifting toward measurable channels.",
        title="Retail Momentum Report",
        insights=["i1", "i2", "i3", "i4", "i5"],
        quote=Quote(schema_version="1.0", text="Quote", author="Author"),
        figure=Figure(
            schema_version="1.0",
            title="Legacy primary caption",
            evidence="Legacy primary caption",
        ),
        commentary="Executive commentary for the report.",
        source="https://example.com/report",
        publisher="Acme Insights",
        taxonomy=["retail_media"],
        categories=["retail"],
        region="US",
        time_period="2026",
        _figure_assets=assets,
    )


def test_generate_figure_captions_builds_context_and_updates_assets(
    tmp_path,
    ingest_settings,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    runtime = _runtime(ingest_settings, tmp_path)
    (Path(runtime.settings.output_dir) / "report" / "slices").mkdir(
        parents=True, exist_ok=True
    )
    assets = [
        ReportFigureAsset(
            image_path="report/slices/primary.png",
            page=1,
            candidate_id="chart-1",
            kind="chart",
            is_primary=True,
            detected_caption="Retail media growth by channel",
            preview_text="Retail media spend rose sharply in social commerce.",
            display_caption="Legacy primary caption",
            caption_source="legacy",
        ),
        ReportFigureAsset(
            image_path="report/slices/secondary.png",
            page=2,
            candidate_id="table-2",
            kind="table",
            is_primary=False,
            detected_caption="Commerce conversion benchmarks",
            preview_text="Conversion rates improved for loyalty-led cohorts.",
            display_caption="Additional figure 2",
            caption_source="placeholder",
        ),
    ]
    payload = _payload(assets=assets)
    render_requests = []
    openai_requests = []
    store_requests = []

    def _openai_chat_json_with_images(request, _ctx):
        openai_requests.append(request)
        caption = (
            "Retail media accelerates where commerce-native channels convert attention into measurable demand."
            if len(openai_requests) == 1
            else "Benchmarks show loyalty-led cohorts widening the conversion gap as efficiency compounds."
        )
        return OpenAIResponseResult(
            schema_version="1.0",
            text=json.dumps({"caption": caption}),
            parsed_json={"caption": caption},
            input_tokens=12,
            output_tokens=7,
            total_tokens=19,
            request_id=f"req_{len(openai_requests)}",
            model=request.model,
        )

    def _analysis_store_pack(request, _ctx):
        store_requests.append(request)
        return AnalysisStorePackResponse(
            schema_version="1.0",
            output_path=str(
                Path(request.output_dir)
                / "report"
                / "report_analysis"
                / "figure_captions.json"
            ),
        )

    def _render_and_capture(request, ctx):
        render_requests.append(request)
        return _render_prompt(request, ctx)

    dependencies = replace(
        ReportGeneratorDependencies.default(),
        load_prompt_set=lambda request, _ctx: _prompt_set(),
        render_prompt=_render_and_capture,
        openai_chat_json_with_images=_openai_chat_json_with_images,
        analysis_store_pack=_analysis_store_pack,
    )

    doc_map = {
        "sections": [
            {
                "title": "Retail momentum",
                "summary": "Retail media spend is consolidating around channels with stronger commerce intent.",
                "pages": [2],
                "key_points": ["Commerce media is outpacing upper-funnel formats."],
            }
        ]
    }
    findings_pack = {
        "findings": [
            {
                "text": "Retail media budgets are concentrating in channels tied to conversion gains.",
                "pages": [2],
            }
        ]
    }
    artifacts_payload = {
        "summary": {
            "tldr": "Retail media budgets are concentrating around measurable commerce channels.",
            "executive_summary": "Commerce-led media is outperforming broad reach tactics as teams prioritize proof of impact.",
            "claim_evidence_map": [
                {
                    "claim": "Conversion efficiency is the strategic filter.",
                    "evidence": "Higher-intent channels are winning budget share.",
                    "pages": [2],
                }
            ],
        }
    }

    caplog.set_level(logging.INFO, logger="market_lense.figure_caption_generator")
    result = generate_figure_captions(
        runtime=runtime,
        selection=SimpleNamespace(),
        payload=payload,
        doc_map=doc_map,
        findings_pack=findings_pack,
        artifacts_payload=artifacts_payload,
        dependencies=dependencies,
    )

    assert len(openai_requests) == 2
    assert openai_requests[0].model == "gpt-5-caption"
    assert result.payload._figure_assets[0].caption_source == "generated"
    assert result.payload._figure_assets[1].caption_source == "generated"
    assert (
        result.payload._figure_assets[0].display_caption
        == "Retail media accelerates where commerce-native channels convert attention into measurable demand."
    )
    assert (
        result.payload.figure.title == result.payload._figure_assets[0].display_caption
    )
    assert (
        result.payload.figure.evidence
        == result.payload._figure_assets[0].display_caption
    )
    assert result.pack_path.endswith("figure_captions.json")
    assert store_requests[0].pack_name == "figure_captions"
    assert result.pack_payload["results"][0]["request_id"] == "req_1"

    user_requests = [
        request
        for request in render_requests
        if request.template.path.endswith("user.yaml")
    ]
    first_context = json.loads(user_requests[0].variables["context_json"])
    assert first_context["report_identity"]["title"] == "Retail Momentum Report"
    assert first_context["section_context"]["section_title"] == "Retail momentum"
    assert len(first_context["evidence_highlights"]) >= 1
    assert "candidate_type" in first_context["figure_signals"]

    events = _events(caplog)
    assert_logs_have_required_fields(events)
    event_names = {str(event["event"]) for event in events}
    assert "figure_caption_prompt_selected" in event_names
    assert "figure_caption_prompt_rendered" in event_names
    assert "figure_caption_generated" in event_names
    assert "figure_caption_pack_stored" in event_names
    generated_events = [
        event for event in events if event["event"] == "figure_caption_generated"
    ]
    assert generated_events[0]["fields"]["raw_response"]
    assert generated_events[0]["fields"]["caption_source"] == "generated"


def test_generate_figure_captions_fail_open_uses_fallback_sources(
    tmp_path,
    ingest_settings,
) -> None:
    runtime = _runtime(ingest_settings, tmp_path)
    runtime = replace(
        runtime,
        settings=runtime.settings.__class__(
            **{**runtime.settings.__dict__, "figure_caption_max_chars": 40}
        ),
    )
    assets = [
        ReportFigureAsset(
            image_path="report/slices/primary.png",
            page=1,
            candidate_id="chart-1",
            kind="chart",
            is_primary=True,
            detected_caption="Detected primary caption",
            preview_text="Primary preview",
            display_caption="Legacy primary caption",
            caption_source="legacy",
        ),
        ReportFigureAsset(
            image_path="report/slices/secondary.png",
            page=2,
            candidate_id="table-2",
            kind="table",
            is_primary=False,
            detected_caption="Detected secondary caption",
            preview_text="Secondary preview",
            display_caption="Additional figure 2",
            caption_source="placeholder",
        ),
        ReportFigureAsset(
            image_path="report/slices/tertiary.png",
            page=3,
            candidate_id="image-3",
            kind="image",
            is_primary=False,
            detected_caption="",
            preview_text="Tertiary preview",
            display_caption="Additional figure 3",
            caption_source="placeholder",
        ),
    ]
    payload = _payload(assets=assets)
    call_index = {"value": 0}

    def _openai_chat_json_with_images(request, _ctx):
        call_index["value"] += 1
        if call_index["value"] == 1:
            caption = "This caption is deliberately far too long to survive the configured character limit."
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps({"caption": caption}),
                parsed_json={"caption": caption},
                request_id="req_long",
                model=request.model,
            )
        if call_index["value"] == 2:
            raise RuntimeError("provider_failure")
        return OpenAIResponseResult(
            schema_version="1.0",
            text=json.dumps({"caption": ""}),
            parsed_json={"caption": ""},
            request_id="req_empty",
            model=request.model,
        )

    dependencies = replace(
        ReportGeneratorDependencies.default(),
        load_prompt_set=lambda request, _ctx: _prompt_set(),
        render_prompt=_render_prompt,
        openai_chat_json_with_images=_openai_chat_json_with_images,
        analysis_store_pack=lambda request, _ctx: AnalysisStorePackResponse(
            schema_version="1.0",
            output_path=str(
                Path(request.output_dir)
                / "report"
                / "report_analysis"
                / "figure_captions.json"
            ),
        ),
    )

    result = generate_figure_captions(
        runtime=runtime,
        selection=SimpleNamespace(),
        payload=payload,
        doc_map={"sections": []},
        findings_pack={"findings": []},
        artifacts_payload={"summary": {}},
        dependencies=dependencies,
    )

    assert result.payload._figure_assets[0].caption_source == "legacy"
    assert result.payload._figure_assets[0].display_caption == "Legacy primary caption"
    assert result.payload._figure_assets[1].caption_source == "detected"
    assert (
        result.payload._figure_assets[1].display_caption == "Detected secondary caption"
    )
    assert result.payload._figure_assets[2].caption_source == "placeholder"
    assert result.payload._figure_assets[2].display_caption == "Additional figure 3"
    assert result.payload.figure.title == "Legacy primary caption"
    assert result.pack_payload["results"][0]["error"] == "caption_too_long"
    assert result.pack_payload["results"][1]["error"] == "provider_failure"
    assert result.pack_payload["results"][2]["error"] == "empty_caption"


def test_generate_figure_captions_skips_when_disabled(
    tmp_path, ingest_settings
) -> None:
    runtime = _runtime(ingest_settings, tmp_path)
    runtime = replace(
        runtime,
        settings=runtime.settings.__class__(
            **{**runtime.settings.__dict__, "figure_caption_enabled": False}
        ),
    )
    payload = _payload(
        assets=[
            ReportFigureAsset(
                image_path="report/slices/primary.png",
                page=1,
                candidate_id="chart-1",
                kind="chart",
                is_primary=True,
            )
        ]
    )
    openai_calls = []
    store_calls = []

    dependencies = replace(
        ReportGeneratorDependencies.default(),
        load_prompt_set=lambda request, _ctx: _prompt_set(),
        render_prompt=_render_prompt,
        openai_chat_json_with_images=lambda request, _ctx: openai_calls.append(request),
        analysis_store_pack=lambda request, _ctx: store_calls.append(request),
    )

    result = generate_figure_captions(
        runtime=runtime,
        selection=SimpleNamespace(),
        payload=payload,
        doc_map={"sections": []},
        findings_pack={"findings": []},
        artifacts_payload={"summary": {}},
        dependencies=dependencies,
    )

    assert result.pack_path == ""
    assert result.pack_payload == {}
    assert result.payload._figure_assets[0].generated_caption == ""
    assert openai_calls == []
    assert store_calls == []
