# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_collect_cto_review_evidence.py"
)

from ._shared import *  # noqa: F401,F403


def test_strict_clean_exact_head_snapshots_logs_and_publishes_redacted_bundle(
    tmp_path: Path,
) -> None:
    paths, sha, source, editorial = _strict_paths(tmp_path)
    (paths.log_dir / "ignored.log").write_text(source, encoding="utf-8")

    collect(paths)

    manifest = json.loads((paths.output_dir / "evidence_run_manifest.json").read_text())
    snapshots = json.loads((paths.output_dir / "snapshot_manifest.json").read_text())
    leakage = json.loads((paths.output_dir / "log_content_leakage.json").read_text())
    validation = json.loads(
        (paths.output_dir / "consistency_validation.json").read_text()
    )
    assert manifest["repository"] == {
        "expected_commit_sha": sha,
        "start_commit_sha": sha,
        "end_commit_sha": sha,
        "head_stable": True,
        "dirty_worktree_start": False,
        "dirty_worktree_end": False,
        "exact_head_verified": True,
    }
    assert snapshots["log_snapshots"][0]["source_path"] == "market_lense_2026-07-16.log"
    assert len(snapshots["log_snapshots"]) == 1
    assert snapshots["log_snapshots"][0]["snapshot_path"].startswith("standard_logs/")
    assert (
        snapshots["log_snapshots"][0]["structured_event_metadata_mode"]
        == "matches_only"
    )
    assert leakage["status"] == "passed"
    assert leakage["coverage"]["source_canary_count"] == 5
    assert leakage["coverage"]["editorial_canary_count"] == 5
    assert validation["passed"] is True
    assert validation["repository_commit_sha"] == sha
    rendered = "\n".join(
        path.read_text(encoding="utf-8")
        for path in paths.output_dir.iterdir()
        if path.suffix in {".json", ".csv"}
    )
    assert source not in rendered
    assert editorial not in rendered
    assert all(
        "sha256" in item and "byte_count" in item
        for item in manifest["artifact_inventory"]
    )


def test_declared_smoke_log_scope_is_explicit_in_public_evidence(
    tmp_path: Path,
) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)
    paths = EvidencePaths(
        **{
            **paths.__dict__,
            "log_corpus_scope": "post_remediation_smoke_only",
        }
    )

    collect(paths)

    manifest = json.loads((paths.output_dir / "evidence_run_manifest.json").read_text())
    leakage = json.loads((paths.output_dir / "log_content_leakage.json").read_text())
    expected_scope = "post_remediation_smoke_only"
    assert manifest["log_corpus"]["operator_declared_scope"] == expected_scope
    assert leakage["log_corpus"]["operator_declared_scope"] == expected_scope
    assert (
        "post_remediation_smoke_only_no_representative_report_processing"
        in leakage["limitations"]
    )
    assert "does not attest" in manifest["log_corpus"]["repository_provenance"]


def test_strict_isolated_bundle_marks_absent_run_logs_unavailable(
    tmp_path: Path,
) -> None:
    paths, sha, _, _ = _strict_paths(tmp_path)
    paths = EvidencePaths(
        **{
            **paths.__dict__,
            "log_dir": tmp_path / "isolated-run-logs",
            "allow_unavailable_run_logs": True,
        }
    )

    collect(paths)

    leakage = json.loads((paths.output_dir / "log_content_leakage.json").read_text())
    validation = json.loads(
        (paths.output_dir / "consistency_validation.json").read_text()
    )
    assert leakage["status"] == "unavailable"
    assert "run_owned_logs_unavailable" in leakage["limitations"]
    assert validation["passed"] is True
    assert validation["checks"]["log_content_leakage"] == "unavailable"
    assert validation["repository_commit_sha"] == sha


def test_unknown_log_corpus_scope_fails_before_snapshot_work(tmp_path: Path) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)
    paths = EvidencePaths(**{**paths.__dict__, "log_corpus_scope": "unknown"})

    with pytest.raises(LogCorpusScopeError):
        collect(paths)

    assert not paths.output_dir.exists()


