from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.ci.check_documentation import (
    validate_documentation,
    validate_markdown_links,
    validate_readme_hygiene,
)
from scripts.docs.generate_references import (
    collect_cli_commands,
    stale_generated_documents,
)

ROOT = Path(__file__).resolve().parents[1]


def test_generated_references_are_current_and_include_registered_commands() -> None:
    assert stale_generated_documents(ROOT) == ()
    command_names = {command.name for command in collect_cli_commands(ROOT)}
    reference = (ROOT / "docs" / "generated" / "cli-reference.md").read_text(
        encoding="utf-8"
    )

    for command_name in command_names:
        assert f"`{command_name}`" in reference


def test_documentation_gate_accepts_the_repository_documentation() -> None:
    assert validate_documentation(ROOT, check_generated=True) == ()


def test_readme_hygiene_rejects_dated_ledger_content(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# MarketLense\n\nLive verification on 2026-07-15 passed 73 tests.\n"
        "See CONSOLIDATED_TODO.md.\n",
        encoding="utf-8",
    )

    reasons = {violation.reason for violation in validate_readme_hygiene(tmp_path)}

    assert "contains dated implementation detail" in reasons
    assert "contains live verification ledger" in reasons
    assert "contains test-count narrative" in reasons


def test_markdown_link_validation_detects_missing_relative_file(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text(
        "[Missing guide](docs/missing.md)\n", encoding="utf-8"
    )

    violations = validate_markdown_links(tmp_path)

    assert violations == (
        type(violations[0])(
            path=Path("README.md"), reason="missing link target: docs/missing.md"
        ),
    )


def test_markdown_link_validation_allows_ignored_runtime_artifact_pointers(
    tmp_path: Path,
) -> None:
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text(
        "[Run output](out/validation/report.html)\n",
        encoding="utf-8",
    )

    assert validate_markdown_links(tmp_path) == ()
