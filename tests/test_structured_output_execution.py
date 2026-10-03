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
