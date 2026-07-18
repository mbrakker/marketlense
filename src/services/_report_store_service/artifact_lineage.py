"""Reports-DB service boundary for durable artifact lineage."""

from __future__ import annotations

# ruff: noqa: E501
import hashlib
import json
import sqlite3
from pathlib import Path

from src.contracts.artifact_lineage import (
    ARTIFACT_LINEAGE_SCHEMA_VERSION,
    ArtifactInvalidationRequest,
    ArtifactInvalidationResponse,
    ArtifactLineageBackfillRequest,
    ArtifactLineageBackfillResponse,
    ArtifactLineageRecord,
    ArtifactLineageRegistrationRequest,
    ArtifactLineageRegistrationResponse,
    ArtifactLineageStorageLookupRequest,
    ArtifactLineageStorageLookupResponse,
    ArtifactLineageTraceRequest,
    ArtifactLineageTraceResponse,
    ArtifactReuseCheckRequest,
    ArtifactReuseCheckResponse,
)
from src.contracts.run_context import RunContext
from src.utils.artifact_lineage_invalidation import (
    select_invalidation_roots,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

from .common import logger
from .connection import _metadata_conn


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha256_file(storage_ref: str) -> tuple[str, str]:
    path = Path(storage_ref).expanduser().resolve()
    if not path.is_file():
        raise AppError(
            code="artifact_lineage_storage_missing",
            message="Artifact storage reference must be a readable file",
            retryable=False,
            context={"storage_ref": str(path)},
        )
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return str(path), digest.hexdigest()


def _identity_payload(
    request: ArtifactLineageRegistrationRequest,
    storage_ref: str,
    content_hash: str,
    dependencies: list[str],
) -> dict[str, object]:
    return {
        "schema_version": ARTIFACT_LINEAGE_SCHEMA_VERSION,
        "artifact_kind": request.artifact_kind.strip(),
        "report_id": request.report_id.strip(),
        "source_id": request.source_id.strip(),
        "storage_ref": storage_ref,
        "content_hash": content_hash,
        "schema_version_used": request.schema_version_used.strip(),
        "processing_version": request.processing_version.strip(),
        "dependencies": dependencies,
        "prompt_hash": request.prompt_hash.strip(),
        "model_provider": request.model_provider.strip(),
        "model_name": request.model_name.strip(),
        "model_parameters_hash": request.model_parameters_hash.strip(),
        "validation_status": request.validation_status.strip(),
        "metadata": request.metadata,
        "compatibility": request.compatibility,
        "lineage_status": request.lineage_status.strip(),
    }


def _artifact_id(payload: dict[str, object]) -> str:
    return "art_" + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _row_to_record(row: sqlite3.Row) -> ArtifactLineageRecord:
    return ArtifactLineageRecord(
        schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
        artifact_id=str(row["artifact_id"]),
        artifact_kind=str(row["artifact_kind"]),
        report_id=str(row["report_id"]),
        source_id=str(row["source_id"]),
        content_hash=str(row["content_hash"]),
        storage_ref=str(row["storage_ref"]),
        producer=str(row["producer"]),
        schema_version_used=str(row["schema_version_used"]),
        processing_version=str(row["processing_version"]),
        prompt_hash=str(row["prompt_hash"]),
        model_provider=str(row["model_provider"]),
        model_name=str(row["model_name"]),
        model_parameters_hash=str(row["model_parameters_hash"]),
        validation_status=str(row["validation_status"]),
        state=str(row["state"]),
        invalidation_reason=str(row["invalidation_reason"] or ""),
        superseded_by=str(row["superseded_by"] or ""),
        metadata=json.loads(str(row["metadata_json"])),
        compatibility=json.loads(str(row["compatibility_json"] or "{}")),
        lineage_status=str(row["lineage_status"] or "legacy_unverified"),
    )


def _get_record(
    conn: sqlite3.Connection, artifact_id: str
) -> ArtifactLineageRecord | None:
    row = conn.execute(
        """SELECT r.*, s.state, s.invalidation_reason, s.superseded_by FROM artifact_lineage_records r
        JOIN artifact_lineage_states s ON s.artifact_id=r.artifact_id WHERE r.artifact_id=?""",
        (artifact_id,),
    ).fetchone()
    return _row_to_record(row) if row else None


def _make_storage_record_canonical(
    conn: sqlite3.Connection,
    *,
    artifact_id: str,
    report_id: str,
    artifact_kind: str,
    storage_ref: str,
) -> None:
    """Keep one active lineage observation for a materialized artifact path."""
    conn.execute(
        """
        UPDATE artifact_lineage_states
        SET state='active', invalidation_reason='', superseded_by='',
            updated_at_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now')
        WHERE artifact_id=?
        """,
        (artifact_id,),
    )
    conn.execute(
        """
        WITH RECURSIVE superseded_artifacts(artifact_id) AS (
            SELECT r.artifact_id
            FROM artifact_lineage_records r
            WHERE r.report_id=? AND r.artifact_kind=? AND r.storage_ref=?
              AND r.artifact_id<>?
            UNION
            SELECT dependency.artifact_id
            FROM artifact_lineage_dependencies dependency
            JOIN superseded_artifacts parent
              ON parent.artifact_id=dependency.dependency_artifact_id
            JOIN artifact_lineage_states child
              ON child.artifact_id=dependency.artifact_id
            WHERE child.state='active'
        )
        UPDATE artifact_lineage_states
        SET state='superseded', invalidation_reason='', superseded_by=?,
            updated_at_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now')
        WHERE state='active' AND artifact_id IN (SELECT artifact_id FROM superseded_artifacts)
        """,
        (report_id, artifact_kind, storage_ref, artifact_id, artifact_id),
    )


def record_artifact_lineage(
    request: ArtifactLineageRegistrationRequest, ctx: RunContext
) -> ArtifactLineageRegistrationResponse:
    if (
        not request.db_path.strip()
        or not request.artifact_kind.strip()
        or not request.storage_ref.strip()
    ):
        raise AppError(
            code="artifact_lineage_request_invalid",
            message="Artifact lineage requires DB path, kind, and storage reference",
            retryable=False,
        )
    storage_ref, actual_hash = _sha256_file(request.storage_ref)
    if request.content_hash and request.content_hash.strip().lower() != actual_hash:
        raise AppError(
            code="artifact_lineage_content_hash_mismatch",
            message="Supplied artifact content hash does not match storage",
            retryable=False,
            context={"storage_ref": storage_ref},
        )
    dependencies = sorted(
        {value.strip() for value in request.dependency_artifact_ids if value.strip()}
    )
    payload = _identity_payload(request, storage_ref, actual_hash, dependencies)
    artifact_id = _artifact_id(payload)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="artifact_lineage_record_start",
            module=logger.name,
            fields={
                "artifact_id": artifact_id,
                "artifact_kind": request.artifact_kind,
                "dependency_count": len(dependencies),
            },
        )
    )
    with _metadata_conn(request.db_path.strip(), ctx) as conn:
        existing = _get_record(conn, artifact_id)
        if existing is not None:
            _make_storage_record_canonical(
                conn,
                artifact_id=artifact_id,
                report_id=request.report_id.strip(),
                artifact_kind=request.artifact_kind.strip(),
                storage_ref=storage_ref,
            )
            existing = _get_record(conn, artifact_id)
            assert existing is not None
            return ArtifactLineageRegistrationResponse(
                schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
                record=existing,
                created=False,
            )
        missing = [
            dependency
            for dependency in dependencies
            if _get_record(conn, dependency) is None
        ]
        if missing:
            raise AppError(
                code="artifact_lineage_dependency_missing",
                message="Artifact lineage dependencies must be recorded first",
                retryable=False,
                context={"missing_dependency_ids": missing},
            )
        conn.execute(
            """INSERT INTO artifact_lineage_records(artifact_id,artifact_kind,report_id,source_id,content_hash,storage_ref,producer,schema_version_used,processing_version,prompt_hash,model_provider,model_name,model_parameters_hash,validation_status,metadata_json,compatibility_json,lineage_status,created_at_utc)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))""",
            (
                artifact_id,
                request.artifact_kind.strip(),
                request.report_id.strip(),
                request.source_id.strip(),
                actual_hash,
                storage_ref,
                request.producer.strip(),
                request.schema_version_used.strip(),
                request.processing_version.strip(),
                request.prompt_hash.strip(),
                request.model_provider.strip(),
                request.model_name.strip(),
                request.model_parameters_hash.strip(),
                request.validation_status.strip(),
                _canonical_json(request.metadata),
                _canonical_json(request.compatibility),
                request.lineage_status.strip() or "legacy_unverified",
            ),
        )
        conn.execute(
            "INSERT INTO artifact_lineage_states(artifact_id,state,invalidation_reason,superseded_by,updated_at_utc) VALUES(?, 'active', '', '', strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
            (artifact_id,),
        )
        # A materialization path is the canonical identity of one artifact
        # family for a report.  Keep immutable prior observations, but remove
        # them from the active graph once a newer version occupies that path.
        # Otherwise an old incompatible record would make every later minimal
        # plan regenerate work that the current record already satisfies.
        _make_storage_record_canonical(
            conn,
            artifact_id=artifact_id,
            report_id=request.report_id.strip(),
            artifact_kind=request.artifact_kind.strip(),
            storage_ref=storage_ref,
        )
        for dependency in dependencies:
            conn.execute(
                "INSERT INTO artifact_lineage_dependencies(artifact_id,dependency_artifact_id) VALUES(?,?)",
                (artifact_id, dependency),
            )
        record = _get_record(conn, artifact_id)
    assert record is not None
    logger.info(
        log_event(
            ctx,
            role="service",
            event="artifact_lineage_record_complete",
            module=logger.name,
            fields={
                "artifact_id": artifact_id,
                "created": True,
                "content_hash": actual_hash,
            },
        )
    )
    return ArtifactLineageRegistrationResponse(
        schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION, record=record, created=True
    )


