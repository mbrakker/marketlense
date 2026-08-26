"""Bounded live A/B benchmark for claim-embedding retrieval and throughput.

The script reads retained claim text only, makes bounded OpenAI embedding calls,
and writes scalar measurements without retaining claim text or vectors.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.contracts.config import ConfigLoadRequest
from src.contracts.openai import OpenAIEmbeddingRequest
from src.services import llm_service
from src.services.config_service import load_settings, new_runtime_context
from src.utils.costing import estimate_cost_usd

Embed = Callable[[str, list[str], int], tuple[list[list[float]], int, float]]


@dataclass(frozen=True)
class ClaimEmbeddingBenchmarkLane:
    model: str
    dimensions: int
    batch_size: int
    claim_count: int
    query_count: int
    provider_call_count: int
    input_tokens: int
    total_processing_seconds: float
    claims_per_second: float
    provider_latency_p50_ms: float
    provider_latency_p95_ms: float
    recall_at_5: float
    mean_reciprocal_rank: float
    cost_per_1m_input_tokens_usd: float
    cost_per_1000_claims_usd: float
    total_estimated_cost_usd: float
    vector_storage_bytes_per_claim: int
    completed: bool


@dataclass(frozen=True)
class ClaimEmbeddingBenchmark:
    schema_version: str
    corpus_claim_count: int
    query_count: int
    lanes: tuple[ClaimEmbeddingBenchmarkLane, ClaimEmbeddingBenchmarkLane]
    vector_storage_change_bytes_per_claim: int
    vector_storage_change_percent: float
    cost_change_percent: float
    throughput_change_percent: float
    quality_change_mrr: float
    quality_change_recall_at_5: float


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _percent_change(before: float, after: float) -> float:
    return round(((after - before) / before) * 100, 4) if before else 0.0


def _percent_reduction(before: float, after: float) -> float:
    return round(((before - after) / before) * 100, 4) if before else 0.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return round(ordered[math.ceil(len(ordered) * percentile) - 1], 4)


def _run_lane(
    *,
    model: str,
    dimensions: int,
    batch_size: int,
    claims: list[tuple[str, str]],
    query_claim_uids: list[str],
    embed: Embed,
    cost_per_1m_input_tokens_usd: float,
) -> ClaimEmbeddingBenchmarkLane:
    claim_uids = [claim_uid for claim_uid, _ in claims]
    claim_texts = [text for _, text in claims]
    text_by_uid = dict(claims)
    query_texts = [text_by_uid[claim_uid] for claim_uid in query_claim_uids]
    call_latencies: list[float] = []
    input_tokens = 0
    started = time.monotonic()

    def embed_all(texts: list[str]) -> list[list[float]]:
        nonlocal input_tokens
        vectors: list[list[float]] = []
        for chunk in _chunks(texts, batch_size):
            response_vectors, tokens, latency_ms = embed(model, chunk, dimensions)
            if len(response_vectors) != len(chunk) or any(
                len(vector) != dimensions for vector in response_vectors
            ):
                raise ValueError("embedding response did not match the requested batch")
            vectors.extend(response_vectors)
            input_tokens += tokens
            call_latencies.append(latency_ms)
        return vectors

    claim_vectors = embed_all(claim_texts)
    query_vectors = embed_all(query_texts)
    total_seconds = time.monotonic() - started
    ranks: list[int] = []
    for query_uid, query_vector in zip(query_claim_uids, query_vectors, strict=True):
        ranking = sorted(
            zip(claim_uids, claim_vectors, strict=True),
            key=lambda item: (-_cosine(query_vector, item[1]), item[0]),
        )
        ranks.append(
            next(
                index
                for index, (uid, _) in enumerate(ranking, start=1)
                if uid == query_uid
            )
        )
    recall_at_5 = sum(rank <= 5 for rank in ranks) / len(ranks) if ranks else 0.0
    mrr = sum(1 / rank for rank in ranks) / len(ranks) if ranks else 0.0
    total_cost = (input_tokens / 1_000_000) * cost_per_1m_input_tokens_usd
    return ClaimEmbeddingBenchmarkLane(
        model=model,
        dimensions=dimensions,
        batch_size=batch_size,
        claim_count=len(claims),
        query_count=len(query_claim_uids),
        provider_call_count=len(call_latencies),
        input_tokens=input_tokens,
        total_processing_seconds=round(total_seconds, 4),
        claims_per_second=round(len(claims) / total_seconds, 4)
        if total_seconds
        else 0.0,
        provider_latency_p50_ms=round(statistics.median(call_latencies), 4)
        if call_latencies
        else 0.0,
        provider_latency_p95_ms=_percentile(call_latencies, 0.95),
        recall_at_5=round(recall_at_5, 4),
        mean_reciprocal_rank=round(mrr, 4),
        cost_per_1m_input_tokens_usd=cost_per_1m_input_tokens_usd,
        cost_per_1000_claims_usd=round(total_cost / len(claims) * 1000, 8)
        if claims
        else 0.0,
        total_estimated_cost_usd=round(total_cost, 8),
        vector_storage_bytes_per_claim=dimensions * 4,
        completed=True,
    )


def build_claim_embedding_benchmark(
    *,
    claims: list[tuple[str, str]],
    query_claim_uids: list[str],
    embed: Embed,
    small_dimensions: int = 1536,
    large_dimensions: int = 1024,
    large_batch_size: int = 25,
    small_cost_per_1m_input_tokens_usd: float = 0.02,
    large_cost_per_1m_input_tokens_usd: float = 0.13,
) -> ClaimEmbeddingBenchmark:
    old = _run_lane(
        model="text-embedding-3-small",
        dimensions=small_dimensions,
        batch_size=1,
        claims=claims,
        query_claim_uids=query_claim_uids,
        embed=embed,
        cost_per_1m_input_tokens_usd=small_cost_per_1m_input_tokens_usd,
    )
    new = _run_lane(
        model="text-embedding-3-large",
        dimensions=large_dimensions,
        batch_size=large_batch_size,
        claims=claims,
        query_claim_uids=query_claim_uids,
        embed=embed,
        cost_per_1m_input_tokens_usd=large_cost_per_1m_input_tokens_usd,
    )
    return ClaimEmbeddingBenchmark(
        schema_version="1.0",
        corpus_claim_count=len(claims),
        query_count=len(query_claim_uids),
        lanes=(old, new),
        vector_storage_change_bytes_per_claim=(
            new.vector_storage_bytes_per_claim - old.vector_storage_bytes_per_claim
        ),
        vector_storage_change_percent=_percent_reduction(
            old.vector_storage_bytes_per_claim, new.vector_storage_bytes_per_claim
        ),
        cost_change_percent=_percent_change(
            old.total_estimated_cost_usd, new.total_estimated_cost_usd
        ),
        throughput_change_percent=_percent_change(
            old.claims_per_second, new.claims_per_second
        ),
        quality_change_mrr=round(
            new.mean_reciprocal_rank - old.mean_reciprocal_rank, 4
        ),
        quality_change_recall_at_5=round(new.recall_at_5 - old.recall_at_5, 4),
    )


def _read_claims(reports_db: str, limit: int) -> list[tuple[str, str]]:
    with sqlite3.connect(reports_db) as connection:
        rows = connection.execute(
            """
            SELECT claim_uid, claim
            FROM report_claims
            WHERE trim(claim) <> ''
            ORDER BY claim_uid
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [(str(claim_uid), str(claim).strip()) for claim_uid, claim in rows]


