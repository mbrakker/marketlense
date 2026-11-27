import errno
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from src.contracts.report_analysis import (
    AnalysisGenerationByIdReadRequest,
    AnalysisGenerationCommitRequest,
    AnalysisGenerationReadRequest,
)
from src.services import file_service, report_analysis_store_service
from src.utils.errors import AppError
from tests._test_report_analysis_generator._shared import _runtime


def test_generation_path_preflight_accepts_fitting_path_without_writing(tmp_path):
    output = tmp_path / "output"
    report_analysis_store_service.validate_generation_path(
        AnalysisGenerationReadRequest(
            schema_version="1.0",
            output_dir=str(output),
            report_id="report",
            report_slug="report",
        ),
        _runtime(tmp_path).ctx,
    )
    assert not output.exists()


def test_generation_commit_and_read_are_coherent(tmp_path):
    ctx = _runtime(tmp_path).ctx
    request = AnalysisGenerationCommitRequest(
        schema_version="1.0",
        output_dir=str(tmp_path),
        report_id="report",
        report_slug="report",
        expected_generation="",
        packs={"first": {"value": "new"}, "second": {"value": "new"}},
    )
    committed = report_analysis_store_service.commit_generation(request, ctx)
    observed = report_analysis_store_service.read_generation(
        AnalysisGenerationReadRequest(
            schema_version="1.0",
            output_dir=str(tmp_path),
            report_id="report",
            report_slug="report",
        ),
        ctx,
    )
    assert observed.generation == committed.generation
    assert observed.packs == request.packs
    assert set(observed.pack_paths) == {"first", "second"}
    assert json.loads(
        Path(observed.pack_paths["first"]).read_text(encoding="utf-8")
    ) == {"value": "new"}
    assert Path(observed.pack_paths["first"]) != Path(observed.pack_paths["second"])


def test_generation_rejects_another_report_with_same_slug(tmp_path):
    ctx = _runtime(tmp_path).ctx
    committed = report_analysis_store_service.commit_generation(
        AnalysisGenerationCommitRequest(
            schema_version="1.0",
            output_dir=str(tmp_path),
            report_id="report-a",
            report_slug="shared-title",
            packs={"first": {"value": "report-a"}},
        ),
        ctx,
    )
    with pytest.raises(AppError):
        report_analysis_store_service.read_generation(
            AnalysisGenerationReadRequest(
                schema_version="1.0",
                output_dir=str(tmp_path),
                report_id="report-b",
                report_slug="shared-title",
            ),
            ctx,
        )
    with pytest.raises(AppError):
        report_analysis_store_service.read_generation_by_id(
            AnalysisGenerationByIdReadRequest(
                schema_version="1.0",
                output_dir=str(tmp_path),
                report_id="report-b",
                report_slug="shared-title",
                generation=committed.generation,
            ),
            ctx,
        )
    with pytest.raises(AppError):
        report_analysis_store_service.commit_generation(
            AnalysisGenerationCommitRequest(
                schema_version="1.0",
                output_dir=str(tmp_path),
                report_id="report-b",
                report_slug="shared-title",
                expected_generation=committed.generation,
                packs={"first": {"value": "report-b"}},
            ),
            ctx,
        )


def test_historical_v12_generation_remains_readable_without_migration(tmp_path):
    ctx = _runtime(tmp_path).ctx
    directory = tmp_path / "report" / "report_analysis"
    generations = directory / ".generations"
    packs = {"first": {"value": "historical"}}
    body = {"schema_version": "1.2", "packs": packs, "parent_generation": ""}
    content = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    generation = hashlib.sha256(content).hexdigest()
    pack_directory = generations / generation
    pack_directory.mkdir(parents=True)
    (generations / f"{generation}.json").write_bytes(content)
    pack_name = hashlib.sha256(b"first").hexdigest()[:16]
    (pack_directory / f"{pack_name}.json").write_text(
        '{"value":"historical"}', encoding="utf-8"
    )
    manifest_path = directory / ".generation-manifest.json"
    manifest = json.dumps({"schema_version": "1.0", "generation": generation})
    manifest_path.write_text(manifest, encoding="utf-8")
    result = report_analysis_store_service.read_generation(
        AnalysisGenerationReadRequest(
            schema_version="1.0",
            output_dir=str(tmp_path),
            report_id="report",
            report_slug="report",
        ),
        ctx,
    )
    assert result.generation == generation
    assert result.packs == packs
    assert manifest_path.read_text(encoding="utf-8") == manifest
    with pytest.raises(AppError) as exc:
        report_analysis_store_service.commit_generation(
            AnalysisGenerationCommitRequest(
                schema_version="1.0",
                output_dir=str(tmp_path),
                report_id="report-b",
                report_slug="report",
                expected_generation=generation,
                packs={"first": {"value": "replacement"}},
            ),
            ctx,
        )
    assert exc.value.code == "analysis_generation_identity_unbound"
    assert manifest_path.read_text(encoding="utf-8") == manifest