def test_strict_expected_commit_mismatch_fails_before_snapshot_work(
    tmp_path: Path,
) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)
    paths = EvidencePaths(**{**paths.__dict__, "expected_commit_sha": "0" * 40})

    with pytest.raises(RepositoryHeadMismatchError):
        collect(paths)

    assert not paths.output_dir.exists()
    assert not list(tmp_path.glob("cto_evidence_*"))


def test_strict_dirty_worktree_fails(tmp_path: Path) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)
    (paths.repository_root / "tracked.txt").write_text("changed\n", encoding="utf-8")

    with pytest.raises(RepositoryWorktreeDirtyError):
        collect(paths)


def test_strict_collection_ignores_only_its_staging_directory(tmp_path: Path) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)
    documentation_dir = paths.repository_root / "docs"
    documentation_dir.mkdir()
    (documentation_dir / ".keep").write_text("\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "docs/.keep"],
        cwd=paths.repository_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "add docs directory"],
        cwd=paths.repository_root,
        check=True,
        capture_output=True,
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=paths.repository_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    paths = EvidencePaths(
        **{
            **paths.__dict__,
            "output_dir": documentation_dir / "CTO_evidence",
            "expected_commit_sha": sha,
        }
    )

    collect(paths)

    validate_consistency(
        paths.output_dir,
        expected_run_id=json.loads(
            (paths.output_dir / "detailed_metrics.json").read_text(encoding="utf-8")
        )["evidence_run_id"],
        strict=True,
    )


def test_strict_collection_rejects_other_untracked_changes_at_finalization(
    tmp_path: Path,
) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)

    def create_untracked(_: dict[str, Path]) -> None:
        (paths.repository_root / "untracked.txt").write_text(
            "unexpected\n", encoding="utf-8"
        )

    with pytest.raises(RepositoryWorktreeDirtyError):
        collect(paths, _after_snapshot=create_untracked)

    assert not paths.output_dir.exists()


def test_strict_head_change_during_collection_fails_and_does_not_publish(
    tmp_path: Path,
) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)

    def advance_head(_: dict[str, Path]) -> None:
        repository = paths.repository_root
        (repository / "tracked.txt").write_text("next\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
        subprocess.run(["git", "commit", "-m", "next"], cwd=repository, check=True)

    with pytest.raises(RepositoryHeadChangedError):
        collect(paths, _after_snapshot=advance_head)

    assert not paths.output_dir.exists()


def test_strict_unavailable_git_metadata_fails(tmp_path: Path) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)
    non_repository = tmp_path / "not-a-repository"
    non_repository.mkdir()
    paths = EvidencePaths(**{**paths.__dict__, "repository_root": non_repository})

    with pytest.raises(RepositoryStateUnavailableError):
        collect(paths)


def test_live_log_changes_after_snapshot_do_not_affect_leakage_scan(
    tmp_path: Path,
) -> None:
    paths, _, source, _ = _strict_paths(tmp_path)
    live_log = paths.log_dir / "market_lense_2026-07-16.log"

    def add_leak(_: dict[str, Path]) -> None:
        live_log.write_text(source, encoding="utf-8")

    collect(paths, _after_snapshot=add_leak)

    leakage = json.loads((paths.output_dir / "log_content_leakage.json").read_text())
    assert leakage["passed"] is True


@pytest.mark.parametrize("kind", ["source", "editorial"])
def test_strict_retained_content_in_standard_log_fails_closed(
    tmp_path: Path, kind: str
) -> None:
    paths, _, source, editorial = _strict_paths(tmp_path)
    leaked = source if kind == "source" else editorial
    _seed_standard_log(tmp_path, leaked)

    with pytest.raises(LogContentLeakageError):
        collect(paths)

    assert not paths.output_dir.exists()


