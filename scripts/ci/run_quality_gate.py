from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def quality_gate_commands() -> tuple[tuple[str, ...], ...]:
    return (
        ("python", "scripts/ci/check_formatting.py"),
        ("python", "scripts/ci/check_risk_policy.py"),
        ("python", "scripts/ci/check_split_symbol_links.py"),
        ("python", "scripts/ci/run_type_check.py"),
        ("python", "scripts/ci/check_architecture_imports.py"),
        ("python", "scripts/ci/check_agent_policy.py"),
        ("python", "scripts/ci/check_forbidden_patching.py"),
        ("python", "scripts/ci/check_bounded_logging.py"),
        ("python", "scripts/ci/check_repository_hygiene.py"),
        ("python", "scripts/ci/check_quality_ledger.py"),
        ("python", "scripts/ci/check_remediation_runbooks.py"),
        ("python", "scripts/ci/check_backlog_source.py"),
        ("python", "scripts/ci/check_documentation.py", "--check-generated"),
        (
            "python",
            "scripts/ci/check_contract_schemas.py",
            "--snapshot",
            "docs/quality/contract_schemas.json",
        ),
        ("python", "scripts/ci/check_wordpress_subproject.py"),
        ("python", "scripts/ci/check_public_site_seo_performance.py"),
        (
            "python",
            "-m",
            "pytest",
            "--cov=src",
            "--cov-report=xml",
            "--cov-report=term-missing",
        ),
        (
            "python",
            "scripts/ci/check_coverage.py",
            "--coverage-xml",
            "coverage.xml",
        ),
        (
            "python",
            "scripts/ci/run_mutation_gate.py",
            "--json-out",
            "mutation_results.json",
        ),
        (
            "python",
            "scripts/ci/check_quality_regression.py",
            "--baseline",
            "docs/quality/baseline_2026-02-21.json",
            "--coverage-xml",
            "coverage.xml",
            "--mutation-json",
            "mutation_results.json",
            "--docpack-root",
            "tests/fixtures/docpacks/golden",
            "--candidate-root",
            "tests/fixtures/candidate_extraction/golden",
        ),
        (
            "python",
            "scripts/ci/check_prompt_fixture_regression.py",
            "--baseline",
            "docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json",
            "--config",
            "src/config/app.yaml",
            "--iterations",
            "3",
        ),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the canonical local quality gate in CI order."
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print commands without executing them.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    commands = quality_gate_commands()
    for index, command in enumerate(commands, start=1):
        print(f"[{index}/{len(commands)}] {' '.join(command)}", flush=True)
        if args.list:
            continue
        completed = subprocess.run(command, cwd=ROOT, check=False)
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
