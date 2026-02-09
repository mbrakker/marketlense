from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class PromptLoadRequest:
    schema_version: str = field(metadata={"doc": "Prompt load request schema version."})
    namespace: str = field(metadata={"doc": "Prompt namespace under src/prompts."})
    reload_if_changed: bool = field(default=False, metadata={"doc": "Force reload from disk if prompt files changed."})
    force_reload: bool = field(default=False, metadata={"doc": "Bypass cache and reload prompts from disk."})


@dataclass(frozen=True)
class PromptRenderRequest:
    schema_version: str = field(metadata={"doc": "Prompt render request schema version."})
    template: "PromptTemplate" = field(metadata={"doc": "Prompt template to render."})
    variables: Dict[str, Any] = field(metadata={"doc": "Variables to render into the prompt template."})


@dataclass(frozen=True)
class PromptRenderResponse:
    schema_version: str = field(metadata={"doc": "Prompt render response schema version."})
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


@dataclass(frozen=True)
class PromptNamespaceListRequest:
    schema_version: str = field(metadata={"doc": "Prompt namespace list request schema version."})
    reload_if_changed: bool = field(default=True, metadata={"doc": "Reload namespaces when on-disk prompt files change."})
    force_reload: bool = field(default=False, metadata={"doc": "Bypass in-memory cache for namespace prompt loading."})


@dataclass(frozen=True)
class PromptNamespaceSummary:
    schema_version: str = field(metadata={"doc": "Prompt namespace summary schema version."})
    namespace: str = field(metadata={"doc": "Prompt namespace path under src/prompts."})
    system_path: str = field(metadata={"doc": "Filesystem path to system.yaml."})
    user_path: str = field(metadata={"doc": "Filesystem path to user.yaml."})
    system_sha256: str = field(metadata={"doc": "SHA-256 hash of system prompt text."})
    user_sha256: str = field(metadata={"doc": "SHA-256 hash of user prompt text."})


@dataclass(frozen=True)
class PromptNamespaceListResponse:
    schema_version: str = field(metadata={"doc": "Prompt namespace list response schema version."})
    namespaces: list[PromptNamespaceSummary] = field(metadata={"doc": "Discovered prompt namespaces with hashes."})
