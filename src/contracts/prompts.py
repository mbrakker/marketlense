from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

PROMPT_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class PromptDryRunBenchmark:
    schema_version: str = field(
        metadata={"doc": "Prompt dry-run benchmark schema version."}
    )
    expected_output_tokens: int = field(
        default=0,
        metadata={
            "doc": "Expected output-token budget used for fixture-corpus cost estimation."
        },
    )
    expected_tool_calls: int = field(
        default=0,
        metadata={
            "doc": "Expected tool-call count used for fixture-corpus cost estimation."
        },
    )
    expected_browser_attempts: int = field(
        default=0,
        metadata={"doc": "Expected browser-attempt count represented by this fixture."},
    )
    expected_ocr_calls: int = field(
        default=0,
        metadata={"doc": "Expected OCR-call count represented by this fixture."},
    )


@dataclass(frozen=True)
class PromptLoadRequest:
    schema_version: str = field(metadata={"doc": "Prompt load request schema version."})
    namespace: str = field(metadata={"doc": "Prompt namespace under src/prompts."})
    reload_if_changed: bool = field(
        default=False,
        metadata={"doc": "Force reload from disk if prompt files changed."},
    )
    force_reload: bool = field(
        default=False, metadata={"doc": "Bypass cache and reload prompts from disk."}
    )


@dataclass(frozen=True)
class PromptRenderRequest:
    schema_version: str = field(
        metadata={"doc": "Prompt render request schema version."}
    )
    template: "PromptTemplate" = field(metadata={"doc": "Prompt template to render."})
    variables: Dict[str, Any] = field(
        metadata={"doc": "Variables to render into the prompt template."}
    )


@dataclass(frozen=True)
class PromptRenderResponse:
    schema_version: str = field(
        metadata={"doc": "Prompt render response schema version."}
    )
    text: str = field(metadata={"doc": "Rendered prompt text."})


@dataclass(frozen=True)
class PromptSet:
    schema_version: str = field(metadata={"doc": "Prompt set schema version."})
    system: "PromptTemplate" = field(metadata={"doc": "System prompt template."})
    user: "PromptTemplate" = field(metadata={"doc": "User prompt template."})


@dataclass(frozen=True)
class PromptTemplate:
    schema_version: str = field(metadata={"doc": "Prompt template schema version."})
    path: str = field(metadata={"doc": "Prompt file path."})
    text: str = field(metadata={"doc": "Prompt template text."})
    sha256: str = field(metadata={"doc": "SHA-256 hash of the prompt text."})
    include_paths: list[str] = field(
        default_factory=list,
        metadata={"doc": "Prompt include file paths composed by the prompt service."},
    )
    include_sha256s: list[str] = field(
        default_factory=list,
        metadata={"doc": "SHA-256 hashes for prompt include text in composition order."},
    )
    schema_snippets: Dict[str, str] = field(
        default_factory=dict,
        metadata={"doc": "Generated source-schema prompt snippets keyed by variable name."},
    )
    schema_snippet_sources: Dict[str, str] = field(
        default_factory=dict,
        metadata={"doc": "Source schema references used to generate prompt snippets."},
    )


@dataclass(frozen=True)
class PromptNamespaceListRequest:
    schema_version: str = field(
        metadata={"doc": "Prompt namespace list request schema version."}
    )
    reload_if_changed: bool = field(
        default=True,
        metadata={"doc": "Reload namespaces when on-disk prompt files change."},
    )
    force_reload: bool = field(
        default=False,
        metadata={"doc": "Bypass in-memory cache for namespace prompt loading."},
    )


@dataclass(frozen=True)
class PromptNamespaceSummary:
    schema_version: str = field(
        metadata={"doc": "Prompt namespace summary schema version."}
    )
    namespace: str = field(metadata={"doc": "Prompt namespace path under src/prompts."})
    system_path: str = field(metadata={"doc": "Filesystem path to system.yaml."})
    user_path: str = field(metadata={"doc": "Filesystem path to user.yaml."})
    system_sha256: str = field(metadata={"doc": "SHA-256 hash of system prompt text."})
    user_sha256: str = field(metadata={"doc": "SHA-256 hash of user prompt text."})


