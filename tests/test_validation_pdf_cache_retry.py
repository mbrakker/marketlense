from __future__ import annotations

import pytest

from src.generators.validation import evidence
from src.utils.errors import AppError


def test_validation_pdf_cache_propagates_retryable_read_error(
    run_context,
    assert_app_error,
    external_boundary_mocks_only,
) -> None:
    def _read_latest_pdf_cache_text(request, ctx):
        raise AppError(
            code="pdf_cache_locked",
            message="cache is locked",
            retryable=True,
            severity="warning",
        )

    external_boundary_mocks_only.setattr(
        evidence.file_service,
        "read_latest_pdf_cache_text",
        _read_latest_pdf_cache_text,
    )

    with pytest.raises(AppError) as captured:
        evidence.load_pdf_text_from_cache(
            "cache", "0123456789abcdef0123456789abcdef", run_context
        )

    assert_app_error(
        captured.value,
        code="pdf_cache_locked",
        retryable=True,
        severity="warning",
    )


def test_validation_pdf_cache_treats_permanent_read_error_as_best_effort(
    run_context,
    external_boundary_mocks_only,
) -> None:
    def _read_latest_pdf_cache_text(request, ctx):
        raise AppError(
            code="pdf_cache_corrupt",
            message="cache is corrupt",
            retryable=False,
        )

    external_boundary_mocks_only.setattr(
        evidence.file_service,
        "read_latest_pdf_cache_text",
        _read_latest_pdf_cache_text,
    )

    assert (
        evidence.load_pdf_text_from_cache(
            "cache", "0123456789abcdef0123456789abcdef", run_context
        )
        == ""
    )
