from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class RepositoryPathClassification:
    schema_version: str = field(
        metadata={"doc": "Repository analysis path-classification schema version."}
    )
    include: bool = field(
        metadata={"doc": "Whether repository analysis tools should inspect the path."}
    )
    section: str = field(
        metadata={"doc": "First-party report section for included paths."}
    )
    reason: str = field(metadata={"doc": "Stable exclusion reason for skipped paths."})


FIRST_PARTY_SECTIONS = {
    "src": "src",
    "tests": "tests",
    "scripts": "scripts",
    "Wordpress": "wordpress",
}
TOP_LEVEL_RUNTIME_DIRS = {
    ".codex_tmp",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".streamlit",
    ".tmp",
    ".venv",
    ".vscode",
    "__pycache__",
    "agent-skills",
    "cache",
    "env",
    "ENV",
    "htmlcov",
    "logs",
    "node_modules",
    "out",
    "state",
    "venv",
}
TOP_LEVEL_TEMP_PREFIXES = (
    ".pytest_tmp",
    ".pytest-tmp",
    ".pytest-work",
    "live-wp-executor-",
    "mutation_cov_",
    "tmp_",
    "tmp-",
    "tmpu",
)
FIRST_PARTY_GENERATED_DIRS = {
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
    "node_modules",
}
VENDORED_PREFIXES = ("tools/browser-use",)
TRAVERSAL_PARENT_PREFIXES = ("tools",)


def normalize_repository_path(path: str | Path) -> str:
    normalized = str(path).replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def is_repository_analysis_traversal_parent(path: str | Path) -> bool:
    normalized = normalize_repository_path(path)
    if not normalized:
        return True
    return any(
        prefix.startswith(f"{normalized}/")
        for prefix in (*VENDORED_PREFIXES, *TRAVERSAL_PARENT_PREFIXES)
    )


def classify_repository_path(path: str | Path) -> RepositoryPathClassification:
    normalized = normalize_repository_path(path)
    parts = [part for part in normalized.split("/") if part]
    if not parts:
        return RepositoryPathClassification(
            schema_version="1.0",
            include=False,
            section="",
            reason="repository root",
        )

    first = parts[0]
    if any(
        normalized == prefix or normalized.startswith(f"{prefix}/")
        for prefix in VENDORED_PREFIXES
    ):
        return RepositoryPathClassification(
            schema_version="1.0",
            include=False,
            section="",
            reason="vendored dependency tree",
        )
    if first in TOP_LEVEL_RUNTIME_DIRS or first.startswith(TOP_LEVEL_TEMP_PREFIXES):
        return RepositoryPathClassification(
            schema_version="1.0",
            include=False,
            section="",
            reason="top-level runtime/temp directory",
        )
    section = FIRST_PARTY_SECTIONS.get(first)
    if section is None:
        return RepositoryPathClassification(
            schema_version="1.0",
            include=False,
            section="",
            reason="outside first-party analysis roots",
        )
    if any(part in FIRST_PARTY_GENERATED_DIRS for part in parts[1:-1]):
        return RepositoryPathClassification(
            schema_version="1.0",
            include=False,
            section="",
            reason="generated files inside first-party root",
        )
    return RepositoryPathClassification(
        schema_version="1.0",
        include=True,
        section=section,
        reason="",
    )
