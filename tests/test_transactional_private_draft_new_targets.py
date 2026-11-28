"""Scoped, evidence-bound targets discovered during private refinement."""

import pytest

from tests.test_transactional_private_draft_refinement import _run_draft_scenario


def test_claim_scoped_summary_reconstruction_can_refine_private_draft(tmp_path):
    _run_draft_scenario(tmp_path, "summary_claim_draft")


def test_private_draft_refines_newly_reviewed_linkedin_sentence(tmp_path):
    _run_draft_scenario(tmp_path, "linkedin_nomination")


@pytest.mark.parametrize(
    "case",
    [
        "factual",
        "source_integrity",
        "empty_evidence",
        "unknown_evidence",
        "unknown_identity",
    ],
)
def test_private_draft_rejects_unsafe_linkedin_review(tmp_path, case):
    _run_draft_scenario(tmp_path, f"linkedin_negative_{case}")
