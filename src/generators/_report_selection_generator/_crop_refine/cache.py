from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from src.contracts.candidates import Candidate
from src.contracts.ingest import IngestSettings
from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisStorePackRequest,
)
from src.contracts.semantic_ids import ReportId
from src.generators.report_generation_dependencies import ReportSelectionDependencies
from src.generators.report_generation_shared import read_cache_json
from src.utils.cache_utils import sha256_json
from src.utils.coercion import coerce_int
from src.utils.logging import child_context
from src.utils.candidate_features import candidate_features_payload

from ..ranking import _candidate_quality_signals

def _bbox_tuple(values: Any) -> tuple[float, float, float, float]:
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        raise ValueError(f"Expected bbox with 4 coordinates, received: {values!r}")
    return (
        float(values[0]),
        float(values[1]),
        float(values[2]),
        float(values[3]),
    )

def _crop_refine_parallel_workers(settings: IngestSettings, selected_max: int) -> int:
    configured = coerce_int(getattr(settings, "report_worker_limit", 1), 1)
    if configured < 1:
        configured = 1
    return max(1, min(configured, max(1, selected_max), 3))

def _crop_refine_profile_key(
    md5: str,
    *,
    model: str,
    temperature: float,
    seed: Optional[int],
    mode: str,
    prompt_system_sha256: str,
    prompt_user_sha256: str,
) -> str:
    return sha256_json(
        {
            "schema_version": "1.0",
            "md5": md5,
            "model": model,
            "temperature": temperature,
            "seed": seed,
            "mode": mode,
            "prompt_system_sha256": prompt_system_sha256,
            "prompt_user_sha256": prompt_user_sha256,
        }
    )

def _crop_refine_entry_key(
    md5: str,
    candidate: Candidate,
    *,
    model: str,
    temperature: float,
    seed: Optional[int],
    mode: str,
    prompt_system_sha256: str,
    prompt_user_sha256: str,
) -> str:
    return sha256_json(
        {
            "schema_version": "1.0",
            "md5": md5,
            "candidate_id": candidate.id,
            "page": candidate.page,
            "bbox": list(candidate.bbox),
            "features": candidate_features_payload(candidate),
            "quality_signals": _candidate_quality_signals(candidate),
            "caption": candidate.caption or "",
            "preview_text": candidate.preview_text or "",
            "model": model,
            "temperature": temperature,
            "seed": seed,
            "mode": mode,
            "prompt_system_sha256": prompt_system_sha256,
            "prompt_user_sha256": prompt_user_sha256,
        }
    )

def _crop_refine_cache_path(
    settings: IngestSettings,
    file_id: str,
    report_name: str,
    ctx,
    dependencies: ReportSelectionDependencies,
) -> str:
    return dependencies.analysis_pack_path(
        AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=settings.output_dir,
            report_id=ReportId(file_id),
            pack_name="crop_refine",
            report_slug=report_name,
        ),
        child_context(ctx, task_id=f"{ctx.task_id}:crop_refine_cache_path"),
    ).output_path

def _load_crop_refine_cache(
    settings: IngestSettings,
    *,
    file_id: str,
    report_name: str,
    profile_key: str,
    ctx,
    dependencies: ReportSelectionDependencies,
) -> dict[str, dict]:
    crop_cache_path = _crop_refine_cache_path(
        settings,
        file_id,
        report_name,
        ctx,
        dependencies,
    )
    payload = read_cache_json(Path(crop_cache_path), ctx, dependencies)
    if not isinstance(payload, dict):
        return {}
    profile_value = payload.get("_cache")
    profile = profile_value if isinstance(profile_value, dict) else {}
    if str(profile.get("key") or "") != profile_key:
        return {}
    rows_value = payload.get("results")
    rows = rows_value if isinstance(rows_value, list) else []
    out: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        entry_key = str(row.get("entry_key") or "").strip()
        if entry_key:
            out[entry_key] = row
    return out

def _write_crop_refine_cache(
    settings: IngestSettings,
    *,
    file_id: str,
    report_name: str,
    profile: dict,
    entries: dict[str, dict],
    ctx,
    dependencies: ReportSelectionDependencies,
) -> None:
    rows = []
    for entry_key, payload in entries.items():
        if not isinstance(payload, dict):
            continue
        rows.append({"entry_key": entry_key, **payload})
    rows.sort(key=lambda item: str(item.get("entry_key") or ""))
    dependencies.analysis_store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=settings.output_dir,
            report_id=ReportId(file_id),
            pack_name="crop_refine",
            payload={
                "schema_version": "1.0",
                "_cache": profile,
                "results": rows,
            },
            report_slug=report_name,
        ),
        child_context(ctx, task_id=f"{ctx.task_id}:crop_refine_cache_write"),
    )
