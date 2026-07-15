from __future__ import annotations

from pathlib import Path

from scripts.ci.check_agent_policy import validate_agent_policy

ROOT = Path(__file__).resolve().parents[1]


def test_repository_agent_policy_is_concise_and_safe() -> None:
    assert validate_agent_policy(ROOT / "AGENTS.md", max_lines=1000) == ()


def test_agent_policy_gate_rejects_duplicate_headings_and_local_paths(
    tmp_path: Path,
) -> None:
    policy = tmp_path / "AGENTS.md"
    policy.write_text(
        "# Policy\n## Same\n## Same\nC:\\Users\\Someone\\secret\n",
        encoding="utf-8",
    )

    reasons = [item.reason for item in validate_agent_policy(policy, max_lines=1000)]

    assert any("duplicate headings" in reason for reason in reasons)
    assert any("user-specific absolute path" in reason for reason in reasons)
