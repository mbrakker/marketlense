"""Read-only retained-corpus benchmark for semantic evidence preselection.

It never calls a provider or creates embeddings.  When a retained embedding
export is supplied, it compares its semantic ranking to deterministic lexical
ordering; otherwise it records the existing safe fallback explicitly.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class SemanticPreselectionLane:
    schema_version: str
    lane: str
    mode: str
    candidate_count: int
    selected_count: int
    prompt_chars_before: int
    prompt_chars_after: int
    estimated_tokens_before: int
    estimated_tokens_after: int
    evidence_overlap: float
    source_coverage: float
    citation_coverage: float
    coverage_status: str


@dataclass(frozen=True)
class SemanticPreselectionBenchmark:
    schema_version: str
    artifact_count: int
    embedding_count: int
    lanes: tuple[SemanticPreselectionLane, ...]
    warnings: tuple[str, ...]
    failures: tuple[str, ...]


def build_semantic_preselection_benchmark(
    *,
    artifact_paths: list[str],
    embedding_vectors: dict[str, list[float]] | None = None,
    max_evidence_items: int = 12,
    coverage_loss_threshold: float = 0.10,
) -> SemanticPreselectionBenchmark:
    """Compare retained lexical order with supplied retained semantic vectors."""
    candidates: list[dict[str, str]] = []
    for raw_path in sorted(artifact_paths):
        payload = json.loads(Path(raw_path).read_text(encoding="utf-8"))
        report_id = str(payload.get("report_id") or Path(raw_path).parent.parent.name)
        for index, item in enumerate(
            payload.get("insights_final") or payload.get("insights") or []
        ):
            if not isinstance(item, dict):
                continue
            evidence_id = str(item.get("evidence_id") or item.get("id") or index)
            text = str(item.get("evidence") or item.get("text") or "").strip()
            if text:
                candidates.append(
                    {
                        "id": f"{report_id}:{evidence_id}",
                        "report_id": report_id,
                        "evidence_id": evidence_id,
                        "text": text,
                    }
                )
    lexical = sorted(
        candidates, key=lambda item: (item["report_id"], item["evidence_id"])
    )[:max_evidence_items]
    usable_vectors = embedding_vectors or {}
    semantic_scored = [
        (item, _vector_score(usable_vectors.get(item["id"])))
        for item in candidates
        if _vector_score(usable_vectors.get(item["id"])) is not None
    ]
    if semantic_scored:
        semantic = [
            item
            for item, _score in sorted(
                semantic_scored, key=lambda item: (-float(item[1]), item[0]["id"])
            )[:max_evidence_items]
        ]
        mode = "retained_semantic"
    else:
        semantic = lexical
        mode = "deterministic_fallback_no_retained_embeddings"
    lane = _lane(
        "Briefing", candidates, lexical, semantic, mode, coverage_loss_threshold
    )
    signal_lane = _lane(
        "Signal", candidates, lexical, semantic, mode, coverage_loss_threshold
    )
    failures = tuple(
        sorted(
            {
                value
                for row in (lane, signal_lane)
                if row.coverage_status == "fail"
                for value in (f"{row.lane.lower()}_coverage_loss",)
            }
        )
    )
    warnings = tuple(
        sorted(
            {
                value
                for row in (lane, signal_lane)
                if row.coverage_status == "warn"
                for value in (f"{row.lane.lower()}_coverage_loss",)
            }
        )
    )
    return SemanticPreselectionBenchmark(
        "1.0",
        len(artifact_paths),
        len(usable_vectors),
        (lane, signal_lane),
        warnings,
        failures,
    )


def _lane(
    lane: str,
    candidates: list[dict[str, str]],
    lexical: list[dict[str, str]],
    semantic: list[dict[str, str]],
    mode: str,
    threshold: float,
) -> SemanticPreselectionLane:
    lexical_sources = {item["report_id"] for item in lexical}
    semantic_sources = {item["report_id"] for item in semantic}
    source_coverage = _share(len(semantic_sources), len(lexical_sources))
    citations = _share(
        sum(bool(item["evidence_id"]) for item in semantic), len(semantic)
    )
    overlap = _share(
        len({item["id"] for item in lexical} & {item["id"] for item in semantic}),
        len({item["id"] for item in lexical}),
    )
    status = (
        "pass"
        if source_coverage >= 1 - threshold and citations >= 1 - threshold
        else "fail"
    )
    before = sum(len(item["text"]) for item in candidates)
    after = sum(len(item["text"]) for item in semantic)
    return SemanticPreselectionLane(
        "1.0",
        lane,
        mode,
        len(candidates),
        len(semantic),
        before,
        after,
        (before + 3) // 4,
        (after + 3) // 4,
        overlap,
        source_coverage,
        citations,
        status,
    )


def _vector_score(vector: list[float] | None) -> float | None:
    if not vector or not all(isinstance(value, (int, float)) for value in vector):
        return None
    return sum(float(value) * float(value) for value in vector)


def _share(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 1.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", nargs="+")
    parser.add_argument("--retained-embeddings-json", default="")
    parser.add_argument("--output-json", default="")
    args = parser.parse_args(argv)
    vectors = (
        json.loads(Path(args.retained_embeddings_json).read_text(encoding="utf-8"))
        if args.retained_embeddings_json
        else None
    )
    benchmark = build_semantic_preselection_benchmark(
        artifact_paths=args.artifacts,
        embedding_vectors=vectors if isinstance(vectors, dict) else None,
    )
    payload = json.dumps(asdict(benchmark), ensure_ascii=True, indent=2, sort_keys=True)
    if args.output_json:
        Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_json).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 1 if benchmark.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
