import json

import pytest

from scripts.quality.replay_verified_claims_step2 import _load_explicit_cohort_inputs
from tests.test_verified_claims_step2_provenance import _explicit_snapshot


def _snapshot(tmp_path, *, conflict=""):
    cohort, manifest = _explicit_snapshot(
        tmp_path,
        {"id": "claim", "text": "A retained claim.", "pages": [1]},
    )
    source = json.loads(manifest.read_text(encoding="utf-8"))
    digest = source["source_pdfs"]["Test Report"]["sha256"]
    identity = f"source:original|pdf-sha256:{digest}"
    artifact_path = next((tmp_path / "run").rglob("artifacts.json"))
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["insights_final"][0].update(
        {
            "evidence_id": "verified-fact:f1",
            "evidence_spans": [
                {
                    "evidence_id": "verified-fact:f1",
                    "page": 1,
                    "source_identity": (
                        f"source:other|pdf-sha256:{digest}"
                        if conflict == "span"
                        else identity
                    ),
                }
            ],
        }
    )
    artifact["verified_facts"] = [
        {
            "schema_version": "1.0",
            "fact_id": "f1",
            "statement": "A retained fact.",
            "metric": {},
            "source_identity": identity,
            "source_pdf_sha256": "b" * 64 if conflict == "fact_hash" else digest,
            "supporting_physical_pages": [1],
            "verification_outcome": "verified",
            "provenance": {
                "inspected_physical_pages": [1],
                "source_truth_notes_by_page": {"1": "A retained fact."},
            },
        }
    ]
    if conflict == "other_pdf":
        artifact["verified_facts"][0]["source_identity"] = (
            f"source:original|pdf-sha256:{'b' * 64}"
        )
        artifact["verified_facts"][0]["source_pdf_sha256"] = "b" * 64
    if conflict == "manifest_hash":
        source["source_pdfs"]["Test Report"]["sha256"] = "b" * 64
        manifest.write_text(json.dumps(source), encoding="utf-8")
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    return cohort, manifest, identity


def test_explicit_replay_reuses_verified_snapshot_identity(tmp_path):
    cohort, manifest, identity = _snapshot(tmp_path)
    report = _load_explicit_cohort_inputs(cohort, manifest)["reports"][0]
    assert report["source_identity"] == identity
    assert len(report["eligible_claims"]) == 1


@pytest.mark.parametrize(
    "conflict", ["span", "fact_hash", "other_pdf", "manifest_hash"]
)
def test_explicit_replay_rejects_conflicting_source_bindings(tmp_path, conflict):
    cohort, manifest, _ = _snapshot(tmp_path, conflict=conflict)
    report = _load_explicit_cohort_inputs(cohort, manifest)["reports"][0]
    assert report["eligible_claims"] == []
    assert report["unavailable"]
