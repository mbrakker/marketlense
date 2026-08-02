from __future__ import annotations

import ast
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.contracts.artifact_generation import ArtifactRenderTask
from src.contracts.run_context import RunContext
from src.generators.report_analysis_generator import VectorStoreIndexingState
from src.orchestrators._report_analysis_orchestrator.artifact_batches import (
    _execute_artifact_step_batch,
)
from src.orchestrators._report_analysis_orchestrator.payload import (
    _ensure_report_payload_complete,
)
from src.orchestrators._report_analysis_orchestrator.vector_store import (
    _await_vector_store_indexing,
)
from src.utils.errors import AppError

FACADE = Path("src/orchestrators/report_analysis_orchestrator.py")
PACKAGE = Path("src/orchestrators/_report_analysis_orchestrator")

ARTIFACT_BATCH_SYMBOLS = {
    "ArtifactTaskRenderer",
    "_artifact_batch_workers",
    "_execute_artifact_step_batch",
}


def test_artifact_batch_propagates_sequential_render_failure() -> None:
    ctx = RunContext("1.0", "run", "analysis", "span")
    task = ArtifactRenderTask("1.0", "summary", "summary", {}, ctx)

    def fail_render(_task):
        raise RuntimeError("render failed")

    with pytest.raises(RuntimeError, match="render failed"):
        _execute_artifact_step_batch(
            SimpleNamespace(
                artifact_parallel_workers=1,
                artifact_global_max_in_flight=1,
            ),
            [task],
            fail_render,
            ctx,
            "core",
        )


def test_report_payload_completeness_lists_all_missing_public_surfaces() -> None:
    payload = SimpleNamespace(
        title="",
        tldr="",
        commentary="",
        insights=[],
        quote=SimpleNamespace(text=""),
        figure=SimpleNamespace(title="", evidence=""),
    )

    with pytest.raises(AppError) as error:
        _ensure_report_payload_complete(
            payload,
            artifacts={},
            ctx=RunContext("1.0", "run", "analysis", "span"),
            file_id="file-1",
            stage="initial",
        )

    assert error.value.code == "report_payload_incomplete"
    assert set(error.value.context["missing_fields"]) >= {
        "title",
        "tldr",
        "commentary",
        "insights",
        "figure.title",
        "figure.evidence",
    }


def test_vector_store_wait_rejects_missing_store_identity() -> None:
    state = VectorStoreIndexingState(None, None, None, None, None)

    with pytest.raises(AppError, match="vector_store_id is required"):
        _await_vector_store_indexing(state, None, None, None)


VECTOR_STORE_SYMBOLS = {
    "VECTOR_STORE_READY_STATUSES",
    "VECTOR_STORE_FAILED_STATUSES",
    "VECTOR_STORE_POLL_INTERVAL_SECONDS",
    "VECTOR_STORE_POLL_SCHEDULE_SECONDS",
    "_is_vector_store_ready",
    "_await_vector_store_indexing",
}

PAYLOAD_SYMBOLS = {
    "REPORT_PAYLOAD_SENTINELS",
    "_attach_payload_analysis_metadata",
    "_serialize_context_category_fit_payload",
    "_ensure_report_payload_complete",
}

VALIDATION_SYMBOLS = {
    "_run_validation_regeneration_loop",
    "_run_validation_with_fallback",
    "_store_validation_snapshot",
}

REGENERATION_PLAN_SYMBOLS = {
    "RULE_ID_RE",
    "TARGET_ORDER",
    "BROAD_TARGETS",
    "_build_regeneration_plan",
    "_build_target",
    "_normalize_regeneration_issue",
    "_extract_rule_id",
    "_target_section",
    "_target_steps",
    "_target_prompt_namespaces",
    "_issue_grounding",
    "_lookup_topic_grounding",
    "_lookup_insight_grounding",
    "_lookup_quote_grounding",
}

MANIFEST_SYMBOLS = {
    "record_validation_analysis_stage",
}

PUBLIC_COORDINATOR_SYMBOLS = {
    "run_report_analysis",
}

ALL_MOVED_SYMBOLS = (
    ARTIFACT_BATCH_SYMBOLS
    | VECTOR_STORE_SYMBOLS
    | PAYLOAD_SYMBOLS
    | VALIDATION_SYMBOLS
    | REGENERATION_PLAN_SYMBOLS
    | MANIFEST_SYMBOLS
)


def _owned_symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    owned: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            owned.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    owned.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            owned.add(node.target.id)
    return owned


def _imported_siblings(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    sibling_names = {
        "artifact_batches",
        "payload",
        "regeneration_plan",
        "shared",
        "validation",
        "vector_store",
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        module = node.module or ""
        if node.level == 1 and module in sibling_names:
            imports.add(module)
        prefix = "src.orchestrators._report_analysis_orchestrator."
        if module.startswith(prefix):
            imports.add(module.removeprefix(prefix).split(".", 1)[0])
    return imports


def test_report_analysis_orchestrator_uses_semantic_private_modules() -> None:
    artifact_batches = PACKAGE / "artifact_batches.py"
    vector_store = PACKAGE / "vector_store.py"
    payload = PACKAGE / "payload.py"
    validation = PACKAGE / "validation.py"
    regeneration_plan = PACKAGE / "regeneration_plan.py"
    manifest = PACKAGE / "manifest.py"
    shared = PACKAGE / "shared.py"

    assert PACKAGE.joinpath("__init__.py").is_file()
    assert shared.is_file()
    assert artifact_batches.is_file()
    assert vector_store.is_file()
    assert payload.is_file()
    assert validation.is_file()
    assert regeneration_plan.is_file()
    assert manifest.is_file()

    facade_owned = _owned_symbols(FACADE)
    assert facade_owned >= PUBLIC_COORDINATOR_SYMBOLS
    assert facade_owned.isdisjoint(ALL_MOVED_SYMBOLS)

    assert _owned_symbols(artifact_batches) >= ARTIFACT_BATCH_SYMBOLS
    assert _owned_symbols(vector_store) >= VECTOR_STORE_SYMBOLS
    assert _owned_symbols(payload) >= PAYLOAD_SYMBOLS
    assert _owned_symbols(validation) >= VALIDATION_SYMBOLS
    assert _owned_symbols(regeneration_plan) >= REGENERATION_PLAN_SYMBOLS
    assert _owned_symbols(manifest) >= MANIFEST_SYMBOLS

    assert _imported_siblings(shared) == set()
    assert _imported_siblings(artifact_batches) <= {"shared"}
    assert _imported_siblings(vector_store) <= {"shared"}
    assert _imported_siblings(payload) <= {"shared"}
    assert _imported_siblings(regeneration_plan) <= set()
    assert _imported_siblings(manifest) <= set()
    assert _imported_siblings(validation) <= {
        "payload",
        "manifest",
        "regeneration_plan",
        "shared",
    }


def test_report_analysis_orchestrator_facade_preserves_compatibility_imports() -> None:
    facade = importlib.import_module("src.orchestrators.report_analysis_orchestrator")

    for symbol in ALL_MOVED_SYMBOLS | PUBLIC_COORDINATOR_SYMBOLS:
        assert hasattr(facade, symbol), symbol
