from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ci.policy import load_architecture_policy

AGENTS_PATH = ROOT / "AGENTS.md"
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
USER_PATH = re.compile(r"[A-Za-z]:\\Users\\|/Users/|/home/")
RESIDUE = (
    "I preserved your tone",
    "production-grade rewrite",
    "rewrite of your document",
)


@dataclass(frozen=True)
class PolicyViolation:
    reason: str


def validate_agent_policy(path: Path, *, max_lines: int) -> tuple[PolicyViolation, ...]:
    text = path.read_text(encoding="utf-8")
    violations: list[PolicyViolation] = []
    line_count = len(text.splitlines())
    if line_count > max_lines:
        violations.append(
            PolicyViolation(f"AGENTS.md has {line_count} lines; maximum is {max_lines}")
        )
    headings = [heading.strip().casefold() for heading in HEADING.findall(text)]
    duplicates = sorted(
        {heading for heading in headings if headings.count(heading) > 1}
    )
    if duplicates:
        violations.append(
            PolicyViolation(f"duplicate headings: {', '.join(duplicates)}")
        )
    if USER_PATH.search(text):
        violations.append(PolicyViolation("contains a user-specific absolute path"))
    lowered = text.casefold()
    for phrase in RESIDUE:
        if phrase.casefold() in lowered:
            violations.append(
                PolicyViolation(f"contains conversational rewrite residue: {phrase}")
            )
    unsafe_logging = (
        "must log exact rendered prompt",
        "must log raw model response",
        "logging required: exact rendered prompt",
    )
    if any(phrase in lowered for phrase in unsafe_logging):
        violations.append(
            PolicyViolation("requires unsafe prompt or raw-response logging")
        )
    return tuple(violations)


def main() -> int:
    policy = load_architecture_policy()
    max_lines = int(policy["policy_validation"]["agents_max_lines"])
    violations = validate_agent_policy(AGENTS_PATH, max_lines=max_lines)
    if not violations:
        print("Agent policy checks passed.")
        return 0
    print("Agent policy checks failed:")
    for violation in violations:
        print(f"  - {violation.reason}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
