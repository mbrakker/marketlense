from __future__ import annotations

import hashlib
from copy import deepcopy

from src.generators.verified_claims_canary import (
    VisualAuthorityCanaryConfig,
    build_visual_authority_admitter,
)
from tests._test_artifact_generator._shared import _ctx
from tests._test_verified_claims_visual_generator.cases_01_visual import (
    _dependencies as _visual_dependencies,
    _settings as _visual_settings,
)
from tests.test_verified_claims_visual_authority_canary import (
    _candidate,
    _evidence_packs,
)


def test_visual_admission_uses_direct_finding_page_before_rendering(tmp_path):
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"source-pdf")
    source_sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    source_identity = f"frozen-report|pdf-sha256:{source_sha}"
    candidate = _candidate(page=20)
    evidence_packs = _evidence_packs(candidate)
    evidence_packs["findings"]["findings"][0]["pages"] = [21]

    responses = iter(
        [
            {"claim": candidate["text"], "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "Page 21 reports the metric value for the stated buyer cohort."
                ),
                "verified_fact": {
                    "statement": candidate["text"],
                    "metric": deepcopy(candidate["metric"]),
                    "qualifiers": [],
                },
            },
        ]
    )
    render_calls = []
    requests = []
    admit = build_visual_authority_admitter(
        config=VisualAuthorityCanaryConfig(
            source_identity=source_identity,
            dependencies=_visual_dependencies(responses, render_calls, requests),
        ),
        pdf_path=str(pdf_path),
        default_output_dir=str(tmp_path),
        report_name="Frozen report",
        evidence_packs=evidence_packs,
        ctx=_ctx(),
        settings=_visual_settings(tmp_path),
        doc_map={},
    )

    admission = admit([candidate])

    assert admission.audit["quarantined"] == []
    assert admission.verified_facts[0]["supporting_physical_pages"] == [21]
    assert [request.page for request in render_calls] == [20]
    assert len(requests[0].image_paths) == 1
    assert (
        requests[0]
        .image_paths[0]
        .replace("/", "\\")
        .endswith("\\report\\crop_refine_pages\\page-20.png")
    )
