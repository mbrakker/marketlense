from __future__ import annotations

import sys
from pathlib import Path

from pydantic import BaseModel

VENDORED_BROWSER_USE_ROOT = (
    Path(__file__).resolve().parents[1] / "tools" / "browser-use"
)
if str(VENDORED_BROWSER_USE_ROOT) not in sys.path:
    sys.path.insert(0, str(VENDORED_BROWSER_USE_ROOT))

from browser_use.agent.service import Agent
from browser_use.tools.views import StructuredOutputAction


class _ExampleOutput(BaseModel):
    name: str
    value: int


def test_structured_output_action_accepts_flattened_payload() -> None:
    parsed = StructuredOutputAction[_ExampleOutput].model_validate(
        {
            "name": "example",
            "value": 7,
            "success": True,
        }
    )

    assert parsed.success is True
    assert parsed.data.name == "example"
    assert parsed.data.value == 7


def test_agent_enhance_task_mentions_done_data_wrapper() -> None:
    agent = Agent.__new__(Agent)

    enhanced = Agent._enhance_task_with_schema(
        agent,
        "Acquire the report.",
        _ExampleOutput,
    )

    assert "done.data" in enhanced
    assert '"name"' in enhanced