@pytest.mark.skipif(sys.platform != "win32", reason="Windows path safety budget")
def test_generation_path_preflight_fails_before_any_write(tmp_path):
    output = tmp_path / ("x" * max(1, 150 - len(str(tmp_path.resolve())) - 1))
    request = AnalysisGenerationReadRequest(
        schema_version="1.0",
        output_dir=str(output),
        report_id="report",
        report_slug="report",
    )
    with pytest.raises(AppError) as exc:
        report_analysis_store_service.validate_generation_path(
            request, _runtime(tmp_path).ctx
        )
    assert exc.value.code == "analysis_generation_path_too_long"
    assert not output.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows path safety budget")
def test_long_generation_path_fails_before_manifest_commit(tmp_path):
    # Keep the ordinary pack path short enough while the generation path is long.
    output = tmp_path / ("x" * max(1, 150 - len(str(tmp_path.resolve())) - 1))
    with pytest.raises(AppError) as exc:
        report_analysis_store_service.commit_generation(
            AnalysisGenerationCommitRequest(
                schema_version="1.0",
                output_dir=str(output),
                report_id="report",
                report_slug="report",
                packs={"first": {"value": 1}},
            ),
            _runtime(tmp_path).ctx,
        )
    assert exc.value.code == "analysis_generation_path_too_long"
    assert not (
        output / "report" / "report_analysis" / ".generation-manifest.json"
    ).exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX filesystem path behavior")
def test_posix_long_generation_uses_original_address_and_remains_readable(tmp_path):
    output = tmp_path / ("x" * max(1, 150 - len(str(tmp_path.resolve())) - 1))
    ctx = _runtime(tmp_path).ctx
    args = {
        "schema_version": "1.0",
        "output_dir": str(output),
        "report_id": "report",
        "report_slug": "report",
    }
    first = report_analysis_store_service.commit_generation(
        AnalysisGenerationCommitRequest(**args, packs={"first": {"value": 1}}), ctx
    )
    pack_path = Path(first.pack_paths["first"])
    assert file_service.atomic_write_temp_path_length(pack_path) > 240
    directory = output / "report" / "report_analysis"
    manifest = json.loads((directory / ".generation-manifest.json").read_text())
    assert manifest["generation"] == first.generation
    assert json.loads(
        (directory / ".generations" / (first.generation + ".json")).read_text()
    )["packs"]["first"] == {"value": 1}
    assert json.loads(pack_path.read_text()) == {"value": 1}
    second = report_analysis_store_service.commit_generation(
        AnalysisGenerationCommitRequest(
            **args, expected_generation=first.generation, packs={"first": {"value": 2}}
        ),
        ctx,
    )
    assert (
        report_analysis_store_service.read_generation_by_id(
            AnalysisGenerationByIdReadRequest(**args, generation=first.generation), ctx
        ).generation
        == first.generation
    )
    assert (
        report_analysis_store_service.read_generation(
            AnalysisGenerationReadRequest(**args), ctx
        ).generation
        == second.generation
    )


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX filesystem path behavior")
def test_native_path_error_is_typed_before_generation_commit(tmp_path):
    output = tmp_path / ("\N{GRINNING FACE}" * 65)
    request = AnalysisGenerationCommitRequest(
        schema_version="1.0",
        output_dir=str(output),
        report_id="report",
        report_slug="report",
        packs={"first": {"value": 1}},
    )
    with pytest.raises(AppError) as exc:
        report_analysis_store_service.commit_generation(request, _runtime(tmp_path).ctx)
    assert exc.value.code == "lock_coordination_failed"
    assert isinstance(exc.value.cause, OSError)
    assert exc.value.cause.errno == errno.ENAMETOOLONG


