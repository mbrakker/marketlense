from __future__ import annotations

import hashlib
import multiprocessing
import random
import zipfile
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from src.contracts.mailbox_acquisition import (
    MailboxAcquisitionSettings,
    MailboxAttachment,
    MailboxAttachmentMaterializeRequest,
)
from src.contracts.run_context import RunContext
from src.services import file_service
from src.services import mailbox_acquisition_service as mailbox_service
from src.services.mailbox_acquisition_service import materialize_mailbox_attachments
from src.utils.errors import AppError
from tests.conftest import ExternalBoundaryMocksOnly

_MIB = 1024 * 1024
_MAX_ZIP_ATTACHMENT_BYTES = 25 * _MIB
_MAX_ZIP_MEMBERS = 500
_MAX_ZIP_MEMBER_BYTES = 16 * _MIB
_MAX_ZIP_TOTAL_BYTES = 32 * _MIB
_MAX_ZIP_PDF_COUNT = 100
_MAX_ZIP_COMPRESSION_RATIO = 100.0


def _settings(tmp_path: Path) -> MailboxAcquisitionSettings:
    return MailboxAcquisitionSettings(
        schema_version="1.0",
        provider="gmail",
        output_dir=str(tmp_path / "mailbox"),
        search_window_minutes=120,
        max_results=10,
        poll_timeout_seconds=120.0,
        poll_interval_seconds=30.0,
        gmail_oauth_client_path="client.json",
        gmail_oauth_token_path="token.json",
        gmail_user_id="me",
        imap_host="",
        imap_port=993,
        imap_user="",
        imap_password="",
        imap_mailbox="INBOX",
    )


def _zip_bytes(
    entries: list[tuple[str, bytes]], *, compression: int = zipfile.ZIP_STORED
) -> bytes:
    stream = BytesIO()
    with ZipFile(stream, "w", compression=compression) as archive:
        for file_name, payload in entries:
            archive.writestr(file_name, payload)
    return stream.getvalue()


def _request(
    tmp_path: Path,
    attachments: list[MailboxAttachment],
    *,
    message_id: str = "zip-message",
) -> MailboxAttachmentMaterializeRequest:
    return MailboxAttachmentMaterializeRequest(
        schema_version="1.0",
        settings=_settings(tmp_path),
        provider_message_id=message_id,
        attachments=attachments,
    )


def _context(message_id: str) -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="zip-test",
        task_id=message_id,
        span_id="zip-span",
    )


def _attachment(payload: bytes, *, name: str = "delivery.zip") -> MailboxAttachment:
    return MailboxAttachment(
        schema_version="1.0",
        file_name=name,
        content_type="application/zip",
        payload=payload,
    )


def _pdf(file_name: str, payload: bytes) -> MailboxAttachment:
    return MailboxAttachment(
        schema_version="1.0",
        file_name=file_name,
        content_type="application/pdf",
        payload=payload,
    )


def _moderately_compressible_pdf(seed_value: int) -> bytes:
    rng = random.Random(seed_value)
    repeated_pattern = rng.randbytes(8 * 1024)
    target_bytes = _MAX_ZIP_MEMBER_BYTES - len(b"%PDF-1.7")
    parts = [b"%PDF-1.7"]
    produced_bytes = 0
    while produced_bytes < target_bytes:
        noise = rng.randbytes(23 * 1024)
        parts.extend((repeated_pattern, noise))
        produced_bytes += len(repeated_pattern) + len(noise)
    return b"".join(parts)[:_MAX_ZIP_MEMBER_BYTES]


def _materialize(
    tmp_path: Path,
    payload: bytes,
    *,
    message_id: str,
):
    return materialize_mailbox_attachments(
        _request(tmp_path, [_attachment(payload)], message_id=message_id),
        _context(message_id),
    )


