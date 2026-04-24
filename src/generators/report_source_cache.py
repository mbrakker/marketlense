from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Generic, Optional, TypeVar

from src.contracts.ingest import IngestSettings
from src.contracts.run_context import RunContext
from src.generators.report_generation_dependencies import ReportGeneratorDependencies
from src.generators.report_generation_shared import (
    cache_dir,
    cache_path,
    logger,
    read_cache_json,
    write_cache_json,
)
from src.utils.logging import log_event

T = TypeVar("T")


@dataclass(frozen=True)
class ReportSourceCacheBinding:
    schema_version: str = field(
        metadata={"doc": "Report-source cache binding schema version."}
    )
    phase: str = field(
        metadata={"doc": "Logical source phase name, for example pdf_info or text."}
    )
    file_id: str = field(
        metadata={"doc": "Drive/local file identifier used for structured logs."}
    )
    cache_key: str = field(
        metadata={"doc": "Deterministic cache key for the bound source phase."}
    )
    cache_path: str = field(
        metadata={"doc": "Resolved cache JSON path when caching is enabled."}
    )
    enabled: bool = field(
        metadata={"doc": "Whether this source phase currently has cache support."}
    )


@dataclass(frozen=True)
class ReportSourceCacheLoadResult(Generic[T]):
    schema_version: str = field(
        metadata={"doc": "Report-source cache load result schema version."}
    )
    status: str = field(
        metadata={"doc": "Cache load status: cache_disabled|miss|hit."}
    )
    cache_hit: bool = field(
        metadata={"doc": "True when a typed cached value was returned."}
    )
    value: Optional[T] = field(
        default=None,
        metadata={"doc": "Typed cached value when the result is a cache hit."},
    )


def bind_report_source_cache(
    *,
    settings: IngestSettings,
    md5: str | None,
    file_id: str,
    phase: str,
    prefix: str,
    cache_key: str,
) -> ReportSourceCacheBinding:
    if not md5:
        return ReportSourceCacheBinding(
            schema_version="1.0",
            phase=phase,
            file_id=file_id,
            cache_key=cache_key,
            cache_path="",
            enabled=False,
        )
    root = cache_dir(settings, md5)
    return ReportSourceCacheBinding(
        schema_version="1.0",
        phase=phase,
        file_id=file_id,
        cache_key=cache_key,
        cache_path=str(cache_path(root, prefix, cache_key)),
        enabled=True,
    )


def load_report_source_cache(
    binding: ReportSourceCacheBinding,
    *,
    ctx: RunContext,
    dependencies: ReportGeneratorDependencies,
    adapt_payload: Callable[[dict[str, object]], Optional[T]],
) -> ReportSourceCacheLoadResult[T]:
    if not binding.enabled or not binding.cache_path or not binding.cache_key:
        return ReportSourceCacheLoadResult(
            schema_version="1.0",
            status="cache_disabled",
            cache_hit=False,
            value=None,
        )

    cached = read_cache_json(Path(binding.cache_path), ctx, dependencies)
    if cached and cached.get("key") == binding.cache_key:
        adapted = adapt_payload(cached)
        if adapted is not None:
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event=f"{binding.phase}_cache_hit",
                    module=logger.name,
                    fields={
                        "file_id": binding.file_id,
                        "cache_path": binding.cache_path,
                    },
                )
            )
            return ReportSourceCacheLoadResult(
                schema_version="1.0",
                status="hit",
                cache_hit=True,
                value=adapted,
            )

    logger.info(
        log_event(
            ctx,
            role="generator",
            event=f"{binding.phase}_cache_miss",
            module=logger.name,
            fields={
                "file_id": binding.file_id,
                "cache_path": binding.cache_path,
            },
        )
    )
    return ReportSourceCacheLoadResult(
        schema_version="1.0",
        status="miss",
        cache_hit=False,
        value=None,
    )


def write_report_source_cache(
    binding: ReportSourceCacheBinding,
    *,
    payload: dict[str, object],
    ctx: RunContext,
    dependencies: ReportGeneratorDependencies,
) -> None:
    if not binding.enabled or not binding.cache_path:
        return
    write_cache_json(
        Path(binding.cache_path),
        dict(payload),
        ctx,
        dependencies,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event=f"{binding.phase}_cache_written",
            module=logger.name,
            fields={
                "file_id": binding.file_id,
                "cache_path": binding.cache_path,
            },
        )
    )