def check_artifact_reuse(
    request: ArtifactReuseCheckRequest, ctx: RunContext
) -> ArtifactReuseCheckResponse:
    with _metadata_conn(request.db_path.strip(), ctx) as conn:
        record = _get_record(conn, request.artifact_id.strip())
    if record is None:
        return ArtifactReuseCheckResponse(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            reusable=False,
            reason="not_found",
        )
    expected = (
        ("schema_version_used", request.expected_schema_version),
        ("processing_version", request.expected_processing_version),
        ("prompt_hash", request.expected_prompt_hash),
        ("model_name", request.expected_model_name),
        ("validation_status", request.expected_validation_status),
    )
    if record.state != "active":
        return ArtifactReuseCheckResponse(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            reusable=False,
            reason="not_active",
            record=record,
        )
    if any(
        expected_value and getattr(record, field) != expected_value
        for field, expected_value in expected
    ):
        return ArtifactReuseCheckResponse(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            reusable=False,
            reason="incompatible",
            record=record,
        )
    try:
        _, actual_hash = _sha256_file(record.storage_ref)
    except AppError:
        return ArtifactReuseCheckResponse(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            reusable=False,
            reason="storage_missing",
            record=record,
        )
    reason = "reusable" if actual_hash == record.content_hash else "content_changed"
    return ArtifactReuseCheckResponse(
        schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
        reusable=reason == "reusable",
        reason=reason,
        record=record,
    )


