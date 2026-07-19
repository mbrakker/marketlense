from __future__ import annotations

import pytest

from scripts.quality.collect_cto_review_evidence import (
    EvidenceFreshnessError,
    EvidencePaths,
    collect,
)
from tests.test_collect_cto_review_evidence import _strict_paths


def test_strict_representative_bundle_requires_fresh_after_before_snapshot(
    tmp_path,
) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)
    paths = EvidencePaths(
        **{
            **paths.__dict__,
            "log_corpus_scope": "representative_report_processing",
        }
    )

    with pytest.raises(EvidenceFreshnessError):
        collect(paths)

    assert not paths.output_dir.exists()
