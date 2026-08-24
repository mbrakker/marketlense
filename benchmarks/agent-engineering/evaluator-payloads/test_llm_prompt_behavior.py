"""Evaluator-only behavioral check for ML-LLM-001.

This payload deliberately discovers a candidate validation entrypoint at runtime
instead of importing a historical helper, request contract, or implementation.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


# The injector places this evaluator-owned payload below ``benchmarks/`` in a
# detached historical worktree, so the working directory is the repository
# root. Do not infer an implementation path from this payload's location.
ROOT = Path.cwd()
PROMPT_TO_MUTATE = ROOT / "src/prompts/pdf_text/ocr_fallback/user.yaml"


def _validator_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for name in tuple(environment):
        if any(token in name.upper() for token in ("OPENAI", "OPENROUTER", "API_KEY")):
            environment.pop(name, None)
    environment.update(
        {
            "ALL_PROXY": "http://127.0.0.1:9",
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "",
        }
    )
    return environment


def _run_validator() -> subprocess.CompletedProcess[str]:
    launcher = r'''
import importlib
import inspect
import subprocess
import sys
from pathlib import Path

root = Path.cwd()
context_module = importlib.import_module("src.contracts.run_context")
service = importlib.import_module("src.services.prompt_service")
context = context_module.RunContext(
    schema_version="1.0", run_id="benchmark", task_id="prompt", span_id="check"
)
for name, candidate in inspect.getmembers(service, inspect.isfunction):
    if name.startswith("_") or "validat" not in name.lower():
        continue
    parameters = list(inspect.signature(candidate).parameters.values())
    required = [
        parameter
        for parameter in parameters
        if parameter.default is inspect.Parameter.empty
        and parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD, parameter.KEYWORD_ONLY)
    ]
    if not required:
        candidate()
        sys.exit(0)
    if len(required) == 1 and required[0].name in {"ctx", "context", "run_context"}:
        candidate(**{required[0].name: context})
        sys.exit(0)
for path in sorted((root / "scripts").rglob("*.py")):
    name = path.name.lower()
    if "prompt" in name and "validat" in name:
        completed = subprocess.run([sys.executable, str(path)], cwd=root, check=False)
        sys.exit(completed.returncode)
raise RuntimeError("no public deterministic prompt-validation entrypoint found")
'''
    return subprocess.run(
        [sys.executable, "-c", launcher],
        cwd=ROOT,
        env=_validator_environment(),
        capture_output=True,
        text=True,
        check=False,
    )


def test_registered_prompt_resources_validate_without_provider_credentials() -> None:
    result = _run_validator()

    assert result.returncode == 0, result.stderr or result.stdout


def test_missing_prompt_data_fails_explicitly() -> None:
    original = PROMPT_TO_MUTATE.read_bytes()
    try:
        PROMPT_TO_MUTATE.write_text(
            'text: "{{ benchmark_missing_value }}"\n', encoding="utf-8"
        )
        result = _run_validator()
    finally:
        PROMPT_TO_MUTATE.write_bytes(original)

    assert result.returncode != 0


def test_malformed_prompt_template_fails_explicitly() -> None:
    original = PROMPT_TO_MUTATE.read_bytes()
    try:
        PROMPT_TO_MUTATE.write_text('text: "{{ broken"\n', encoding="utf-8")
        result = _run_validator()
    finally:
        PROMPT_TO_MUTATE.write_bytes(original)

    assert result.returncode != 0
