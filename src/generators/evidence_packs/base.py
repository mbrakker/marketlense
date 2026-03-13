from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class PackNormalizationResult:
    payload: dict[str, object] = field(
        metadata={"doc": "Normalized payload ready for schema validation/storage."}
    )
    changed: bool = field(
        metadata={"doc": "Whether normalization changed the source payload."}
    )
    metadata: dict[str, object] = field(
        default_factory=dict,
        metadata={"doc": "Strategy-specific normalization diagnostics."},
    )


@dataclass(frozen=True)
class EvidencePackStrategy:
    pack_name: str = field(metadata={"doc": "Stable evidence pack name."})
    prompt_namespace_suffix: str = field(
        metadata={"doc": "Prompt namespace suffix under report_vs/."}
    )
    schema_name: str = field(metadata={"doc": "Schema name used for validation."})
    normalize_payload: Callable[[object, str, str], PackNormalizationResult] = field(
        metadata={"doc": "Pack-specific payload normalization function."}
    )
    empty_payload: Callable[[str], dict[str, object]] = field(
        metadata={"doc": "Factory for a typed empty payload with a not-found reason."}
    )


def build_list_pack_empty_payload(
    *, root_key: str, reason: str
) -> dict[str, object]:
    return {"schema_version": "1.0", "not_found_reason": reason, root_key: []}


def build_scalar_pack_empty_payload(
    *, root_key: str, default_value: object, reason: str
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "not_found_reason": reason,
        root_key: default_value,
    }


def unchanged_result(payload: dict[str, object]) -> PackNormalizationResult:
    return PackNormalizationResult(payload=payload, changed=False)
