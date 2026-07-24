from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence


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


def build_list_pack_empty_payload(*, root_key: str, reason: str) -> dict[str, object]:
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


def _extract_wrapped_pack_payload(
    payload: object, *, root_key: str
) -> tuple[object, dict[str, object] | None]:
    cache_meta = None
    source = payload
    if isinstance(payload, dict):
        cache_meta = (
            payload.get("_cache") if isinstance(payload.get("_cache"), dict) else None
        )
        wrapped = payload.get(root_key)
        if wrapped is None:
            wrapped = payload.get("evidence_pack")
        if wrapped is None:
            wrapped = payload.get("evidencePack")
        if wrapped is not None:
            source = wrapped
    return source, cache_meta


def build_list_pack_strategy(
    *,
    pack_name: str,
    prompt_namespace_suffix: str,
    schema_name: str,
    root_key: str,
    source_aliases: Sequence[str] = (),
    normalize_items: Callable[[object], Sequence[object]],
) -> EvidencePackStrategy:
    def build_empty_payload(reason: str) -> dict[str, object]:
        return build_list_pack_empty_payload(root_key=root_key, reason=reason)

    def normalize_payload(
        payload: object, report_id: str, report_name: str
    ) -> PackNormalizationResult:
        del report_id, report_name
        source, cache_meta = _extract_wrapped_pack_payload(payload, root_key=root_key)
        root = source if isinstance(source, dict) else {}
        normalized = build_empty_payload("")
        if isinstance(root, dict):
            normalized["not_found_reason"] = str(
                root.get("not_found_reason") or ""
            ).strip()
        raw_value = root.get(root_key) if isinstance(source, dict) else source
        if raw_value is None:
            for alias in source_aliases:
                raw_value = root.get(alias)
                if raw_value is not None:
                    break
        normalized[root_key] = list(normalize_items(raw_value))
        if cache_meta:
            normalized["_cache"] = cache_meta
        return PackNormalizationResult(
            payload=normalized, changed=normalized != payload
        )

    return EvidencePackStrategy(
        pack_name=pack_name,
        prompt_namespace_suffix=prompt_namespace_suffix,
        schema_name=schema_name,
        normalize_payload=normalize_payload,
        empty_payload=build_empty_payload,
    )


def build_scalar_pack_strategy(
    *,
    pack_name: str,
    prompt_namespace_suffix: str,
    schema_name: str,
    root_key: str,
    default_value: object,
    source_aliases: Sequence[str] = (),
    normalize_value: Callable[[object], object],
) -> EvidencePackStrategy:
    def build_empty_payload(reason: str) -> dict[str, object]:
        return build_scalar_pack_empty_payload(
            root_key=root_key, default_value=default_value, reason=reason
        )

    def normalize_payload(
        payload: object, report_id: str, report_name: str
    ) -> PackNormalizationResult:
        del report_id, report_name
        source, cache_meta = _extract_wrapped_pack_payload(payload, root_key=root_key)
        root = source if isinstance(source, dict) else {}
        normalized = build_empty_payload("")
        if isinstance(root, dict):
            normalized["not_found_reason"] = str(
                root.get("not_found_reason") or ""
            ).strip()
        raw_value = root.get(root_key) if isinstance(source, dict) else source
        if raw_value is None:
            for alias in source_aliases:
                raw_value = root.get(alias)
                if raw_value is not None:
                    break
        normalized[root_key] = normalize_value(raw_value)
        if cache_meta:
            normalized["_cache"] = cache_meta
        return PackNormalizationResult(
            payload=normalized, changed=normalized != payload
        )

    return EvidencePackStrategy(
        pack_name=pack_name,
        prompt_namespace_suffix=prompt_namespace_suffix,
        schema_name=schema_name,
        normalize_payload=normalize_payload,
        empty_payload=build_empty_payload,
    )
