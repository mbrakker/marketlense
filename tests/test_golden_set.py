import json
import hashlib
from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.contracts.categories import CategoryAssignment, CategoryMappings, CategoryMappingLoadResponse, CategoryDefinition
from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestSettings
from src.contracts.openai import OpenAIAnalyzeResponse
from src.contracts.pdf_context import PdfContext, PdfContextBuildResponse
from src.contracts.pdf_contents import PdfContentsDetectionResponse
from src.contracts.pdf_text import PdfTextExtractResponse
from src.contracts.pdf_utils import PdfInfoResponse
from src.contracts.prompts import PromptRenderResponse, PromptSet, PromptTemplate
from src.contracts.report_assets import (
    ExtractCandidatesResponse,
    FigureExtractResponse,
    PreviewResponse,
    RenderResponse,
)
from src.contracts.report_models import Figure, Quote, ReportPayload
from src.contracts.run_context import RunContext
from src.generators.report_generator import generate_report
from src.contracts.validation import ValidationReport


FIXTURES_ROOT = Path("out/fixtures/golden_set")


def _load_cases() -> List[dict]:
    raw = json.loads(json.dumps(_load_yaml(FIXTURES_ROOT / "metadata.yaml")))  # normalize YAML scalars
    return raw.get("fixtures", [])


def _load_yaml(path: Path) -> dict:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return FIXTURES_ROOT / path


def _load_expected_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _ctx(case_id: str) -> RunContext:
    return RunContext(schema_version="1.0", run_id=f"run-{case_id}", task_id=case_id, span_id=f"span-{case_id}")


def _prompt_template(text: str) -> PromptTemplate:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return PromptTemplate(schema_version="1.0", path=f"/dev/null/{digest}.yaml", text=text, sha256=digest)


def _payload_from_dict(data: Dict[str, Any]) -> ReportPayload:
    return ReportPayload(
        tldr=data["tldr"],
        title=data["title"],
        insights=data["insights"],
        quote=Quote(text=data["quote"]["text"], author=data["quote"]["author"], schema_version="1.0"),
        figure=Figure(title=data["figure"]["title"], evidence=data["figure"]["evidence"], schema_version="1.0"),
        commentary=data["commentary"],
        source=data["source"],
        publisher=data["publisher"],
        taxonomy=data["taxonomy"],
        categories=[],  # will be filled by categorize step
        region=data["region"],
        time_period=data["time_period"],
        contents_page_number=data.get("contents_page_number", 0),
        contents_heading=data.get("contents_heading", ""),
        _openai_file_id="",
        _figure_image="",
        _figure_gallery=[],
        _figure_top="",
        _contents_image="",
    )


def _render_html(data: Dict[str, Any]) -> str:
    lines = [
        "<html>",
        "<body>",
        f"<h1>{data['title']}</h1>",
        f"<p>TLDR: {data['tldr']}</p>",
        "<ul>",
    ]
    for insight in data["insights"]:
        lines.append(f"<li>{insight}</li>")
    lines.extend(
        [
            "</ul>",
            f"<p>Commentary: {data['commentary']}</p>",
            f"<p>Source: {data['source']}</p>",
            "</body>",
            "</html>",
        ]
    )
    return "\n".join(lines) + "\n"


def _base_settings(output_dir: Path, cache_dir: Path, state_db: Path, reports_db: Path, category_map: Path) -> IngestSettings:
    return IngestSettings(
        schema_version="1.0",
        google_sa_path=str(output_dir / "sa.json"),
        gdrive_folder_id="dummy-folder",
        openai_api_key="dummy",
        openai_model="gpt-5",
        batch_limit=5,
        output_dir=str(output_dir),
        cache_dir=str(cache_dir),
        state_db=str(state_db),
        reports_db=str(reports_db),
        category_mapping_path=str(category_map),
        ingest_lock_path=str(output_dir / "ingest.lock"),
        ingest_lock_ttl_seconds=10.0,
        temperature=0.2,
        openai_seed=None,
        pdf_text_max_pages=2,
        pdf_text_max_chars=2000,
        rank_model="",
        rank_temperature=0.3,
        rank_seed=None,
        openai_timeout_seconds=5.0,
        rank_timeout_seconds=5.0,
        contents_max_pages=2,
        contents_min_headings=1,
        contents_keywords=["contents"],
        contents_preview_dpi=72,
        cost_ledger_path=str(output_dir / "cost-ledger.jsonl"),
        cost_daily_path=str(output_dir / "cost-daily.json"),
        model_pricing={"gpt-5": {"input_tokens_per_1k_usd": 0.01, "output_tokens_per_1k_usd": 0.03, "tool_call_usd": 0.0}},
    )


