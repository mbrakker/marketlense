from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

PROMPT_SCHEMA_VERSION = "1.0"
PROMPT_COMPOSITION_VERSION = "2.0"
PROMPT_IDENTITY_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class PromptDependency:
    """One content-addressed prompt or schema input without machine-local paths."""

    schema_version: str = field(
        metadata={"doc": "Prompt dependency contract schema version."}
    )
    path: str = field(
        metadata={
            "doc": "Canonical prompts/ or schemas/ relative path, never an absolute path."
        }
    )
    sha256: str = field(metadata={"doc": "SHA-256 of the dependency file bytes."})
    kind: str = field(
        metadata={
            "doc": "Dependency role: system_root, user_root, partial, or schema_snippet."
        }
    )
    source: str = field(
        default="",
        metadata={
            "doc": "Bounded source detail such as a JSON Pointer, when applicable."
        },
    )


@dataclass(frozen=True)
class PromptDependencyManifest:
    """All content inputs that can alter one namespace's rendered prompt."""

    schema_version: str = field(
        metadata={"doc": "Prompt dependency-manifest schema version."}
    )
    namespace: str = field(
        metadata={"doc": "Canonical prompt namespace under src/prompts."}
    )
    system_root: PromptDependency = field(
        metadata={"doc": "Content-addressed system.yaml root dependency."}
    )
    user_root: PromptDependency = field(
        metadata={"doc": "Content-addressed user.yaml root dependency."}
    )
    included_partials: list[PromptDependency] = field(
        default_factory=list,
        metadata={"doc": "Ordered partial dependencies from both prompt roots."},
    )
    schema_snippets: list[PromptDependency] = field(
        default_factory=list,
        metadata={"doc": "Ordered schema-file dependencies from both prompt roots."},
    )
    composition_version: str = field(
        default=PROMPT_COMPOSITION_VERSION,
        metadata={"doc": "Version of canonical include and schema composition."},
    )
    prompt_content_hash: str = field(
        default="",
        metadata={
            "doc": "Canonical SHA-256 identity of this manifest excluding this field."
        },
    )


@dataclass(frozen=True)
class LLMExecutionIdentity:
    """Content and execution compatibility identity for a model invocation."""

    schema_version: str = field(
        metadata={"doc": "LLM execution-identity schema version."}
    )
    prompt_content_hash: str = field(
        metadata={
            "doc": "Canonical prompt-content identity from its dependency manifest."
        }
    )
    provider: str = field(metadata={"doc": "Resolved model provider."})
    model: str = field(metadata={"doc": "Resolved provider model."})
    temperature: float | None = field(
        metadata={"doc": "Sampling temperature sent to the provider, if supported."}
    )
    seed: int | None = field(
        metadata={"doc": "Configured deterministic seed, if supported."}
    )
    output_controls: Dict[str, Any] = field(
        default_factory=dict,
        metadata={"doc": "Stable output and token controls for the invocation."},
    )
    retrieval_mode: str = field(
        default="chat_json",
        metadata={"doc": "Resolved retrieval mode that affects model output."},
    )
    routing_policy: Dict[str, Any] = field(
        default_factory=dict,
        metadata={"doc": "Resolved routing policy values affecting execution."},
    )
    compaction_policy: Dict[str, Any] = field(
        default_factory=dict,
        metadata={"doc": "Resolved deterministic context-compaction policy."},
    )
    output_contract_schema_version: str = field(
        default="",
        metadata={"doc": "Output contract or structured-output schema version."},
    )
    validator_version: str = field(
        default="",
        metadata={"doc": "Output validator compatibility version, when applicable."},
    )
    execution_identity: str = field(
        default="",
        metadata={"doc": "Canonical SHA-256 identity of all execution fields."},
    )


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
    dependency_manifest: PromptDependencyManifest | None = field(
        default=None,
        metadata={"doc": "Complete content-addressed dependency manifest."},
    )
    prompt_content_hash: str = field(
        default="",
        metadata={"doc": "Canonical identity for all prompt-content dependencies."},
    )


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
        metadata={
            "doc": "SHA-256 hashes for prompt include text in composition order."
        },
    )
    schema_snippets: Dict[str, str] = field(
        default_factory=dict,
        metadata={
            "doc": "Generated source-schema prompt snippets keyed by variable name."
        },
    )
    schema_snippet_sources: Dict[str, str] = field(
        default_factory=dict,
        metadata={"doc": "Source schema references used to generate prompt snippets."},
    )
    schema_snippet_paths: Dict[str, str] = field(
        default_factory=dict,
        metadata={"doc": "Canonical schema dependency path keyed by snippet variable."},
    )
    schema_snippet_sha256s: Dict[str, str] = field(
        default_factory=dict,
        metadata={"doc": "Schema-file SHA-256 keyed by snippet variable."},
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
    prompt_content_hash: str = field(
        default="",
        metadata={"doc": "Canonical identity of all prompt dependencies."},
    )


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
        metadata={
            "doc": "Legacy descriptive fixture temperature; not a runtime override."
        },
    )
    test_only_execution_override: bool = field(
        default=False,
        metadata={
            "doc": "Permit this fixture's model/temperature only in explicitly test-only validation."
        },
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
        metadata={"doc": "Resolved runtime or explicitly test-only temperature."},
    )
    execution_policy_hash: str = field(
        default="", metadata={"doc": "Resolved runtime policy identity."}
    )
    execution_policy_source: str = field(
        default="", metadata={"doc": "Resolved policy prefix or compatibility source."}
    )


@dataclass(frozen=True)
class PromptDryRunResponse:
    schema_version: str = field(
        metadata={"doc": "Prompt dry-run response schema version."}
    )
    results: list[PromptDryRunResult] = field(
        metadata={"doc": "Validated prompt dry-run results for each namespace."}
    )