def trace_artifact_lineage(
    request: ArtifactLineageTraceRequest, ctx: RunContext
) -> ArtifactLineageTraceResponse:
    with _metadata_conn(request.db_path.strip(), ctx) as conn:
        root = _get_record(conn, request.artifact_id.strip())
        if root is None:
            raise AppError(
                code="artifact_lineage_not_found",
                message="Cannot trace a missing artifact",
                retryable=False,
            )
        rows = conn.execute(
            """WITH RECURSIVE lineage(artifact_id, dependency_artifact_id) AS (
          SELECT artifact_id, dependency_artifact_id FROM artifact_lineage_dependencies WHERE artifact_id=?
          UNION SELECT d.artifact_id, d.dependency_artifact_id FROM artifact_lineage_dependencies d JOIN lineage l ON d.artifact_id=l.dependency_artifact_id)
          SELECT artifact_id, dependency_artifact_id FROM lineage""",
            (root.artifact_id,),
        ).fetchall()
        edges = [(str(row[0]), str(row[1])) for row in rows]
        ids = [root.artifact_id] + sorted({value for edge in edges for value in edge})
        records = [
            record
            for artifact_id in ids
            if (record := _get_record(conn, artifact_id)) is not None
        ]
    return ArtifactLineageTraceResponse(
        schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION, records=records, edges=edges
    )


