import json

from src.contracts.openai import OpenAIFileSearchResult
from src.generators.structured_output_execution import shared_retrieval_context_json


def test_shared_retrieval_context_deduplicates_queries_across_results() -> None:
    queries = [f"search query {index} with report-specific detail" for index in range(6)]
    results = [
        OpenAIFileSearchResult(
            schema_version="1.0",
            queries=queries,
            file_id="file_report",
            filename="report.pdf",
            score=0.9 - index / 100,
            text=(f"Excerpt {index}. " + ("Evidence detail. " * 90)),
        )
        for index in range(40)
    ]

    serialized = shared_retrieval_context_json(results)
    payload = json.loads(serialized)

    assert len(payload["searches"]) == 1
    assert payload["searches"][0]["queries"] == queries
    assert len(payload["searches"][0]["results"]) == 40
    assert all(
        result["filename"] == "report.pdf"
        for result in payload["searches"][0]["results"]
    )
    assert len(serialized) <= 72_000


def test_oversized_shared_retrieval_keeps_high_score_results_from_each_search() -> None:
    results = [
        OpenAIFileSearchResult(
            schema_version="1.0",
            queries=[f"search group {group}"],
            file_id=f"file_{group}",
            filename="report.pdf",
            score=1.0 - rank / 100,
            text=f"group {group} rank {rank}. " + ("Evidence detail. " * 65),
        )
        for group in range(4)
        for rank in range(20)
    ]

    serialized = shared_retrieval_context_json(results)
    payload = json.loads(serialized)

    assert len(serialized) <= 72_000
    assert len(payload["searches"]) == 4
    assert 0 < sum(len(search["results"]) for search in payload["searches"]) < 80
    for group, search in enumerate(payload["searches"]):
        assert search["queries"] == [f"search group {group}"]
        assert search["results"][0]["text"].startswith(f"group {group} rank 0.")
