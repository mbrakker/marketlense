from __future__ import annotations

import ast
import json
from pathlib import Path

from src.services import llm_service, openai_service


ROOT = Path(__file__).resolve().parents[1]
SERVICES_ROOT = ROOT / "src" / "services"


def _imports_openai_service(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "src.services.openai_service" for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == "src.services" and any(
                alias.name == "openai_service" for alias in node.names
            ):
                return True
            if node.module == "src.services.openai_service":
                return True
    return False


def test_production_code_uses_only_canonical_llm_boundary() -> None:
    violations = [
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "src").rglob("*.py"))
        if path != SERVICES_ROOT / "openai_service.py" and _imports_openai_service(path)
    ]

    assert violations == []
    vector_store_source = (SERVICES_ROOT / "vector_store_service.py").read_text(
        encoding="utf-8"
    )
    assert "openai_service = llm_service" not in vector_store_source


def test_llm_service_owns_all_provider_operation_exports() -> None:
    required = {
        "analyze_report",
        "openai_chat_json",
        "openai_chat_json_with_images",
        "openai_ocr_pdf",
        "openai_respond_with_vector_store",
        "openai_vector_store_create",
        "openai_vector_store_upload_file",
        "openai_vector_store_attach_file",
        "openai_vector_store_status",
        "openai_vector_store_delete",
        "openai_vector_store_update_metadata",
    }

    assert required <= set(dir(llm_service))
    source = Path(llm_service.__file__).read_text(encoding="utf-8")
    assert "_openai_boundary" not in source
    assert "from src.services import openai_service" not in source


def test_service_boundary_map_names_llm_service_as_canonical() -> None:
    payload = json.loads(
        (ROOT / "docs" / "quality" / "service_boundary_map.json").read_text(
            encoding="utf-8"
        )
    )
    openai_boundary = payload["systems"]["openai"]

    assert openai_boundary["canonical_entrypoint"] == "src/services/llm_service.py"
    assert "src/services/_llm_service/" in openai_boundary["private_roots"]
    assert (
        openai_boundary["compatibility_entrypoint"] == "src/services/openai_service.py"
    )


def test_llm_service_family_files_remain_below_threshold() -> None:
    paths = [
        SERVICES_ROOT / "llm_service.py",
        SERVICES_ROOT / "openai_service.py",
        *sorted((SERVICES_ROOT / "_llm_service").glob("*.py")),
    ]
    oversized = {
        path.relative_to(ROOT).as_posix(): len(
            path.read_text(encoding="utf-8").splitlines()
        )
        for path in paths
        if path.exists() and len(path.read_text(encoding="utf-8").splitlines()) > 1000
    }

    assert oversized == {}


def test_legacy_openai_facade_delegates_to_canonical_llm_exports() -> None:
    exported_names = [
        "analyze_report",
        "openai_chat_json",
        "openai_chat_json_with_images",
        "openai_ocr_pdf",
        "openai_respond_with_vector_store",
        "openai_vector_store_create",
        "openai_vector_store_upload_file",
        "openai_vector_store_attach_file",
        "openai_vector_store_status",
        "openai_vector_store_delete",
        "openai_vector_store_update_metadata",
    ]

    assert all(
        getattr(openai_service, name) is getattr(llm_service, name)
        for name in exported_names
    )