def get_artifact_lineage_for_storage(
    request: ArtifactLineageStorageLookupRequest, ctx: RunContext
) -> ArtifactLineageStorageLookupResponse:
    try:
        storage_ref, _ = _sha256_file(request.storage_ref)
    except AppError:
        return ArtifactLineageStorageLookupResponse(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION, record=None
        )
    with _metadata_conn(request.db_path.strip(), ctx) as conn:
        row = conn.execute(
            """SELECT r.*, s.state, s.invalidation_reason, s.superseded_by
            FROM artifact_lineage_records r JOIN artifact_lineage_states s
            ON s.artifact_id=r.artifact_id
            WHERE r.report_id=? AND r.artifact_kind=? AND r.storage_ref=?
            ORDER BY r.created_at_utc DESC LIMIT 1""",
            (request.report_id.strip(), request.artifact_kind.strip(), storage_ref),
        ).fetchone()
    return ArtifactLineageStorageLookupResponse(
        schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
        record=_row_to_record(row) if row else None,
    )


def invalidate_artifacts(
    request: ArtifactInvalidationRequest, ctx: RunContext
) -> ArtifactInvalidationResponse:
    with _metadata_conn(request.db_path.strip(), ctx) as conn:
        rows = conn.execute(
            "SELECT r.*, s.state, s.invalidation_reason, s.superseded_by FROM artifact_lineage_records r JOIN artifact_lineage_states s ON s.artifact_id=r.artifact_id"
        ).fetchall()
        records = [_row_to_record(row) for row in rows]
        roots = select_invalidation_roots(
            records,
            change_kind=request.change_kind,
            changed_value=request.changed_value,
            report_id=request.report_id,
        )
        if not roots:
            return ArtifactInvalidationResponse(
                schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
                root_artifact_ids=[],
                invalidated_artifact_ids=[],
                dry_run=request.dry_run,
            )
        queue, affected = list(roots), set(roots)
        while queue:
            dependency = queue.pop(0)
            children = conn.execute(
                "SELECT artifact_id FROM artifact_lineage_dependencies WHERE dependency_artifact_id=?",
                (dependency,),
            ).fetchall()
            for child in (str(row[0]) for row in children):
                if child not in affected:
                    affected.add(child)
                    queue.append(child)
        ordered = sorted(affected)
        if not request.dry_run:
            reason = f"{request.change_kind}:{request.changed_value}"
            conn.executemany(
                "UPDATE artifact_lineage_states SET state='invalidated', invalidation_reason=?, updated_at_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE artifact_id=? AND state='active'",
                [(reason, artifact_id) for artifact_id in ordered],
            )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="artifact_lineage_invalidated",
            module=logger.name,
            fields={
                "change_kind": request.change_kind,
                "root_count": len(roots),
                "affected_count": len(ordered),
                "dry_run": request.dry_run,
            },
        )
    )
    return ArtifactInvalidationResponse(
        schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
        root_artifact_ids=roots,
        invalidated_artifact_ids=ordered,
        dry_run=request.dry_run,
    )


def backfill_artifact_lineage(
    request: ArtifactLineageBackfillRequest, ctx: RunContext
) -> ArtifactLineageBackfillResponse:
    root = Path(request.checkpoint_root).expanduser()
    workspace_root = root.parent.parent.parent
    checkpoint_paths = sorted(root.glob("*/*.json"))[: max(0, request.limit)]
    scanned = eligible = created = skipped = incomplete = 0
    for checkpoint_path in checkpoint_paths:
        scanned += 1
        try:
            payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            checkpoint = dict(payload.get("checkpoint") or payload)
            inner = dict(checkpoint.get("payload") or {})
            registry = dict(inner.get("artifact_registry") or {})
            refs = _checkpoint_artifact_refs(
                registry=registry,
                artifact_refs=checkpoint.get("artifact_refs"),
                workspace_root=workspace_root,
                stage_name=str(checkpoint.get("stage_name") or "checkpoint_backfill"),
            )
            file_id = str(checkpoint.get("file_id") or "")
            known: dict[str, str] = {}
            for ref in refs:
                artifact_name, storage_ref = (
                    str(ref.get("artifact_id") or ""),
                    str(ref.get("path") or ""),
                )
                if (
                    not artifact_name
                    or not storage_ref
                    or not Path(storage_ref).is_file()
                ):
                    skipped += 1
                    continue
                eligible += 1
                dependencies = [
                    known[value]
                    for value in _checkpoint_dependencies(artifact_name)
                    if value in known
                ]
                if request.dry_run:
                    known[artifact_name] = artifact_name
                    incomplete += 1
                    continue
                prompt_hash, model_name, metadata = _backfill_provenance(
                    inner, artifact_name
                )
                response = record_artifact_lineage(
                    ArtifactLineageRegistrationRequest(
                        schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
                        db_path=request.db_path,
                        artifact_kind=artifact_name,
                        report_id=file_id,
                        source_id="",
                        storage_ref=storage_ref,
                        producer=str(ref.get("producer_step") or "checkpoint_backfill"),
                        schema_version_used=str(ref.get("schema_version") or "1.0"),
                        processing_version="checkpoint-v1",
                        dependency_artifact_ids=dependencies,
                        prompt_hash=prompt_hash,
                        model_name=model_name,
                        validation_status="not_applicable",
                        metadata=metadata,
                        lineage_status="legacy_unverified",
                    ),
                    ctx,
                )
                known[artifact_name] = response.record.artifact_id
                created += int(response.created)
                incomplete += int(response.record.lineage_status != "complete")
        except (OSError, ValueError, TypeError, AppError):
            skipped += 1
    return ArtifactLineageBackfillResponse(
        schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
        scanned_checkpoints=scanned,
        eligible_artifacts=eligible,
        created_artifacts=created,
        skipped_artifacts=skipped,
        dry_run=request.dry_run,
        incomplete_artifacts=incomplete,
    )