def test_manifest_error_after_replacement_returns_committed_generation(tmp_path):
    from src.services import file_service

    ctx = _runtime(tmp_path).ctx
    request = AnalysisGenerationCommitRequest(
        schema_version="1.0",
        output_dir=str(tmp_path),
        report_id="report",
        report_slug="report",
        packs={"first": {"value": 1}},
    )

    def write_then_fail(write_request, write_ctx):
        result = file_service.write_bytes(write_request, write_ctx)
        if Path(write_request.path).name == ".generation-manifest.json":
            raise AppError(code="injected_post_replace", message="post-replace failure")
        return result

    committed = report_analysis_store_service.commit_generation(
        request, ctx, write_bytes=write_then_fail
    )
    assert committed.packs == {"first": {"value": 1}}
    assert (
        report_analysis_store_service.read_generation(
            AnalysisGenerationReadRequest(
                schema_version="1.0",
                output_dir=str(tmp_path),
                report_id="report",
                report_slug="report",
            ),
            ctx,
        ).generation
        == committed.generation
    )


def test_read_generation_by_id_requires_committed_ancestry_and_intact_packs(tmp_path):
    ctx = _runtime(tmp_path).ctx
    first = report_analysis_store_service.commit_generation(
        AnalysisGenerationCommitRequest(
            schema_version="1.0",
            output_dir=str(tmp_path),
            report_id="report",
            report_slug="report",
            packs={"first": {"value": 1}},
        ),
        ctx,
    )
    report_analysis_store_service.commit_generation(
        AnalysisGenerationCommitRequest(
            schema_version="1.0",
            output_dir=str(tmp_path),
            report_id="report",
            report_slug="report",
            expected_generation=first.generation,
            packs={"first": {"value": 2}},
        ),
        ctx,
    )
    request = AnalysisGenerationByIdReadRequest(
        schema_version="1.0",
        output_dir=str(tmp_path),
        report_id="report",
        report_slug="report",
        generation=first.generation,
    )
    manifest = tmp_path / "report" / "report_analysis" / ".generation-manifest.json"
    observed = report_analysis_store_service.read_generation_by_id(request, ctx)
    assert observed.packs == {"first": {"value": 1}}
    manifest_bytes = manifest.read_bytes()
    manifest.write_bytes(b"invalid manifest")
    with pytest.raises(AppError) as exc:
        report_analysis_store_service.read_generation_by_id(request, ctx)
    assert exc.value.code == "analysis_generation_invalid"
    manifest.write_bytes(manifest_bytes)
    Path(observed.pack_paths["first"]).write_bytes(b"{}")
    with pytest.raises(AppError) as exc:
        report_analysis_store_service.read_generation_by_id(request, ctx)
    assert exc.value.code == "analysis_generation_invalid"


def test_read_generation_by_id_rejects_uncommitted_orphan(tmp_path):
    ctx = _runtime(tmp_path).ctx
    args = {
        "schema_version": "1.0",
        "output_dir": str(tmp_path),
        "report_id": "report",
        "report_slug": "report",
    }
    first = report_analysis_store_service.commit_generation(
        AnalysisGenerationCommitRequest(**args, packs={"first": {"value": "first"}}),
        ctx,
    )
    manifest = tmp_path / "report" / "report_analysis" / ".generation-manifest.json"
    saved = manifest.read_bytes()
    orphan = report_analysis_store_service.commit_generation(
        AnalysisGenerationCommitRequest(
            **args,
            expected_generation=first.generation,
            packs={"first": {"value": "orphan"}},
        ),
        ctx,
    )
    manifest.write_bytes(saved)
    with pytest.raises(AppError) as exc:
        report_analysis_store_service.read_generation_by_id(
            AnalysisGenerationByIdReadRequest(**args, generation=orphan.generation), ctx
        )
    assert exc.value.code == "analysis_generation_invalid"