def test_json_escaped_and_windowed_retained_content_fail_leakage_assessment(
    tmp_path: Path,
) -> None:
    paths, _, source, _ = _strict_paths(tmp_path)
    normalized = " ".join(source.casefold().split())
    middle = (len(normalized) - 80) // 2
    partial = f"{normalized[:80]} unrelated operational marker {normalized[middle : middle + 80]}"
    _seed_standard_log(tmp_path, json.dumps({"nested": partial}, ensure_ascii=True))

    with pytest.raises(LogContentLeakageError):
        collect(paths)


def test_log_matcher_detects_full_and_windowed_canary_content() -> None:
    content = _retained_paragraph("source", 1)
    canary = Canary(
        canary_class="source",
        report_identity="report-1",
        relative_artifact_path="report-1/report_analysis/doc_map.json",
        field_family="summary",
        normalized_text=" ".join(content.casefold().split()),
    )
    matcher = _build_matcher([canary])

    assert matcher(f"operational record {canary.normalized_text}") == [
        (canary, "full", 0)
    ]

    normalized = canary.normalized_text
    middle = (len(normalized) - 80) // 2
    windowed = f"{normalized[:80]} unrelated marker {normalized[middle : middle + 80]}"
    assert matcher(windowed) == [(canary, "windowed", 2)]


def test_missing_canary_coverage_is_incomplete_and_fails_strict_collection(
    tmp_path: Path,
) -> None:
    state, _ = _seed_state(tmp_path)
    repository, sha = _init_git_repository(tmp_path)
    paths = EvidencePaths(
        state,
        tmp_path / "empty-artifacts",
        tmp_path / "evidence",
        log_dir=_seed_standard_log(tmp_path),
        require_exact_head=True,
        expected_commit_sha=sha,
        repository_root=repository,
        workspace_parent=tmp_path,
    )

    with pytest.raises(EvidenceCoverageError):
        collect(paths)

    assert not paths.output_dir.exists()


def test_corrupt_retained_canary_artifact_fails_closed_in_strict_mode(
    tmp_path: Path,
) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)
    (paths.artifact_dir / "report-00" / "report_analysis" / "doc_map.json").write_text(
        "{not-json", encoding="utf-8"
    )

    with pytest.raises(RetainedArtifactEvidenceError):
        collect(paths)

    assert not paths.output_dir.exists()


def test_freshness_requires_a_fresh_standard_log(tmp_path: Path) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)
    old = datetime.now(UTC) - timedelta(days=2)
    log_path = paths.log_dir / "market_lense_2026-07-16.log"
    timestamp = old.timestamp()
    os.utime(log_path, (timestamp, timestamp))
    paths = EvidencePaths(
        **{
            **paths.__dict__,
            "fresh_after": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        }
    )

    with pytest.raises(EvidenceCoverageError):
        collect(paths)


__all__ = [
    "test_strict_clean_exact_head_snapshots_logs_and_publishes_redacted_bundle",
    "test_declared_smoke_log_scope_is_explicit_in_public_evidence",
    "test_strict_isolated_bundle_marks_absent_run_logs_unavailable",
    "test_unknown_log_corpus_scope_fails_before_snapshot_work",
    "test_strict_expected_commit_mismatch_fails_before_snapshot_work",
    "test_strict_dirty_worktree_fails",
    "test_strict_collection_ignores_only_its_staging_directory",
    "test_strict_collection_rejects_other_untracked_changes_at_finalization",
    "test_strict_head_change_during_collection_fails_and_does_not_publish",
    "test_strict_unavailable_git_metadata_fails",
    "test_live_log_changes_after_snapshot_do_not_affect_leakage_scan",
    "test_strict_retained_content_in_standard_log_fails_closed",
    "test_json_escaped_and_windowed_retained_content_fail_leakage_assessment",
    "test_log_matcher_detects_full_and_windowed_canary_content",
    "test_missing_canary_coverage_is_incomplete_and_fails_strict_collection",
    "test_corrupt_retained_canary_artifact_fails_closed_in_strict_mode",
    "test_freshness_requires_a_fresh_standard_log",
]