def _query_claim_uids(claims: list[tuple[str, str]], count: int) -> list[str]:
    if not claims or count <= 0:
        return []
    positions = {
        round(index * (len(claims) - 1) / max(1, min(count, len(claims)) - 1))
        for index in range(min(count, len(claims)))
    }
    return [claims[index][0] for index in sorted(positions)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-db", default="state/reports.sqlite")
    parser.add_argument("--claim-limit", type=int, default=100)
    parser.add_argument("--query-count", type=int, default=20)
    parser.add_argument("--large-batch-size", type=int, default=25)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args(argv)
    claims = _read_claims(args.reports_db, max(1, args.claim_limit))
    query_claim_uids = _query_claim_uids(claims, args.query_count)
    if len(claims) < 2 or not query_claim_uids:
        raise SystemExit("The benchmark requires at least two retained claim rows.")
    ctx = new_runtime_context(task_id="claim_embedding_ab_benchmark")
    settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    pricing = settings.model_pricing

    def live_embed(
        model: str, inputs: list[str], dimensions: int
    ) -> tuple[list[list[float]], int, float]:
        started = time.monotonic()
        response = llm_service.openai_create_embeddings(
            OpenAIEmbeddingRequest(
                schema_version="1.0",
                api_key=settings.openai_api_key,
                model=model,
                inputs=inputs,
                dimensions=dimensions,
                timeout_seconds=120.0,
                model_pricing=pricing,
                prompt_namespace="claim_embedding/ab_benchmark",
                execution_identity=f"claim_embedding.ab_benchmark:{model}:d{dimensions}",
                execution_policy_hash="claim_embedding.ab_benchmark.v1",
                workflow="claim_embedding_ab_benchmark",
                stage="provider_embedding",
                artifact_family="claim",
            ),
            ctx,
        )
        return (
            response.embeddings,
            int(response.input_tokens or 0),
            (time.monotonic() - started) * 1000,
        )

    benchmark = build_claim_embedding_benchmark(
        claims=claims,
        query_claim_uids=query_claim_uids,
        embed=live_embed,
        large_batch_size=max(1, args.large_batch_size),
        small_cost_per_1m_input_tokens_usd=estimate_cost_usd(
            "text-embedding-3-small", 1_000_000, 0, 0, pricing
        ),
        large_cost_per_1m_input_tokens_usd=estimate_cost_usd(
            "text-embedding-3-large", 1_000_000, 0, 0, pricing
        ),
    )
    output = Path(args.output_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(asdict(benchmark), ensure_ascii=True, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
