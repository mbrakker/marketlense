"""Opt-in regression against the retained, unmodified Activate source PDF."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.integration
def test_activate_candidate_extraction_completes_with_configured_workers(tmp_path):
    source = os.environ.get("MARKETLENSE_ACTIVATE_PDF", "")
    if not source:
        pytest.skip("Set MARKETLENSE_ACTIVATE_PDF to the retained Activate PDF")
    pdf = Path(source)
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == (
        "5f960886c6d6ee8cf355b4d469a6c1bc12080cd85351b4cb457c8565ae9dd4f2"
    )
    code = "\n".join(
        [
            "import sys, hashlib, json",
            "from dataclasses import asdict",
            "from src.contracts.report_assets import ExtractCandidatesRequest",
            "from src.services.config_service import new_runtime_context",
            "from src.services.pdf_service import collect_candidates",
            "request = ExtractCandidatesRequest(schema_version='1.0', "
            "pdf_path=sys.argv[1], out_dir=sys.argv[2], "
            "report_name='activate', parallel_workers=int(sys.argv[3]))",
            "result = collect_candidates(request, "
            "new_runtime_context(task_id='activate_candidate_regression'))",
            "payload = json.dumps([asdict(c) for c in result.candidates], "
            "sort_keys=True, default=str).encode()",
            "print(json.dumps({'count':len(result.candidates), "
            "'digest':hashlib.sha256(payload).hexdigest()}))",
        ]
    )
    results = []
    for workers in (1, 5):
        result = subprocess.run(
            [sys.executable, "-c", code, str(pdf), str(tmp_path), str(workers)],
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
        assert result.returncode == 0, result.stderr[-2000:]
        results.append(json.loads(result.stdout.strip().splitlines()[-1]))
    assert results[0]["count"] > 0
    assert results[0] == results[1]