def _zip_materialization_process(
    root_path,
    archive_payload,
    role,
    first_committed,
    resume_first,
    result_queue,
):
    request = _request(
        Path(root_path),
        [_attachment(archive_payload)],
        message_id="cross-process-zip-reuse",
    )
    ctx = RunContext(
        schema_version="1.0",
        run_id="zip-cross-process-test",
        task_id="cross-process-zip-reuse",
        span_id="zip-cross-process-span",
    )
    commit_operation = "rename" if mailbox_service.os.name == "nt" else "link"
    actual_commit = getattr(mailbox_service.os, commit_operation)
    boundary_mocks = ExternalBoundaryMocksOnly()

    if role == "pause_then_fail":

        def pause_then_fail_commit(source, destination):
            if Path(destination).name == "second.pdf":
                if not resume_first.wait(30):
                    raise OSError(
                        "timed out waiting to inject the second commit failure"
                    )
                raise OSError("injected second ZIP commit failure")
            result = actual_commit(source, destination)
            if Path(destination).name == "first.pdf":
                first_committed.set()
                if not resume_first.wait(30):
                    raise OSError("timed out waiting to resume the first worker")
            return result

        boundary_mocks.setattr(
            mailbox_service.os, commit_operation, pause_then_fail_commit
        )

    try:
        response = materialize_mailbox_attachments(request, ctx)
        result_queue.put(
            (
                "success",
                role,
                [
                    (
                        artifact.file_name,
                        artifact.path,
                        artifact.source_container_file_name,
                        artifact.source_member_file_name,
                    )
                    for artifact in response.artifacts
                ],
                [failure.error_code for failure in response.failures],
            )
        )
    except AppError as exc:
        result_queue.put(("error", role, exc.code, exc.retryable))
    except Exception as exc:
        result_queue.put(("unexpected", role, type(exc).__name__, str(exc)))
    finally:
        boundary_mocks.close()


def _mutate_encryption_flag(payload: bytes) -> bytes:
    encrypted = bytearray(payload)
    local_header = encrypted.find(b"PK\x03\x04")
    central_header = encrypted.find(b"PK\x01\x02")
    assert local_header >= 0 and central_header >= 0
    local_flags = int.from_bytes(
        encrypted[local_header + 6 : local_header + 8], "little"
    )
    central_flags = int.from_bytes(
        encrypted[central_header + 8 : central_header + 10], "little"
    )
    encrypted[local_header + 6 : local_header + 8] = (local_flags | 1).to_bytes(
        2, "little"
    )
    encrypted[central_header + 8 : central_header + 10] = (central_flags | 1).to_bytes(
        2, "little"
    )
    return bytes(encrypted)


def _windows_path_units(path: Path) -> int:
    return len(str(path).encode("utf-16-le")) // 2


def _deep_output_dir(tmp_path: Path) -> Path:
    output_dir = tmp_path
    while _windows_path_units(output_dir) < 150:
        output_dir /= f"mailbox-root-{output_dir.name[-1]}-segment"
    return output_dir / "mailbox"


def _corrupt_member_data(payload: bytes, member_name: str) -> bytes:
    corrupted = bytearray(payload)
    with ZipFile(BytesIO(payload)) as archive:
        member = archive.getinfo(member_name)
        header_offset = member.header_offset
    name_length = int.from_bytes(
        corrupted[header_offset + 26 : header_offset + 28], "little"
    )
    extra_length = int.from_bytes(
        corrupted[header_offset + 28 : header_offset + 30], "little"
    )
    data_offset = header_offset + 30 + name_length + extra_length
    corrupted[data_offset] ^= 0xFF
    return bytes(corrupted)