def test_stale_writer_and_legacy_marker_are_rejected(tmp_path):
    ctx = _runtime(tmp_path).ctx
    request = AnalysisGenerationCommitRequest(
        schema_version="1.0",
        output_dir=str(tmp_path),
        report_id="report",
        report_slug="report",
        packs={"first": {"value": 1}},
    )
    report_analysis_store_service.commit_generation(request, ctx)
    with pytest.raises(AppError) as exc:
        report_analysis_store_service.commit_generation(request, ctx)
    assert exc.value.code == "analysis_generation_conflict"
    marker = tmp_path / "report" / "report_analysis" / ".promotion-pending"
    marker.write_bytes(b"unknown owner")
    with pytest.raises(AppError) as exc:
        report_analysis_store_service.commit_generation(request, ctx)
    assert exc.value.code == "regeneration_promotion_recovery_failed"
    assert marker.read_bytes() == b"unknown owner"


def test_reader_rejects_corrupted_generation(tmp_path):
    ctx = _runtime(tmp_path).ctx
    request = AnalysisGenerationCommitRequest(
        schema_version="1.0",
        output_dir=str(tmp_path),
        report_id="report",
        report_slug="report",
        packs={"first": {"value": 1}},
    )
    committed = report_analysis_store_service.commit_generation(request, ctx)
    path = (
        tmp_path
        / "report"
        / "report_analysis"
        / ".generations"
        / (committed.generation + ".json")
    )
    path.write_bytes(b"{}")
    with pytest.raises(AppError) as exc:
        report_analysis_store_service.read_generation(
            AnalysisGenerationReadRequest(
                schema_version="1.0",
                output_dir=str(tmp_path),
                report_id="report",
                report_slug="report",
            ),
            ctx,
        )
    assert exc.value.code == "analysis_generation_invalid"


def test_missing_manifest_is_distinct_from_missing_committed_data(tmp_path):
    ctx = _runtime(tmp_path).ctx
    read = AnalysisGenerationReadRequest(
        schema_version="1.0",
        output_dir=str(tmp_path),
        report_id="report",
        report_slug="report",
    )
    with pytest.raises(AppError) as exc:
        report_analysis_store_service.read_generation(read, ctx)
    assert exc.value.code == "analysis_generation_missing"
    result = report_analysis_store_service.commit_generation(
        AnalysisGenerationCommitRequest(
            schema_version="1.0",
            output_dir=str(tmp_path),
            report_id="report",
            report_slug="report",
            packs={"first": {"value": 1}},
        ),
        ctx,
    )
    Path(result.pack_paths["first"]).unlink()
    with pytest.raises(AppError) as exc:
        report_analysis_store_service.read_generation(read, ctx)
    assert exc.value.code == "analysis_generation_invalid"


def test_killed_lock_holder_does_not_prevent_commit(tmp_path):
    worker = subprocess.Popen(
        [sys.executable, "-m", "tests.test_analysis_generation_store", str(tmp_path)]
    )
    try:
        deadline = time.monotonic() + 30
        while (
            not (tmp_path / "locked").exists()
            and worker.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)
        assert (tmp_path / "locked").exists()
    finally:
        worker.kill()
        worker.wait(timeout=10)
    ctx = _runtime(tmp_path).ctx
    request = AnalysisGenerationCommitRequest(
        schema_version="1.0",
        output_dir=str(tmp_path),
        report_id="report",
        report_slug="report",
        packs={"first": {"value": 1}},
    )
    result = report_analysis_store_service.commit_generation(request, ctx)
    assert result.packs == request.packs


@pytest.mark.parametrize(
    "long_path",
    [
        False,
        pytest.param(
            True,
            marks=pytest.mark.skipif(
                sys.platform == "win32", reason="POSIX filesystem path behavior"
            ),
        ),
    ],
)
def test_concurrent_processes_cannot_both_commit_same_parent(tmp_path, long_path):
    output = (
        tmp_path / ("x" * max(1, 150 - len(str(tmp_path.resolve())) - 1))
        if long_path
        else tmp_path
    )
    workers = [
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "tests.test_analysis_generation_store",
                str(output),
                str(i),
            ]
        )
        for i in range(2)
    ]
    try:
        results = sorted(worker.wait(timeout=30) for worker in workers)
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.kill()
                worker.wait(timeout=10)
    assert results == [0, 2]
    ctx = _runtime(tmp_path).ctx
    observed = report_analysis_store_service.read_generation(
        AnalysisGenerationReadRequest(
            schema_version="1.0",
            output_dir=str(output),
            report_id="report",
            report_slug="report",
        ),
        ctx,
    )
    assert observed.packs["first"]["value"] in ("0", "1")
    assert observed.packs["first"] == observed.packs["second"]