@pytest.mark.golden_set
def test_golden_reports_regression(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cases = _load_cases()
    assert cases, "Expected at least one golden case"
    for case in cases:
        case_id = case["id"]
        output_dir = tmp_path / case_id / "out"
        cache_dir = tmp_path / case_id / "cache"
        reports_db = tmp_path / case_id / "reports.sqlite"
        state_db = tmp_path / case_id / "state.sqlite"
        category_map = tmp_path / case_id / "categories.yaml"
        output_dir.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)

        expected_json_path = _resolve(case["expected_json"])
        expected_html_path = _resolve(case["expected_html"])
        expected_payload = _load_expected_json(expected_json_path)
        normalized_capture: Dict[str, Any] = {}

        def fake_pdf_info(request, ctx):
            return PdfInfoResponse(schema_version="1.0", path=request.path, page_count=case.get("page_count", 1), metadata={"Title": case["name"]})

        def fake_build_pdf_context(request, ctx):
            return PdfContextBuildResponse(schema_version="1.0", context=PdfContext(schema_version="1.0", path=request.path), fitz_error=None, pypdf_error=None)

        def fake_detect_contents(request, ctx):
            return PdfContentsDetectionResponse(
                schema_version="1.0",
                path=request.path,
                has_contents=False,
                page_index=-1,
                page_number=0,
                heading="",
                confidence=0.0,
            )

        def fake_pdf_text(request, ctx):
            text = case.get("extracted_text", "")
            return PdfTextExtractResponse(schema_version="1.0", text=text, pages_extracted=1, char_count=len(text))

        def fake_load_prompt_set(request, ctx):
            system = _prompt_template("system")
            user = _prompt_template("user")
            return PromptSet(schema_version="1.0", system=system, user=user)

        def fake_render_prompt(request, ctx):
            return PromptRenderResponse(schema_version="1.0", text=request.template.text)

        def fake_openai(request, ctx):
            payload = _payload_from_dict(expected_payload)
            return OpenAIAnalyzeResponse(
                schema_version="1.0",
                payload=payload,
                prompt_system_sha256=request.prompt_system_sha256,
                prompt_user_sha256=request.prompt_user_sha256,
                model=request.model,
                temperature=request.temperature,
                raw_content=json.dumps(expected_payload),
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                request_id="req-golden",
            )

        def fake_load_category_mappings(request, ctx):
            definitions = [
                CategoryDefinition(id=cat_id, label=label, description="", tags=[])
                for cat_id, label in zip(case["categories"]["ids"], case["categories"]["labels"])
            ]
            return CategoryMappingLoadResponse(schema_version="1.0", mappings=CategoryMappings(schema_version="1.0", categories=definitions))

        def fake_categorize(taxonomy, mappings, ctx):
            return CategoryAssignment(
                schema_version="1.0",
                categories=list(case["categories"]["ids"]),
                category_labels=list(case["categories"]["labels"]),
                unmapped_tags=[],
            )

        def fake_update_uncategorized(request, ctx):
            return None

        def fake_extract_figure(request, ctx):
            return FigureExtractResponse(schema_version="1.0", image_path=None, caption=None)

        def fake_collect_candidates(request, ctx):
            return ExtractCandidatesResponse(schema_version="1.0", candidates=[])

        def fake_render_preview(request, ctx):
            return PreviewResponse(schema_version="1.1", image_path=f"{case_id}/preview.png", page_number=0)

        def fake_render_report(request, ctx):
            normalized_capture["payload"] = request.data
            html_text = _render_html(request.data)
            html_path = Path(request.out_dir) / f"{case_id}.html"
            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text(html_text, encoding="utf-8")
            return RenderResponse(schema_version="1.0", html_path=str(html_path))

        def fake_upsert_metadata(request, ctx):
            return None

        def fake_validation(request, settings, ctx, pack_name="validation"):
            return ValidationReport(schema_version="1.1", status="pass", severity="pass", issues=[], source_path="")

        monkeypatch.setattr("src.generators.report_generator.extract_pdf_info", fake_pdf_info)
        monkeypatch.setattr("src.generators.report_generator.build_pdf_context", fake_build_pdf_context)
        monkeypatch.setattr("src.generators.report_generator.detect_contents_page_service", fake_detect_contents)
        monkeypatch.setattr("src.generators.report_generator.extract_pdf_text", fake_pdf_text)
        monkeypatch.setattr("src.generators.report_generator.load_prompt_set", fake_load_prompt_set)
        monkeypatch.setattr("src.generators.report_generator.render_prompt", fake_render_prompt)
        monkeypatch.setattr("src.generators.report_generator.openai_analyze", fake_openai)
        monkeypatch.setattr("src.generators.report_generator.load_category_mappings", fake_load_category_mappings)
        monkeypatch.setattr("src.generators.report_generator.categorize_taxonomy", fake_categorize)
        monkeypatch.setattr("src.generators.report_generator.update_uncategorized_tags", fake_update_uncategorized)
        monkeypatch.setattr("src.generators.report_generator.extract_best_figure_service", fake_extract_figure)
        monkeypatch.setattr("src.generators.report_generator.collect_candidates_service", fake_collect_candidates)
        monkeypatch.setattr("src.generators.report_generator.render_preview_service", fake_render_preview)
        monkeypatch.setattr("src.generators.report_generator.render_report_service", fake_render_report)
        monkeypatch.setattr("src.generators.report_generator.upsert_report_metadata", fake_upsert_metadata)
        monkeypatch.setattr("src.generators.report_generator.run_validation", fake_validation)

        settings = _base_settings(output_dir, cache_dir, state_db, reports_db, category_map)
        drive_file = DriveFile(
            schema_version="1.0",
            file_id=case["file_id"],
            name=case["name"],
            modified_time=None,
            md5_checksum="md5",
            version=None,
        )
        pdf_path = _resolve(case["pdf"])
        outcome = generate_report(drive_file, str(pdf_path), settings, md5="md5", ctx=_ctx(case_id))

        assert outcome.status == "processed"
        assert Path(outcome.html_path).exists()
        normalized_capture["payload"].pop("validation_report", None)
        assert normalized_capture["payload"] == expected_payload
        html_text = Path(outcome.html_path).read_text(encoding="utf-8")
        expected_html = expected_html_path.read_text(encoding="utf-8")
        assert html_text == expected_html
