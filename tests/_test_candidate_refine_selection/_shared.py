# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_candidate_refine_selection.py"
)

import json
import logging
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from pypdf import PdfWriter

from src.contracts.candidates import Candidate, CandidateFeatures
from src.contracts.ingest import IngestSettings
from src.contracts.prompts import PromptDependency, PromptDependencyManifest
from src.contracts.report_assets import CropRefineResponse, CropRefineResult
from src.contracts.report_models import Figure, Quote, RankedCandidate, ReportPayload
from src.contracts.run_context import RunContext
from src.generators import report_selection_generator as rsg
from src.generators.report_generation_dependencies import ReportSelectionDependencies


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0", run_id="run", task_id="task", span_id="span"
    )


def _settings(tmp_path, **overrides) -> IngestSettings:
    cover_style_path = (
        Path(__file__).resolve().parents[1] / "src" / "config" / "cover-styles.yaml"
    )
    base = IngestSettings(
        schema_version="1.0",
        google_sa_path="sa.json",
        gdrive_folder_id="folder",
        openai_api_key="key",
        openai_model="gpt-5-mini",
        batch_limit=1,
        output_dir=str(tmp_path / "out"),
        cache_dir=str(tmp_path / "cache"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        category_mapping_path="cats.yaml",
        cover_style_path=str(cover_style_path),
        ingest_lock_path=str(tmp_path / "lock"),
        temperature=0.0,
    )
    payload = {**base.__dict__, **overrides}
    return IngestSettings(**payload)


def _deps(**overrides) -> ReportSelectionDependencies:
    base = ReportSelectionDependencies.default()
    seeded = replace(
        base,
        load_prompt_set=lambda req, ctx: SimpleNamespace(
            system=SimpleNamespace(path="system.yaml", sha256="sys"),
            user=SimpleNamespace(path="user.yaml", sha256="usr"),
            dependency_manifest=PromptDependencyManifest(
                schema_version="1.0",
                namespace=req.namespace,
                system_root=PromptDependency(
                    schema_version="1.0",
                    path=f"{req.namespace}/system.yaml",
                    sha256="a" * 64,
                    kind="system_root",
                ),
                user_root=PromptDependency(
                    schema_version="1.0",
                    path=f"{req.namespace}/user.yaml",
                    sha256="b" * 64,
                    kind="user_root",
                ),
                prompt_content_hash="c" * 64,
            ),
            prompt_content_hash="c" * 64,
        ),
        render_prompt=lambda req, ctx: SimpleNamespace(text="prompt"),
        render_page_for_crop_refine=lambda req, ctx: SimpleNamespace(
            schema_version="1.0",
            image_path="page.png",
            page=req.page,
            image_width=600,
            image_height=800,
            page_width=600.0,
            page_height=800.0,
            scale_x=1.0,
            scale_y=1.0,
        ),
        apply_crop_refine_bbox=lambda req, ctx: SimpleNamespace(
            schema_version="1.0",
            page=req.page,
            bbox=(
                float(req.bbox[0]) - 8.0,
                float(req.bbox[1]) - 8.0,
                float(req.bbox[2]) + 8.0,
                float(req.bbox[3]) + 8.0,
            ),
        ),
    )
    return replace(seeded, **overrides)


def _candidate(
    *,
    cid: str,
    kind: str,
    page: int = 0,
    bbox=(10.0, 10.0, 300.0, 220.0),
    caption: str = "",
    preview_text: str = "",
    meta: dict | None = None,
) -> Candidate:
    return Candidate(
        schema_version="1.0",
        id=cid,
        kind=kind,
        page=page,
        bbox=bbox,
        caption=caption,
        preview_text=preview_text,
        meta=meta or {},
    )


def _pdf_path(tmp_path: Path) -> str:
    path = tmp_path / "dummy.pdf"
    writer = PdfWriter()
    for _ in range(10):
        writer.add_blank_page(width=600, height=800)
    with path.open("wb") as handle:
        writer.write(handle)
    return str(path)


__all__ = [
    name
    for name in globals()
    if name
    not in {
        "__name__",
        "__annotations__",
        "__doc__",
        "__spec__",
        "__file__",
        "__package__",
        "__loader__",
        "__cached__",
        "__builtins__",
        "_SplitPath",
    }
]
