from __future__ import annotations

import json
import inspect
from dataclasses import MISSING, fields, is_dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import pytest

from src.contracts.ingest import IngestSettings
from src.contracts.publish import PublishSettings
from src.contracts.run_context import RunContext
from src.contracts.wordpress import WordPressAuthSettings
from src.services import llm_service, wordpress_service
from src.utils.errors import AppError
from tests.support.fakes import FakeOpenAIBoundary, RequestsRouter


class ExternalBoundaryMocksOnly:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._monkeypatch = monkeypatch

    def _target_module_name(self, target: object) -> str:
        return str(getattr(target, "__name__", target.__class__.__module__) or "")

    def _assert_allowed(self, target: object, attr_name: str) -> None:
        if str(attr_name or "").startswith("_"):
            raise AssertionError(
                f"private/helper patching is forbidden: {self._target_module_name(target)}.{attr_name}"
            )

        target_module = self._target_module_name(target)
        if target_module in {"time", "random", "os"}:
            return
        if target_module.startswith(
            ("requests", "urllib3", "openai", "google", "googleapiclient")
        ):
            return
        if not target_module.startswith("src."):
            return
        if target_module.startswith("src.services."):
            original = getattr(target, attr_name, None)
            original_module = str(getattr(original, "__module__", "") or "")
            if inspect.isfunction(original) or inspect.ismethod(original):
                return
            if original is None:
                return
            if original_module and not original_module.startswith("src."):
                return
            raise AssertionError(
                "only public service boundaries or external client symbols may be patched"
            )
        raise AssertionError(
            f"patching internal non-service code is forbidden: {target_module}.{attr_name}"
        )

    def setattr(
        self,
        target: object,
        name: str,
        value: object,
        raising: bool = True,
    ) -> None:
        self._assert_allowed(target, name)
        self._monkeypatch.setattr(target, name, value, raising=raising)

    def setenv(self, name: str, value: str, prepend: str | None = None) -> None:
        self._monkeypatch.setenv(name, value, prepend=prepend)

    def delenv(self, name: str, raising: bool = True) -> None:
        self._monkeypatch.delenv(name, raising=raising)

    def chdir(self, path: str | Path) -> None:
        self._monkeypatch.chdir(path)


@pytest.fixture
def run_context() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="test-run",
        task_id="test-task",
        span_id="test-span",
    )


@pytest.fixture
def app_paths(tmp_path: Path) -> dict[str, str]:
    output_dir = tmp_path / "out"
    cache_dir = tmp_path / "cache"
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return {
        "output_dir": str(output_dir),
        "cache_dir": str(cache_dir),
        "state_db": str(tmp_path / "state.sqlite"),
        "reports_db": str(tmp_path / "reports.sqlite"),
        "ingest_lock_path": str(tmp_path / "ingest.lock"),
    }


@pytest.fixture
def ingest_settings(app_paths: dict[str, str]) -> IngestSettings:
    repo_root = Path(__file__).resolve().parents[1]
    config_dir = repo_root / "src" / "config"
    return IngestSettings(
        schema_version="1.0",
        google_sa_path="sa.json",
        gdrive_folder_id="folder",
        openai_api_key="key",
        openai_model="gpt-4.1-mini",
        batch_limit=2,
        output_dir=app_paths["output_dir"],
        cache_dir=app_paths["cache_dir"],
        state_db=app_paths["state_db"],
        reports_db=app_paths["reports_db"],
        category_mapping_path=str(config_dir / "category-mappings.yaml"),
        cover_style_path=str(config_dir / "cover-styles.yaml"),
        ingest_lock_path=app_paths["ingest_lock_path"],
        ingest_lock_ttl_seconds=300.0,
        temperature=0.1,
        ingest_worker_limit=2,
        report_worker_limit=2,
        openai_timeout_seconds=30.0,
        rank_timeout_seconds=30.0,
        contents_preview_dpi=72,
        vector_store_keep=True,
        cost_ledger_path=str(Path(app_paths["output_dir"]) / "cost-ledger.jsonl"),
        cost_daily_path=str(Path(app_paths["output_dir"]) / "cost-daily.json"),
        model_pricing={},
    )