def _checkpoint_artifact_refs(
    *,
    registry: dict[str, object],
    artifact_refs: object,
    workspace_root: Path,
    stage_name: str,
) -> list[dict[str, object]]:
    registry_refs = registry.get("refs")
    if isinstance(registry_refs, list) and registry_refs:
        return [dict(ref) for ref in registry_refs if isinstance(ref, dict)]
    if not isinstance(artifact_refs, dict):
        return []
    refs: list[dict[str, object]] = []
    for artifact_name, raw_path in artifact_refs.items():
        name = str(artifact_name or "").strip()
        storage_ref = str(raw_path or "").strip()
        if not name or not storage_ref:
            continue
        path = Path(storage_ref).expanduser()
        if not path.is_absolute():
            path = workspace_root / path
        refs.append(
            {
                "artifact_id": name,
                "path": str(path),
                "producer_step": stage_name,
                "schema_version": "1.0",
            }
        )
    dependency_order = {
        "source_pdf": 0,
        "analysis_pdf": 1,
        "contents_image": 2,
        "preview_image": 2,
        "doc_map": 3,
        "artifacts": 4,
        "validation": 5,
        "rendered_html": 6,
    }
    return sorted(
        refs,
        key=lambda ref: (
            dependency_order.get(str(ref.get("artifact_id") or ""), 3),
            str(ref.get("artifact_id") or ""),
        ),
    )


def _checkpoint_dependencies(artifact_kind: str) -> list[str]:
    if artifact_kind == "analysis_pdf":
        return ["source_pdf"]
    if artifact_kind in {"contents_image", "preview_image"}:
        return ["analysis_pdf"]
    if artifact_kind == "rendered_html":
        return ["artifacts", "validation"]
    return (
        ["analysis_pdf"] if artifact_kind not in {"source_pdf", "analysis_pdf"} else []
    )


def _backfill_provenance(
    payload: dict[str, object], artifact_name: str
) -> tuple[str, str, dict[str, object]]:
    metadata: dict[str, object] = {"checkpoint_artifact_name": artifact_name}
    if artifact_name != "artifacts":
        return "", "", metadata
    analysis = payload.get("analysis")
    if not isinstance(analysis, dict):
        return "", "", metadata
    generated = analysis.get("artifacts_payload")
    if not isinstance(generated, dict):
        return "", "", metadata
    cache = generated.get("_cache")
    prompts = cache.get("prompts") if isinstance(cache, dict) else None
    if not isinstance(prompts, dict) or not prompts:
        return "", "", metadata
    prompt_hash = hashlib.sha256(_canonical_json(prompts).encode("utf-8")).hexdigest()
    models = sorted(
        {
            str(value.get("model") or "").strip()
            for value in prompts.values()
            if isinstance(value, dict) and str(value.get("model") or "").strip()
        }
    )
    metadata["prompt_hashes"] = prompts
    return prompt_hash, ",".join(models), metadata
