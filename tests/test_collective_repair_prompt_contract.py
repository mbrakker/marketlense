from src.contracts.prompts import PromptLoadRequest
from src.contracts.run_context import RunContext
from src.services.prompt_service import load_prompt_set


def test_report_repair_prompt_distinguishes_collective_and_single_target():
    prompt = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/validate/public_editorial_quality",
        ),
        RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
    )
    text = " ".join(prompt.system.text.split())
    assert "For a single-target report repair" in text
    assert "collective insight-leaf repairs use repair_items" in text
    assert "Nominations require empty affected_item_id and repair_target" in text


def test_review_prompt_checks_distinct_contributions_within_insight_pairs():
    prompt = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/validate/public_editorial_quality",
        ),
        RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
    )
    text = " ".join(prompt.system.text.split())
    assert "Assess each insight's so_what and now_what together" in text
    assert "a restated imperative is not a distinct action" in text


def test_review_prompt_distinguishes_descriptive_differences_from_significance():
    prompt = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/validate/public_editorial_quality",
        ),
        RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
    )
    text = " ".join(prompt.system.text.split())
    assert "Do not infer statistical significance from a descriptive" in text
    assert "do not call an omitted uncertainty measure source-stated" in text
