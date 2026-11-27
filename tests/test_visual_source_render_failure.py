from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.generators.verified_claims_visual_generator import evaluate_shortlisted_claims
from src.utils.errors import AppError
from tests._test_verified_claims_visual_generator.cases_01_visual import (
    _claim,
    _ctx,
    _dependencies,
    _request,
    _settings,
)


def test_failed_page_render_never_claims_pages_were_inspected(tmp_path):
    claim = _claim("candidate", "A claim", page=5)
    claim["pages"] = [5, 6]
    deps = _dependencies(iter([]), [], [])

    def render(request, _ctx):
        if request.page == 5:
            return SimpleNamespace(image_path="")
        return SimpleNamespace(image_path="page.png")

    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, [claim]),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=replace(deps, render_page_for_crop_refine=render),
    )
    assert result.claims[0].outcome == "skipped"
    assert result.claims[0].inspected_physical_pages == []


def test_retryable_page_render_error_reaches_recovery_owner(tmp_path):
    deps = _dependencies(iter([]), [], [])

    def render(_request, _ctx):
        raise AppError(code="pdf_render_timeout", message="timeout", retryable=True)

    with pytest.raises(AppError) as raised:
        evaluate_shortlisted_claims(
            request=_request(tmp_path, [_claim("candidate", "A claim", page=5)]),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            dependencies=replace(deps, render_page_for_crop_refine=render),
        )
    assert raised.value.code == "pdf_render_timeout"
    assert raised.value.retryable is True
