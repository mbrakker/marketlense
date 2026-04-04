import json
from types import SimpleNamespace

import pytest

from src.contracts.files import ReadTextRequest
from src.contracts.run_context import RunContext
from src.generators.analysis_pack_cache import (
    CachedPackAdaptResult,
    load_cached_pack,
)
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_load_cached_pack_returns_cache_disabled_without_key(
    assert_no_defaulted_required_fields,
):
    result = load_cached_pack(
        cache_key="",
        ctx=_ctx(),
        resolve_path=lambda: "unused.json",
        read_text=lambda request, ctx: SimpleNamespace(content="{}"),
        on_read_failed=lambda exc, path: None,
        adapt_payload=lambda payload, path: CachedPackAdaptResult(
            schema_version="1.0",
            status="hit",
            value=payload,
        ),
    )

    assert result.status == "cache_disabled"
    assert result.path is None
    assert_no_defaulted_required_fields(result)


def test_load_cached_pack_returns_hit_with_typed_adapter(
    assert_no_defaulted_required_fields,
):
    captured_requests = []

    def _read_text(request: ReadTextRequest, ctx: RunContext):
        captured_requests.append((request, ctx))
        return SimpleNamespace(
            content=json.dumps(
                {
                    "_cache": {"key": "cache-key"},
                    "status": "pass",
                }
            )
        )

    result = load_cached_pack(
        cache_key="cache-key",
        ctx=_ctx(),
        resolve_path=lambda: "packs/validation.json",
        read_text=_read_text,
        on_read_failed=lambda exc, path: None,
        adapt_payload=lambda payload, path: CachedPackAdaptResult(
            schema_version="1.0",
            status="hit",
            value={"payload": payload, "path": path},
        ),
    )

    assert result.status == "hit"
    assert result.path == "packs/validation.json"
    assert result.value == {
        "payload": {"_cache": {"key": "cache-key"}, "status": "pass"},
        "path": "packs/validation.json",
    }
    assert len(captured_requests) == 1
    request, ctx = captured_requests[0]
    assert request.path == "packs/validation.json"
    assert ctx.task_id == "t"
    assert_no_defaulted_required_fields(request)
    assert_no_defaulted_required_fields(result)


def test_load_cached_pack_returns_key_mismatch_without_adapting():
    adapted = []

    result = load_cached_pack(
        cache_key="expected",
        ctx=_ctx(),
        resolve_path=lambda: "packs/artifacts.json",
        read_text=lambda request, ctx: SimpleNamespace(
            content=json.dumps({"_cache": {"key": "other"}})
        ),
        on_read_failed=lambda exc, path: None,
        adapt_payload=lambda payload, path: adapted.append((payload, path)),
    )

    assert result.status == "key_mismatch"
    assert result.value is None
    assert adapted == []


def test_load_cached_pack_calls_read_failed_callback_for_non_missing_file():
    captured_errors = []

    def _read_text(request: ReadTextRequest, ctx: RunContext):
        raise AppError(code="read_failed", message="disk error", retryable=False)

    result = load_cached_pack(
        cache_key="cache-key",
        ctx=_ctx(),
        resolve_path=lambda: "packs/report.json",
        read_text=_read_text,
        on_read_failed=lambda exc, path: captured_errors.append((exc.code, path)),
        adapt_payload=lambda payload, path: CachedPackAdaptResult(
            schema_version="1.0",
            status="hit",
            value=payload,
        ),
    )

    assert result.status == "read_failed"
    assert captured_errors == [("read_failed", "packs/report.json")]


def test_load_cached_pack_propagates_adapter_rejection_status():
    result = load_cached_pack(
        cache_key="cache-key",
        ctx=_ctx(),
        resolve_path=lambda: "packs/taxonomy.json",
        read_text=lambda request, ctx: SimpleNamespace(
            content=json.dumps({"_cache": {"key": "cache-key"}, "taxonomy": []})
        ),
        on_read_failed=lambda exc, path: None,
        adapt_payload=lambda payload, path: CachedPackAdaptResult(
            schema_version="1.0",
            status="schema_invalid",
            value=None,
        ),
    )

    assert result.status == "schema_invalid"
    assert result.path == "packs/taxonomy.json"
    assert result.value is None


def test_load_cached_pack_propagates_retryable_read_error(assert_app_error):
    captured_errors = []

    def _read_text(request: ReadTextRequest, ctx: RunContext):
        del request, ctx
        raise AppError(
            code="read_failed",
            message="temporary disk error",
            retryable=True,
        )

    with pytest.raises(AppError) as err:
        load_cached_pack(
            cache_key="cache-key",
            ctx=_ctx(),
            resolve_path=lambda: "packs/report.json",
            read_text=_read_text,
            on_read_failed=lambda exc, path: captured_errors.append((exc.code, path)),
            adapt_payload=lambda payload, path: CachedPackAdaptResult(
                schema_version="1.0",
                status="hit",
                value=payload,
            ),
        )

    assert_app_error(
        err.value,
        code="read_failed",
        retryable=True,
        severity="error",
    )
    assert captured_errors == [("read_failed", "packs/report.json")]
