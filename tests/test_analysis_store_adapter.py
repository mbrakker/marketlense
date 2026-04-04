import json
from pathlib import Path

from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisPackPathResponse,
    AnalysisStorePackRequest,
    AnalysisStorePackResponse,
)
from src.contracts.run_context import RunContext
from src.generators.analysis_store_adapter import resolve_pack_path, store_pack


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


class CanonicalAnalysisStore:
    def __init__(self, *, output_path: str):
        self.output_path = output_path
        self.pack_path_requests = []
        self.store_pack_requests = []

    def pack_path(self, request: AnalysisPackPathRequest, ctx: RunContext):
        self.pack_path_requests.append((request, ctx))
        return AnalysisPackPathResponse(
            schema_version="1.0",
            output_path=self.output_path,
        )

    def store_pack(self, request: AnalysisStorePackRequest, ctx: RunContext):
        self.store_pack_requests.append((request, ctx))
        return AnalysisStorePackResponse(
            schema_version="1.0",
            output_path=self.output_path,
        )


class LegacyAnalysisStore:
    def __init__(self, *, output_path: str):
        self.output_path = output_path
        self.pack_path_calls = []
        self.store_pack_calls = []

    def pack_path(
        self,
        output_dir: str,
        report_id: str,
        pack_name: str,
        report_slug: str | None = None,
    ) -> str:
        self.pack_path_calls.append((output_dir, report_id, pack_name, report_slug))
        return self.output_path

    def store_pack(
        self,
        output_dir: str,
        report_id: str,
        pack_name: str,
        payload: dict,
        ctx: RunContext,
        report_slug: str | None = None,
    ) -> str:
        self.store_pack_calls.append(
            (output_dir, report_id, pack_name, payload, ctx, report_slug)
        )
        return self.output_path


class NoAnalysisStoreMethods:
    pass


def test_resolve_pack_path_uses_canonical_dataclass_boundary(
    tmp_path, assert_no_defaulted_required_fields
):
    request = AnalysisPackPathRequest(
        schema_version="1.0",
        output_dir=str(tmp_path),
        report_id="report-1",
        pack_name="taxonomy",
        report_slug="report-slug",
    )
    store = CanonicalAnalysisStore(output_path="custom/path/taxonomy.json")

    output_path = resolve_pack_path(analysis_store=store, request=request, ctx=_ctx())

    assert output_path == "custom/path/taxonomy.json"
    assert len(store.pack_path_requests) == 1
    captured_request, captured_ctx = store.pack_path_requests[0]
    assert captured_ctx.task_id == "t"
    assert_no_defaulted_required_fields(captured_request)


def test_resolve_pack_path_retries_legacy_positional_signature(tmp_path):
    request = AnalysisPackPathRequest(
        schema_version="1.0",
        output_dir=str(tmp_path),
        report_id="report-legacy",
        pack_name="artifacts",
        report_slug="legacy-slug",
    )
    store = LegacyAnalysisStore(output_path="legacy/path/artifacts.json")

    output_path = resolve_pack_path(analysis_store=store, request=request, ctx=_ctx())

    assert output_path == "legacy/path/artifacts.json"
    assert store.pack_path_calls == [
        (str(tmp_path), "report-legacy", "artifacts", "legacy-slug")
    ]


def test_store_pack_uses_canonical_dataclass_boundary(
    tmp_path, assert_no_defaulted_required_fields
):
    payload = {"schema_version": "1.0", "taxonomy": ["retail"]}
    request = AnalysisStorePackRequest(
        schema_version="1.0",
        output_dir=str(tmp_path),
        report_id="report-1",
        pack_name="taxonomy",
        payload=payload,
        report_slug="report-slug",
    )
    store = CanonicalAnalysisStore(output_path="custom/path/taxonomy.json")

    output_path = store_pack(analysis_store=store, request=request, ctx=_ctx())

    assert output_path == "custom/path/taxonomy.json"
    assert len(store.store_pack_requests) == 1
    captured_request, captured_ctx = store.store_pack_requests[0]
    assert captured_ctx.task_id == "t"
    assert captured_request.payload == payload
    assert_no_defaulted_required_fields(captured_request)


def test_store_pack_retries_legacy_positional_signature(tmp_path):
    payload = {"schema_version": "1.0", "summary": {"tldr": "TLDR"}}
    request = AnalysisStorePackRequest(
        schema_version="1.0",
        output_dir=str(tmp_path),
        report_id="report-legacy",
        pack_name="artifacts",
        payload=payload,
        report_slug="legacy-slug",
    )
    store = LegacyAnalysisStore(output_path="legacy/path/artifacts.json")
    ctx = _ctx()

    output_path = store_pack(analysis_store=store, request=request, ctx=ctx)

    assert output_path == "legacy/path/artifacts.json"
    assert store.store_pack_calls == [
        (str(tmp_path), "report-legacy", "artifacts", payload, ctx, "legacy-slug")
    ]


def test_analysis_store_adapter_falls_back_to_canonical_service(tmp_path):
    ctx = _ctx()
    request = AnalysisStorePackRequest(
        schema_version="1.0",
        output_dir=str(tmp_path),
        report_id="report-service",
        pack_name="validation",
        payload={
            "schema_version": "1.1",
            "status": "pass",
            "severity": "pass",
            "issues": [],
        },
        report_slug="service-slug",
    )

    resolved_path = resolve_pack_path(
        analysis_store=NoAnalysisStoreMethods(),
        request=AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=str(tmp_path),
            report_id="report-service",
            pack_name="validation",
            report_slug="service-slug",
        ),
        ctx=ctx,
    )
    stored_path = store_pack(
        analysis_store=NoAnalysisStoreMethods(),
        request=request,
        ctx=ctx,
    )

    assert stored_path == resolved_path
    payload_path = Path(stored_path)
    assert payload_path.exists()
    assert json.loads(payload_path.read_text(encoding="utf-8")) == request.payload