def test_zip_limits_accept_exact_values_and_reject_limit_plus_one(tmp_path):
    raw_names = ["padding-a.bin", "padding-b.bin", "padding-c.bin"]
    raw_overhead = len(_zip_bytes([(name, b"") for name in raw_names]))
    raw_content_size = _MAX_ZIP_ATTACHMENT_BYTES - raw_overhead
    raw_sizes = [raw_content_size // 3, raw_content_size // 3, 0]
    raw_sizes[2] = raw_content_size - raw_sizes[0] - raw_sizes[1]
    raw_exact = _zip_bytes(
        [(name, bytes(size)) for name, size in zip(raw_names, raw_sizes, strict=True)]
    )
    assert len(raw_exact) == _MAX_ZIP_ATTACHMENT_BYTES
    raw_result = _materialize(tmp_path, raw_exact, message_id="raw-exact")
    assert raw_result.failures == []
    raw_plus_one = _materialize(tmp_path, raw_exact + b"x", message_id="raw-plus-one")
    assert [failure.error_code for failure in raw_plus_one.failures] == [
        "mailbox_zip_attachment_too_large"
    ]
    assert list((tmp_path / "mailbox" / "raw-plus-one").glob("*.pdf")) == []

    member_exact = b"%PDF-1.7" + bytes(_MAX_ZIP_MEMBER_BYTES - len(b"%PDF-1.7"))
    member_result = _materialize(
        tmp_path,
        _zip_bytes([("report.pdf", member_exact)]),
        message_id="member-exact",
    )
    assert member_result.failures == []
    assert member_result.artifacts[0].size_bytes == _MAX_ZIP_MEMBER_BYTES
    member_plus_one = _materialize(
        tmp_path,
        _zip_bytes([("report.pdf", member_exact + b"x")]),
        message_id="member-plus-one",
    )
    assert [failure.error_code for failure in member_plus_one.failures] == [
        "mailbox_zip_member_size_exceeded"
    ]
    assert list((tmp_path / "mailbox" / "member-plus-one").glob("*.pdf")) == []

    full_a = _moderately_compressible_pdf(31)
    full_b = _moderately_compressible_pdf(47)
    total_exact = _zip_bytes(
        [("a.pdf", full_a), ("b.pdf", full_b)], compression=zipfile.ZIP_DEFLATED
    )
    total_result = _materialize(tmp_path, total_exact, message_id="total-exact")
    assert total_result.failures == []
    assert len(total_result.artifacts) == 2
    total_plus_one = _materialize(
        tmp_path,
        _zip_bytes(
            [("a.pdf", full_a), ("b.pdf", full_b), ("c.pdf", b"x")],
            compression=zipfile.ZIP_DEFLATED,
        ),
        message_id="total-plus-one",
    )
    assert [failure.error_code for failure in total_plus_one.failures] == [
        "mailbox_zip_total_size_exceeded"
    ]
    assert list((tmp_path / "mailbox" / "total-plus-one").glob("*.pdf")) == []

    member_names = [
        (f"member-{index:03}.txt", b"") for index in range(_MAX_ZIP_MEMBERS)
    ]
    member_count_exact = _materialize(
        tmp_path, _zip_bytes(member_names), message_id="count-exact"
    )
    assert member_count_exact.failures == []
    member_count_plus_one = _materialize(
        tmp_path,
        _zip_bytes(member_names + [("extra.txt", b"")]),
        message_id="count-plus-one",
    )
    assert [failure.error_code for failure in member_count_plus_one.failures] == [
        "mailbox_zip_member_count_exceeded"
    ]

    pdf_entries = [
        (f"report-{index:03}.pdf", b"%PDF") for index in range(_MAX_ZIP_PDF_COUNT)
    ]
    pdf_count_exact = _materialize(
        tmp_path, _zip_bytes(pdf_entries), message_id="pdf-count-exact"
    )
    assert pdf_count_exact.failures == []
    assert len(pdf_count_exact.artifacts) == _MAX_ZIP_PDF_COUNT
    pdf_count_plus_one = _materialize(
        tmp_path,
        _zip_bytes(pdf_entries + [("extra.pdf", b"%PDF")]),
        message_id="pdf-count-plus-one",
    )
    assert [failure.error_code for failure in pdf_count_plus_one.failures] == [
        "mailbox_zip_pdf_count_exceeded"
    ]
    assert list((tmp_path / "mailbox" / "pdf-count-plus-one").glob("*.pdf")) == []

    ratio_exact_size = 1600
    for _ in range(32):
        ratio_exact_payload = _zip_bytes(
            [("ratio.pdf", b"A" * ratio_exact_size)],
            compression=zipfile.ZIP_DEFLATED,
        )
        with ZipFile(BytesIO(ratio_exact_payload)) as archive:
            member = archive.infolist()[0]
            next_ratio_exact_size = int(
                member.compress_size * _MAX_ZIP_COMPRESSION_RATIO
            )
            if member.file_size == next_ratio_exact_size:
                break
        ratio_exact_size = next_ratio_exact_size
    else:
        pytest.fail("could not create a ZIP member at the exact compression limit")
    with ZipFile(BytesIO(ratio_exact_payload)) as archive:
        member = archive.infolist()[0]
        assert member.file_size / member.compress_size == _MAX_ZIP_COMPRESSION_RATIO
    ratio_exact = _materialize(tmp_path, ratio_exact_payload, message_id="ratio-exact")
    assert ratio_exact.failures == []
    ratio_over_limit_size = ratio_exact_size + 1
    for _ in range(32):
        ratio_over_limit_payload = _zip_bytes(
            [("ratio.pdf", b"A" * ratio_over_limit_size)],
            compression=zipfile.ZIP_DEFLATED,
        )
        with ZipFile(BytesIO(ratio_over_limit_payload)) as archive:
            member = archive.infolist()[0]
            if member.file_size / member.compress_size > _MAX_ZIP_COMPRESSION_RATIO:
                break
        ratio_over_limit_size += 1
    else:
        pytest.fail("could not create a ZIP member above the compression limit")
    ratio_plus_one = _materialize(
        tmp_path,
        ratio_over_limit_payload,
        message_id="ratio-plus-one",
    )
    assert [failure.error_code for failure in ratio_plus_one.failures] == [
        "mailbox_zip_compression_ratio_exceeded"
    ]

    duplicate_names = _materialize(
        tmp_path,
        _zip_bytes(
            [
                ("first/report.pdf", b"%PDF first"),
                ("second/report.pdf", b"%PDF second"),
            ]
        ),
        message_id="duplicate-names",
    )
    assert [failure.error_code for failure in duplicate_names.failures] == [
        "mailbox_zip_duplicate_pdf_name"
    ]
    assert duplicate_names.artifacts == []
    assert list((tmp_path / "mailbox" / "duplicate-names").glob("*.pdf")) == []


def test_malformed_encrypted_and_unsupported_archives_are_candidate_failures(
    tmp_path,
):
    candidates = [
        ("malformed", b"not a ZIP file", "mailbox_zip_invalid"),
        (
            "encrypted",
            _mutate_encryption_flag(_zip_bytes([("secret.pdf", b"%PDF")])),
            "mailbox_zip_encrypted_entry",
        ),
        (
            "unsupported",
            _zip_bytes([("unsupported.pdf", b"%PDF")], compression=zipfile.ZIP_BZIP2),
            "mailbox_zip_unsupported_compression",
        ),
    ]
    for message_id, payload, expected_code in candidates:
        response = _materialize(tmp_path, payload, message_id=message_id)
        assert response.artifacts == []
        assert [failure.error_code for failure in response.failures] == [expected_code]
        assert list((tmp_path / "mailbox" / message_id).glob("*.pdf")) == []


def test_rejected_archive_leaves_no_outputs_and_preserves_valid_sibling_attachment(
    tmp_path,
):
    archive_payload = _zip_bytes(
        [
            ("nested/valid.pdf", b"%PDF-1.7 valid"),
            ("nested/corrupt.pdf", b"%PDF-1.7 corrupt"),
        ]
    )
    archive_payload = _corrupt_member_data(archive_payload, "nested/corrupt.pdf")
    response = materialize_mailbox_attachments(
        _request(
            tmp_path,
            [
                _attachment(archive_payload),
                _pdf("standalone.pdf", b"%PDF-1.7 standalone"),
            ],
            message_id="mixed-message",
        ),
        _context("mixed-message"),
    )

    assert [failure.error_code for failure in response.failures] == [
        "mailbox_zip_member_read_failed"
    ]
    assert [artifact.file_name for artifact in response.artifacts] == ["standalone.pdf"]
    assert Path(response.artifacts[0].path).read_bytes() == b"%PDF-1.7 standalone"
    assert sorted(
        path.name for path in (tmp_path / "mailbox" / "mixed-message").glob("*.pdf")
    ) == ["standalone.pdf"]


def test_zip_write_failure_retains_committed_files_and_cleans_staging(
    tmp_path, external_boundary_mocks_only
):
    output_dir = tmp_path / "mailbox" / "write-failure"
    output_dir.mkdir(parents=True)
    existing_payload = b"%PDF-1.7 already present"
    (output_dir / "existing.pdf").write_bytes(existing_payload)
    first_payload = b"%PDF-1.7 first"
    second_payload = b"%PDF-1.7 second"
    archive_payload = _zip_bytes(
        [
            ("first.pdf", first_payload),
            ("second.pdf", second_payload),
            ("existing.pdf", existing_payload),
        ]
    )
    request = _request(
        tmp_path, [_attachment(archive_payload)], message_id="write-failure"
    )
    commit_operation = "rename" if mailbox_service.os.name == "nt" else "link"
    actual_commit = getattr(mailbox_service.os, commit_operation)
    commit_calls = 0

    def fail_second_commit(source, destination):
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 2:
            raise OSError("injected second ZIP commit failure")
        actual_commit(source, destination)

    external_boundary_mocks_only.setattr(
        mailbox_service.os, commit_operation, fail_second_commit
    )

    with pytest.raises(AppError, match="Mailbox ZIP PDF artifacts") as error:
        materialize_mailbox_attachments(request, _context("write-failure"))

    assert error.value.code == "mailbox_zip_write_failed"
    assert error.value.retryable is True
    assert (output_dir / "first.pdf").read_bytes() == first_payload
    assert not (output_dir / "second.pdf").exists()
    assert (output_dir / "existing.pdf").read_bytes() == existing_payload
    assert list(output_dir.glob(".*.tmp")) == []
    external_boundary_mocks_only.close()

    replay = materialize_mailbox_attachments(request, _context("write-failure"))

    assert replay.failures == []
    assert [Path(artifact.path).name for artifact in replay.artifacts] == [
        "first.pdf",
        "second.pdf",
        "existing.pdf",
    ]
    assert [Path(artifact.path).read_bytes() for artifact in replay.artifacts] == [
        first_payload,
        second_payload,
        existing_payload,
    ]
    assert list(output_dir.glob(".*.tmp")) == []


def test_zip_cross_process_reuse_survives_other_worker_failure(tmp_path):
    archive_payload = _zip_bytes(
        [
            ("first.pdf", b"%PDF-1.7 first process member"),
            ("second.pdf", b"%PDF-1.7 second process member"),
        ]
    )
    process_context = multiprocessing.get_context("spawn")
    first_committed = process_context.Event()
    resume_first = process_context.Event()
    result_queue = process_context.Queue()
    first_worker = process_context.Process(
        target=_zip_materialization_process,
        args=(
            str(tmp_path),
            archive_payload,
            "pause_then_fail",
            first_committed,
            resume_first,
            result_queue,
        ),
    )
    second_worker = None
    try:
        first_worker.start()
        assert first_committed.wait(30), "first worker did not commit first.pdf"
        second_worker = process_context.Process(
            target=_zip_materialization_process,
            args=(
                str(tmp_path),
                archive_payload,
                "reuse_and_succeed",
                first_committed,
                resume_first,
                result_queue,
            ),
        )
        second_worker.start()
        second_result = result_queue.get(timeout=30)
        second_worker.join(timeout=30)
        assert second_worker.exitcode == 0
        assert second_result[0:2] == ("success", "reuse_and_succeed")
        assert second_result[3] == []
        assert [Path(item[1]).name for item in second_result[2]] == [
            "first.pdf",
            "second.pdf",
        ]
        expected_payloads = [
            b"%PDF-1.7 first process member",
            b"%PDF-1.7 second process member",
        ]
        returned_paths = [Path(item[1]) for item in second_result[2]]
        assert [path.read_bytes() for path in returned_paths] == expected_payloads

        resume_first.set()
        first_result = result_queue.get(timeout=30)
        first_worker.join(timeout=30)
        assert first_worker.exitcode == 0
        assert first_result == (
            "error",
            "pause_then_fail",
            "mailbox_zip_write_failed",
            True,
        )
        assert [path.read_bytes() for path in returned_paths] == expected_payloads
        output_dir = returned_paths[0].parent
        assert list(output_dir.glob(".*.tmp")) == []
    finally:
        resume_first.set()
        for process in (first_worker, second_worker):
            if process is not None and process.is_alive():
                process.terminate()
                process.join(timeout=5)
        result_queue.close()
        result_queue.join_thread()


def test_direct_pdf_long_unicode_paths_are_bounded_distinct_and_reusable(tmp_path):
    output_dir = _deep_output_dir(tmp_path)
    settings = replace(_settings(tmp_path), output_dir=str(output_dir))
    message_id = "long-message-" + "消息身份" * 100
    first_name = "季度市场研究" * 45 + "-甲.pdf"
    second_name = "季度市场研究" * 45 + "-乙.pdf"
    attachments = [
        _pdf(first_name, b"%PDF-1.7 first long attachment"),
        _pdf(second_name, b"%PDF-1.7 second long attachment"),
    ]

    request = _request(tmp_path, attachments, message_id=message_id)
    request = replace(request, settings=settings)
    ctx = _context("long-direct")
    first = materialize_mailbox_attachments(request, ctx)
    repeated = materialize_mailbox_attachments(request, ctx)
    near_message_id = materialize_mailbox_attachments(
        replace(request, provider_message_id=message_id + "-distinct"), ctx
    )

    assert first.failures == []
    assert [artifact.path for artifact in first.artifacts] == [
        artifact.path for artifact in repeated.artifacts
    ]
    assert len({artifact.path.casefold() for artifact in first.artifacts}) == 2
    assert {artifact.path.casefold() for artifact in first.artifacts}.isdisjoint(
        artifact.path.casefold() for artifact in near_message_id.artifacts
    )
    for artifact, expected in zip(
        first.artifacts,
        [
            b"%PDF-1.7 first long attachment",
            b"%PDF-1.7 second long attachment",
        ],
        strict=True,
    ):
        path = Path(artifact.path)
        assert path.read_bytes() == expected
        assert path.resolve().is_relative_to(output_dir.resolve())
        assert _windows_path_units(path) <= 240
        assert _windows_path_units(path.parent / ("." + "0" * 32 + ".tmp")) <= 240
        assert len(path.name) <= 96
        assert len(path.parent.name) <= 64


def test_direct_pdf_sanitized_name_collisions_keep_each_payload_and_stable_path(
    tmp_path,
):
    attachments = [
        _pdf("A?B.pdf", b"%PDF-1.7 question mark"),
        _pdf("A*B.pdf", b"%PDF-1.7 asterisk"),
    ]
    request = _request(tmp_path, attachments, message_id="sanitized-collision")
    output_dir = _deep_output_dir(tmp_path)
    request = replace(
        request,
        settings=replace(request.settings, output_dir=str(output_dir)),
    )
    ctx = _context("sanitized-collision")

    first = materialize_mailbox_attachments(request, ctx)
    repeated = materialize_mailbox_attachments(request, ctx)

    assert first.failures == []
    assert [artifact.path for artifact in first.artifacts] == [
        artifact.path for artifact in repeated.artifacts
    ]
    assert len({artifact.path.casefold() for artifact in first.artifacts}) == 2
    assert [Path(artifact.path).read_bytes() for artifact in first.artifacts] == [
        attachment.payload for attachment in attachments
    ]
    assert all(
        _windows_path_units(Path(artifact.path)) <= 240 for artifact in first.artifacts
    )
    assert all(
        _windows_path_units(Path(artifact.path).parent / ("." + "0" * 32 + ".tmp"))
        <= 240
        for artifact in first.artifacts
    )
    assert all(len(Path(artifact.path).name) <= 96 for artifact in first.artifacts)
    assert all(
        len(Path(artifact.path).parent.name) <= 64 for artifact in first.artifacts
    )


def test_direct_same_name_different_payloads_get_distinct_stable_paths(tmp_path):
    attachments = [
        _pdf("reused.pdf", b"%PDF-1.7 first version"),
        _pdf("reused.pdf", b"%PDF-1.7 second version"),
    ]
    request = _request(tmp_path, attachments, message_id="same-name-collision")
    output_dir = _deep_output_dir(tmp_path)
    request = replace(
        request,
        settings=replace(request.settings, output_dir=str(output_dir)),
    )
    ctx = _context("same-name-collision")

    first = materialize_mailbox_attachments(request, ctx)
    repeated = materialize_mailbox_attachments(request, ctx)
    subsets = [
        materialize_mailbox_attachments(replace(request, attachments=[attachment]), ctx)
        for attachment in attachments
    ]

    assert first.failures == []
    assert [artifact.path for artifact in first.artifacts] == [
        artifact.path for artifact in repeated.artifacts
    ]
    assert [response.artifacts[0].path for response in subsets] == [
        artifact.path for artifact in first.artifacts
    ]
    assert len({artifact.path.casefold() for artifact in first.artifacts}) == 2
    assert [Path(artifact.path).read_bytes() for artifact in first.artifacts] == [
        attachment.payload for attachment in attachments
    ]
    assert all(
        _windows_path_units(Path(artifact.path)) <= 240 for artifact in first.artifacts
    )


def test_zip_member_collision_with_direct_pdf_does_not_overwrite(tmp_path):
    direct_payload = b"%PDF-1.7 direct attachment"
    zip_payload = b"%PDF-1.7 archived attachment"
    attachments = [
        _attachment(_zip_bytes([("reports/report.pdf", zip_payload)])),
        _pdf("report.pdf", direct_payload),
    ]
    response = materialize_mailbox_attachments(
        _request(tmp_path, attachments, message_id="zip-direct-collision"),
        _context("zip-direct-collision"),
    )

    assert [
        (failure.attachment_index, failure.error_code) for failure in response.failures
    ] == [(0, "mailbox_zip_duplicate_pdf_name")]
    assert len(response.artifacts) == 1
    assert Path(response.artifacts[0].path).read_bytes() == direct_payload
    assert response.artifacts[0].source_container_file_name == ""
    assert list(Path(response.artifacts[0].path).parent.glob(".*.tmp")) == []
    assert list(Path(response.artifacts[0].path).parent.glob("*.pdf")) == [
        Path(response.artifacts[0].path)
    ]


def test_zip_long_unicode_and_near_identical_names_stage_and_read_back(tmp_path):
    output_dir = _deep_output_dir(tmp_path)
    settings = replace(_settings(tmp_path), output_dir=str(output_dir))
    message_id = "zip-message-" + "配送識別子" * 90
    common_stem = "global-market-insights-" * 18
    entries = [
        (f"reports/{common_stem}-north.pdf", b"%PDF-1.7 north"),
        (f"reports/{common_stem}-south.pdf", b"%PDF-1.7 south"),
        ("reports/国际市场报告.pdf", b"%PDF-1.7 unicode"),
    ]
    request = _request(
        tmp_path,
        [_attachment(_zip_bytes(entries), name="季度投递.zip")],
        message_id=message_id,
    )
    request = replace(request, settings=settings)
    ctx = _context("long-zip")

    first = materialize_mailbox_attachments(request, ctx)
    repeated = materialize_mailbox_attachments(request, ctx)

    assert first.failures == []
    assert [artifact.path for artifact in first.artifacts] == [
        artifact.path for artifact in repeated.artifacts
    ]
    assert len({artifact.path.casefold() for artifact in first.artifacts}) == len(
        entries
    )
    assert [Path(artifact.path).read_bytes() for artifact in first.artifacts] == [
        payload for _, payload in entries
    ]
    assert all(
        artifact.source_container_file_name == "季度投递.zip"
        for artifact in first.artifacts
    )
    assert [artifact.source_member_file_name for artifact in first.artifacts] == [
        name for name, _ in entries
    ]
    assert all(
        _windows_path_units(Path(artifact.path)) <= 240 for artifact in first.artifacts
    )
    assert all(
        _windows_path_units(Path(artifact.path).parent / ("." + "0" * 32 + ".tmp"))
        <= 240
        for artifact in first.artifacts
    )
    assert list(Path(first.artifacts[0].path).parent.glob(".*.tmp")) == []


def test_zip_distinct_unicode_names_use_output_path_identity(tmp_path):
    entries = [
        ("报告甲.pdf", b"%PDF-1.7 unicode A"),
        ("报告乙.pdf", b"%PDF-1.7 unicode B"),
    ]
    request = _request(
        tmp_path,
        [_attachment(_zip_bytes(entries), name="unicode-reports.zip")],
        message_id="unicode-zip-collisions",
    )
    output_dir = _deep_output_dir(tmp_path)
    request = replace(
        request,
        settings=replace(request.settings, output_dir=str(output_dir)),
    )
    ctx = _context("unicode-zip-collisions")

    first = materialize_mailbox_attachments(request, ctx)
    repeated = materialize_mailbox_attachments(request, ctx)

    assert first.failures == []
    assert [artifact.path for artifact in first.artifacts] == [
        artifact.path for artifact in repeated.artifacts
    ]
    assert len({artifact.path.casefold() for artifact in first.artifacts}) == 2
    assert [Path(artifact.path).read_bytes() for artifact in first.artifacts] == [
        payload for _, payload in entries
    ]
    assert all(
        artifact.source_container_file_name == "unicode-reports.zip"
        for artifact in first.artifacts
    )
    assert all(
        _windows_path_units(Path(artifact.path)) <= 240 for artifact in first.artifacts
    )
    assert all(
        _windows_path_units(Path(artifact.path).parent / ("." + "0" * 32 + ".tmp"))
        <= 240
        for artifact in first.artifacts
    )
    assert list(Path(first.artifacts[0].path).parent.glob(".*.tmp")) == []


def test_short_mailbox_paths_remain_compatible(tmp_path):
    response = materialize_mailbox_attachments(
        _request(
            tmp_path,
            [_pdf("quarterly.pdf", b"%PDF-1.7 short path")],
            message_id="short-message",
        ),
        _context("short-message"),
    )

    assert response.failures == []
    assert response.artifacts[0].path == str(
        (tmp_path / "mailbox" / "short-message" / "quarterly.pdf").resolve()
    )
    assert Path(response.artifacts[0].path).read_bytes() == b"%PDF-1.7 short path"


def test_impossible_mailbox_root_fails_before_direct_or_zip_materialization(tmp_path):
    impossible_root = tmp_path
    while _windows_path_units(impossible_root) <= 250:
        impossible_root /= "root-segment-" + "x" * 24
    settings = replace(_settings(tmp_path), output_dir=str(impossible_root))
    direct_request = _request(
        tmp_path,
        [_pdf("report.pdf", b"%PDF-1.7 direct")],
        message_id="impossible-direct",
    )
    zip_request = _request(
        tmp_path,
        [_attachment(_zip_bytes([("report.pdf", b"%PDF-1.7 zipped")]))],
        message_id="impossible-zip",
    )
    direct_request = replace(direct_request, settings=settings)
    zip_request = replace(zip_request, settings=settings)
    ctx = _context("impossible-root")

    for request in (direct_request, zip_request):
        with pytest.raises(AppError) as error:
            materialize_mailbox_attachments(request, ctx)
        assert error.value.code == "mailbox_attachment_output_dir_invalid"
        assert error.value.retryable is False
        assert error.value.context["next_action"]
    assert not impossible_root.exists()


def test_provider_message_ids_that_sanitize_to_the_same_name_remain_distinct(
    tmp_path,
):
    ctx = _context("message-id-collision")
    artifacts = []
    first_message_id = "a?b"
    mimicking_message_id = (
        "a_b-" + hashlib.sha256(first_message_id.encode("utf-8")).hexdigest()[:12]
    )
    payloads = [
        b"%PDF-1.7 question",
        b"%PDF-1.7 asterisk",
        b"%PDF-1.7 question",
    ]
    for message_id, payload in zip(
        (first_message_id, "a*b", mimicking_message_id), payloads, strict=True
    ):
        response = materialize_mailbox_attachments(
            _request(
                tmp_path,
                [_pdf("report.pdf", payload)],
                message_id=message_id,
            ),
            ctx,
        )
        assert response.failures == []
        artifacts.append(response.artifacts[0])

    assert artifacts[0].path != artifacts[1].path
    assert artifacts[0].path != artifacts[2].path
    assert [Path(artifact.path).read_bytes() for artifact in artifacts] == payloads


def test_direct_path_identities_survive_casefold_hash_and_extension_aliases(
    tmp_path,
):
    lossy_name = "A?B.pdf"
    cases = [
        ("Report.pdf", b"%PDF upper", "report.pdf", b"%PDF lower"),
        (
            lossy_name,
            b"%PDF shared",
            "A_B-" + hashlib.sha256(lossy_name.encode()).hexdigest()[:12] + ".pdf",
            b"%PDF shared",
        ),
        ("report", b"%PDF shared", "report.pdf", b"%PDF shared"),
    ]

    for index, (first_name, first_payload, second_name, second_payload) in enumerate(
        cases
    ):
        message_id = f"path-identity-{index}"
        attachments = [
            _pdf(first_name, first_payload),
            _pdf(second_name, second_payload),
        ]
        request = _request(tmp_path, attachments, message_id=message_id)
        ctx = _context(message_id)
        full = materialize_mailbox_attachments(request, ctx)

        assert full.failures == []
        assert len({artifact.path.casefold() for artifact in full.artifacts}) == 2
        assert [Path(artifact.path).read_bytes() for artifact in full.artifacts] == [
            first_payload,
            second_payload,
        ]


def test_atomic_direct_commit_preserves_a_competing_writer(
    tmp_path, external_boundary_mocks_only
):
    request = _request(
        tmp_path,
        [_pdf("report.pdf", b"%PDF-1.7 intended payload")],
        message_id="atomic-commit-race",
    )
    ctx = _context("atomic-commit-race")
    competing_payload = b"%PDF-1.7 competing payload at commit"
    commit_operation = "rename" if file_service.os.name == "nt" else "link"
    actual_no_replace_commit = getattr(file_service.os, commit_operation)
    actual_replace = file_service.os.replace

    def race_no_replace_commit(source, destination):
        Path(destination).write_bytes(competing_payload)
        return actual_no_replace_commit(source, destination)

    def race_replace_commit(source, destination):
        Path(destination).write_bytes(competing_payload)
        return actual_replace(source, destination)

    external_boundary_mocks_only.setattr(
        file_service.os, commit_operation, race_no_replace_commit
    )
    external_boundary_mocks_only.setattr(
        file_service.os, "replace", race_replace_commit
    )

    with pytest.raises(AppError) as error:
        materialize_mailbox_attachments(request, ctx)

    output_dir = tmp_path / "mailbox" / "atomic-commit-race"
    assert error.value.code == "mailbox_attachment_output_collision"
    assert error.value.retryable is False
    assert (output_dir / "report.pdf").read_bytes() == competing_payload
    assert list(output_dir.glob(".*.tmp")) == []


def test_zip_output_conflict_preserves_prior_pdf_and_leaves_no_staging_files(tmp_path):
    previous_payload = b"%PDF-1.7 previous archive member"
    new_payload = b"%PDF-1.7 changed archive member"
    first = _materialize(
        tmp_path,
        _zip_bytes([("reports/report.pdf", previous_payload)]),
        message_id="zip-output-conflict",
    )
    second = _materialize(
        tmp_path,
        _zip_bytes([("reports/report.pdf", new_payload)]),
        message_id="zip-output-conflict",
    )

    assert first.failures == []
    assert second.artifacts == []
    assert [failure.error_code for failure in second.failures] == [
        "mailbox_zip_output_conflict"
    ]
    assert Path(first.artifacts[0].path).read_bytes() == previous_payload
    assert list(Path(first.artifacts[0].path).parent.glob(".*.tmp")) == []
