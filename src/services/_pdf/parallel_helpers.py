"""Shared deterministic parallel-work helpers for PDF candidate families."""

from __future__ import annotations

import os
from typing import Dict, List


def split_even_chunks(values: List[int], chunk_count: int) -> List[List[int]]:
    if not values:
        return []
    chunk_count = max(1, min(int(chunk_count), len(values)))
    chunks: List[List[int]] = [[] for _ in range(chunk_count)]
    for idx, value in enumerate(values):
        chunks[idx % chunk_count].append(value)
    return [chunk for chunk in chunks if chunk]


def resolve_candidate_parallel_workers(
    requested_workers: int,
    unit_count: int,
) -> int:
    if unit_count <= 1:
        return 1
    try:
        workers = int(requested_workers)
    except (TypeError, ValueError):
        workers = 0
    if workers <= 0:
        env_value = os.getenv("INGEST_REPORT_WORKER_LIMIT")
        if env_value:
            try:
                workers = int(env_value)
            except (TypeError, ValueError):
                workers = 0
    if workers <= 0:
        workers = max(2, min(6, (os.cpu_count() or 2)))
    return max(1, min(workers, unit_count, 8))


def tally_reason(stats: Dict[str, object], reason: str) -> None:
    reasons = stats.get("reasons")
    if not isinstance(reasons, dict):
        reasons = {}
        stats["reasons"] = reasons
    reasons[reason] = int(reasons.get(reason, 0)) + 1