def test_killed_writer_during_staging_leaves_previous_generation_readable(tmp_path):
    ctx = _runtime(tmp_path).ctx
    read = AnalysisGenerationReadRequest(
        schema_version="1.0",
        output_dir=str(tmp_path),
        report_id="report",
        report_slug="report",
    )
    first = report_analysis_store_service.commit_generation(
        AnalysisGenerationCommitRequest(
            schema_version="1.0",
            output_dir=str(tmp_path),
            report_id="report",
            report_slug="report",
            packs={"first": {"value": "old"}},
        ),
        ctx,
    )
    worker = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tests.test_analysis_generation_store",
            str(tmp_path),
            "stage",
            first.generation,
        ]
    )
    generation_dir = tmp_path / "report" / "report_analysis" / ".generations"
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and worker.poll() is None:
            staged = [
                p
                for p in generation_dir.iterdir()
                if p.is_dir() and p.name != first.generation
            ]
            if staged and any(staged[0].iterdir()):
                break
            time.sleep(0.001)
        else:
            pytest.fail("writer did not reach pack staging")
    finally:
        if worker.poll() is None:
            worker.kill()
        worker.wait(timeout=10)
    observed = report_analysis_store_service.read_generation(read, ctx)
    assert observed.generation == first.generation
    assert observed.packs == {"first": {"value": "old"}}
    next_generation = report_analysis_store_service.commit_generation(
        AnalysisGenerationCommitRequest(
            schema_version="1.0",
            output_dir=str(tmp_path),
            report_id="report",
            report_slug="report",
            expected_generation=first.generation,
            packs={"first": {"value": "next"}},
        ),
        ctx,
    )
    assert next_generation.packs["first"]["value"] == "next"


def test_killed_writer_after_commit_keeps_new_generation(tmp_path):
    worker = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tests.test_analysis_generation_store",
            str(tmp_path),
            "committed",
        ]
    )
    try:
        deadline = time.monotonic() + 30
        while (
            not (tmp_path / "committed").exists()
            and worker.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert (tmp_path / "committed").exists()
    finally:
        if worker.poll() is None:
            worker.kill()
        worker.wait(timeout=10)
    observed = report_analysis_store_service.read_generation(
        AnalysisGenerationReadRequest(
            schema_version="1.0",
            output_dir=str(tmp_path),
            report_id="report",
            report_slug="report",
        ),
        _runtime(tmp_path).ctx,
    )
    assert observed.packs == {"first": {"value": "committed"}}
    assert json.loads(
        Path(observed.pack_paths["first"]).read_text(encoding="utf-8")
    ) == {"value": "committed"}


if __name__ == "__main__":
    from pathlib import Path

    root = Path(sys.argv[1])
    if len(sys.argv) > 2 and sys.argv[2] == "committed":
        report_analysis_store_service.commit_generation(
            AnalysisGenerationCommitRequest(
                schema_version="1.0",
                output_dir=str(root),
                report_id="report",
                report_slug="report",
                packs={"first": {"value": "committed"}},
            ),
            _runtime(root).ctx,
        )
        (root / "committed").write_text("committed", encoding="utf-8")
        while True:
            time.sleep(1)
    if len(sys.argv) > 3 and sys.argv[2] == "stage":
        report_analysis_store_service.commit_generation(
            AnalysisGenerationCommitRequest(
                schema_version="1.0",
                output_dir=str(root),
                report_id="report",
                report_slug="report",
                expected_generation=sys.argv[3],
                packs={f"pack{i}": {"value": i} for i in range(500)},
            ),
            _runtime(root).ctx,
        )
        sys.exit(0)
    if len(sys.argv) > 2:
        value = sys.argv[2]
        request = AnalysisGenerationCommitRequest(
            schema_version="1.0",
            output_dir=str(root),
            report_id="report",
            report_slug="report",
            packs={"first": {"value": value}, "second": {"value": value}},
        )
        try:
            report_analysis_store_service.commit_generation(request, _runtime(root).ctx)
        except AppError as exc:
            if exc.code != "analysis_generation_conflict":
                raise
            sys.exit(2)
        sys.exit(0)
    directory = root / "report" / "report_analysis"
    with report_analysis_store_service._generation_writer_lock(directory):
        (root / "locked").write_text("locked", encoding="utf-8")
        while True:
            time.sleep(1)
