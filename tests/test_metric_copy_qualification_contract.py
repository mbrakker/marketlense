import pytest

from src.contracts.prompts import PromptLoadRequest
from src.contracts.run_context import RunContext
from src.services.prompt_service import load_prompt_set


@pytest.mark.parametrize(
    "namespace",
    [
        "report_vs/artifacts/insights_final",
        "report_vs/artifacts/regenerate/insights_final",
    ],
)
def test_metric_copy_prompt_preserves_methodology_in_standalone_copy(namespace):
    prompt = load_prompt_set(
        PromptLoadRequest(schema_version="1.0", namespace=namespace),
        RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
    )
    text = " ".join(prompt.user.text.split())
    assert "material methodology (including averaging)" in text
