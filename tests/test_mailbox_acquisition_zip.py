from __future__ import annotations

import random
import zipfile
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
from src.services.mailbox_acquisition_service import materialize_mailbox_attachments
from src.utils.errors import AppError

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


def _attachment(payload: bytes, *, name: str = "delivery.zip") -> MailboxAttachment:
    return MailboxAttachment(
        schema_version="1.0",
        file_name=name,
        content_type="application/zip",
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
        RunContext(
            schema_version="1.0",
            run_id="zip-test",
            task_id=message_id,
            span_id="zip-span",
        ),
    )


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

    ratio_exact_payload = _zip_bytes(
        [("ratio.pdf", b"A" * 1600)], compression=zipfile.ZIP_DEFLATED
    )
    with ZipFile(BytesIO(ratio_exact_payload)) as archive:
        member = archive.infolist()[0]
        assert member.file_size / member.compress_size == _MAX_ZIP_COMPRESSION_RATIO
    ratio_exact = _materialize(tmp_path, ratio_exact_payload, message_id="ratio-exact")
    assert ratio_exact.failures == []
    ratio_plus_one = _materialize(
        tmp_path,
        _zip_bytes([("ratio.pdf", b"A" * 1601)], compression=zipfile.ZIP_DEFLATED),
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
                MailboxAttachment(
                    schema_version="1.0",
                    file_name="standalone.pdf",
                    content_type="application/pdf",
                    payload=b"%PDF-1.7 standalone",
                ),
            ],
            message_id="mixed-message",
        ),
        RunContext(
            schema_version="1.0",
            run_id="zip-test",
            task_id="mixed-message",
            span_id="zip-span",
        ),
    )

    assert [failure.error_code for failure in response.failures] == [
        "mailbox_zip_member_read_failed"
    ]
    assert [artifact.file_name for artifact in response.artifacts] == ["standalone.pdf"]
    assert Path(response.artifacts[0].path).read_bytes() == b"%PDF-1.7 standalone"
    assert sorted(
        path.name for path in (tmp_path / "mailbox" / "mixed-message").glob("*.pdf")
    ) == ["standalone.pdf"]


def test_zip_write_failure_cleans_temporary_and_already_committed_files(tmp_path):
    output_dir = tmp_path / "mailbox" / "write-failure"
    output_dir.mkdir(parents=True)
    (output_dir / "second.pdf").mkdir()
    archive_payload = _zip_bytes(
        [("first.pdf", b"%PDF-1.7 first"), ("second.pdf", b"%PDF-1.7 second")]
    )

    with pytest.raises(AppError, match="Mailbox ZIP PDF artifacts") as error:
        materialize_mailbox_attachments(
            _request(
                tmp_path,
                [_attachment(archive_payload)],
                message_id="write-failure",
            ),
            RunContext(
                schema_version="1.0",
                run_id="zip-test",
                task_id="write-failure",
                span_id="zip-span",
            ),
        )

    assert error.value.code == "mailbox_zip_write_failed"
    assert error.value.retryable is True
    assert not (output_dir / "first.pdf").exists()
    assert (output_dir / "second.pdf").is_dir()
    assert list(output_dir.glob(".*.tmp")) == []
