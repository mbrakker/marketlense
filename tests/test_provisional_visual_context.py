from __future__ import annotations

import hashlib

from src.generators.verified_claims_canary import (
    VisualAuthorityCanaryConfig,
    build_visual_authority_admitter,
)
from src.utils.cache_utils import sha256_json
from tests._test_evidence_pack_generator._shared import _ctx
from tests._test_verified_claims_visual_generator.cases_01_visual import (
    _dependencies,
    _settings,
)


def test_canary_supplies_bound_page_text_without_recovery(tmp_path):
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"source-pdf")
    identity = "report|pdf-sha256:" + hashlib.sha256(pdf.read_bytes()).hexdigest()
    text = "Selected source page with a forecast caveat."
    finding = {"id": "f1", "text": "Provisional claim", "evidence": text, "pages": [4]}
    requests = []
    admit = build_visual_authority_admitter(
        config=VisualAuthorityCanaryConfig(
            source_identity=identity,
            dependencies=_dependencies(
                iter([{"claim": "", "status": "unresolved", "issues": []}]),
                [],
                requests,
            ),
        ),
        pdf_path=str(pdf),
        default_output_dir=str(tmp_path),
        report_name="report",
        evidence_packs={"findings": {"findings": []}},
        ctx=_ctx(),
        settings=_settings(tmp_path),
        doc_map={},
        visual_quarantine={
            "schema_version": "1.0",
            "source_identity": identity,
            "findings": [
                {
                    "finding": finding,
                    "source_references": [
                        {"evidence_id": "p4", "page": 4, "text_hash": sha256_json(text)}
                    ],
                }
            ],
        },
        source_spans=[
            {"id": "p4", "page": 4, "text": text},
            {"id": "p5", "page": 5, "text": "Unselected page text"},
        ],
    )
    assert not admit([]).verified_facts
    assert text in requests[1].user_prompt
    assert "Unselected page text" not in requests[1].user_prompt
    assert requests[1].image_paths
