from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class PromptLoadRequest:
    schema_version: str = field(metadata={"doc": "Prompt load request schema version."})
    namespace: str = field(metadata={"doc": "Prompt namespace under src/prompts."})


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