@dataclass(frozen=True)
class PromptNamespaceListResponse:
    schema_version: str = field(
        metadata={"doc": "Prompt namespace list response schema version."}
    )
    namespaces: list[PromptNamespaceSummary] = field(
        metadata={"doc": "Discovered prompt namespaces with hashes."}
    )


@dataclass(frozen=True)
class PromptDryRunFixture:
    schema_version: str = field(
        metadata={"doc": "Prompt dry-run fixture schema version."}
    )
    namespace: str = field(
        metadata={"doc": "Prompt namespace covered by this fixture."}
    )
    family: str = field(
        metadata={"doc": "Prompt family label used for coverage and reporting."}
    )
    system_variables: Dict[str, Any] = field(
        metadata={"doc": "Variables used to render the system prompt template."}
    )
    user_variables: Dict[str, Any] = field(
        metadata={"doc": "Variables used to render the user prompt template."}
    )
    benchmark: PromptDryRunBenchmark = field(
        default_factory=lambda: PromptDryRunBenchmark(
            schema_version=PROMPT_SCHEMA_VERSION
        ),
        metadata={
            "doc": "Benchmark metadata used for fixture-corpus regression budgets."
        },
    )
    model: str = field(
        default="",
        metadata={"doc": "Representative model identifier for this prompt fixture."},
    )
    temperature: float = field(
        default=0.0,
        metadata={"doc": "Representative temperature for this prompt fixture."},
    )


@dataclass(frozen=True)
class PromptDryRunRequest:
    schema_version: str = field(
        metadata={"doc": "Prompt dry-run request schema version."}
    )
    namespaces: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Optional explicit prompt namespaces to validate. Empty means all discovered namespaces."
        },
    )
    reload_if_changed: bool = field(
        default=True,
        metadata={"doc": "Reload prompts from disk when source files changed."},
    )
    force_reload: bool = field(
        default=False,
        metadata={"doc": "Bypass prompt cache for prompt and namespace loading."},
    )


@dataclass(frozen=True)
class PromptDryRunResult:
    schema_version: str = field(
        metadata={"doc": "Prompt dry-run result schema version."}
    )
    namespace: str = field(metadata={"doc": "Validated prompt namespace."})
    family: str = field(
        metadata={"doc": "Prompt family label for coverage and reporting."}
    )
    fixture_path: str = field(
        metadata={"doc": "Filesystem path to the fixture registry file."}
    )
    system_path: str = field(metadata={"doc": "Filesystem path to system.yaml."})
    user_path: str = field(metadata={"doc": "Filesystem path to user.yaml."})
    system_sha256: str = field(metadata={"doc": "SHA-256 hash of system prompt text."})
    user_sha256: str = field(metadata={"doc": "SHA-256 hash of user prompt text."})
    rendered_system_prompt: str = field(
        metadata={"doc": "Rendered system prompt text produced by the dry-run."}
    )
    rendered_user_prompt: str = field(
        metadata={"doc": "Rendered user prompt text produced by the dry-run."}
    )
    benchmark: PromptDryRunBenchmark = field(
        default_factory=lambda: PromptDryRunBenchmark(
            schema_version=PROMPT_SCHEMA_VERSION
        ),
        metadata={"doc": "Benchmark metadata copied from the fixture registry."},
    )
    render_runtime_ms: float = field(
        default=0.0,
        metadata={
            "doc": "Measured prompt load and render runtime for this namespace in milliseconds."
        },
    )
    model: str = field(
        default="",
        metadata={"doc": "Representative model identifier recorded by the fixture."},
    )
    temperature: float = field(
        default=0.0,
        metadata={"doc": "Representative temperature recorded by the fixture."},
    )


@dataclass(frozen=True)
class PromptDryRunResponse:
    schema_version: str = field(
        metadata={"doc": "Prompt dry-run response schema version."}
    )
    results: list[PromptDryRunResult] = field(
        metadata={"doc": "Validated prompt dry-run results for each namespace."}
    )