@pytest.fixture
def publish_settings_factory(app_paths: dict[str, str]):
    repo_root = Path(__file__).resolve().parents[1]
    config_dir = repo_root / "src" / "config"

    def _factory(
        *,
        validation_policy: str = "block",
        ssl_verify: bool = True,
        ca_bundle_path: str | None = None,
    ) -> PublishSettings:
        return PublishSettings(
            schema_version="1.0",
            output_dir=app_paths["output_dir"],
            state_db=app_paths["state_db"],
            reports_db=app_paths["reports_db"],
            category_mapping_path=str(config_dir / "category-mappings.yaml"),
            media_upload_workers=4,
            validation_policy=validation_policy,
            wp=WordPressAuthSettings(
                schema_version="1.0",
                site_url="https://example.com",
                username="user",
                app_password="pass",
                bearer_token=None,
                post_status="publish",
                post_type="ml_report",
                ssl_verify=ssl_verify,
                ca_bundle_path=ca_bundle_path,
            ),
        )

    return _factory


@pytest.fixture
def assert_logs_have_required_fields():
    required = {
        "run_id",
        "task_id",
        "span_id",
        "trace_id",
        "parent_span_id",
        "span_name",
        "span_depth",
        "timestamp_utc",
        "role",
        "module",
        "event",
    }

    def _assert(records: Iterable[Any]) -> None:
        for idx, record in enumerate(records):
            payload: Any
            if isinstance(record, dict):
                payload = record
            elif hasattr(record, "message"):
                payload = getattr(record, "message")
            else:
                payload = record
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError as exc:
                    raise AssertionError(f"log[{idx}] is not valid JSON") from exc
            if not isinstance(payload, dict):
                raise AssertionError(f"log[{idx}] must be a JSON object")
            fields_present = payload.get("fields")
            if isinstance(fields_present, dict):
                merged = {**payload, **fields_present}
            else:
                merged = payload
            missing = sorted(key for key in required if key not in merged)
            if missing:
                raise AssertionError(f"log[{idx}] missing required fields: {missing}")

    return _assert


@pytest.fixture
def assert_no_defaulted_required_fields():
    def _is_empty(value: Any, sentinel_values: set[str]) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            normalized = value.strip()
            return not normalized or normalized.lower() in sentinel_values
        if isinstance(value, (list, tuple, dict, set)):
            return len(value) == 0
        return False

    def _assert(obj: Any, *, sentinel_values: Iterable[str] = ()) -> None:
        if not is_dataclass(obj):
            raise AssertionError("expected dataclass instance")
        normalized_sentinels = {
            str(value).strip().lower()
            for value in sentinel_values
            if str(value).strip()
        }
        for field_def in fields(obj):
            is_required = (
                field_def.default is MISSING and field_def.default_factory is MISSING
            )
            if not is_required:
                continue
            value = getattr(obj, field_def.name)
            if _is_empty(value, normalized_sentinels):
                raise AssertionError(
                    f"required field defaulted/empty: {field_def.name}"
                )

    return _assert


@pytest.fixture
def assert_app_error():
    def _assert(
        err: Exception, *, code: str, retryable: bool, severity: str = "error"
    ) -> None:
        if not isinstance(err, AppError):
            raise AssertionError(f"expected AppError, got {type(err).__name__}")
        assert err.code == code
        assert err.retryable is retryable
        assert err.severity == severity

    return _assert


@pytest.fixture
def idempotency_guard():
    def _guard(
        run_once: Callable[[], Any],
        *,
        side_effect_count: Callable[[], int],
    ) -> tuple[Any, Any]:
        first = run_once()
        first_count = int(side_effect_count())
        second = run_once()
        second_count = int(side_effect_count())
        if second_count != first_count:
            raise AssertionError(
                f"idempotency check failed: first_count={first_count}, second_count={second_count}"
            )
        return first, second

    return _guard


@pytest.fixture
def external_boundary_mocks_only(
    monkeypatch: pytest.MonkeyPatch,
) -> ExternalBoundaryMocksOnly:
    return ExternalBoundaryMocksOnly(monkeypatch)


@pytest.fixture
def wordpress_http(
    external_boundary_mocks_only: ExternalBoundaryMocksOnly,
) -> RequestsRouter:
    router = RequestsRouter()
    external_boundary_mocks_only.setattr(wordpress_service.requests, "get", router.get)
    external_boundary_mocks_only.setattr(
        wordpress_service.requests, "post", router.post
    )
    return router


@pytest.fixture
def fake_openai(
    external_boundary_mocks_only: ExternalBoundaryMocksOnly,
) -> FakeOpenAIBoundary:
    boundary = FakeOpenAIBoundary()
    external_boundary_mocks_only.setattr(
        llm_service.openai_legacy, "OpenAI", boundary.client_factory
    )
    return boundary
