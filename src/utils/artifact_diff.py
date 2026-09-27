"""Deterministic changed-path reporting for retained artifact payloads."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from src.contracts.soft_copy_claim_provenance import soft_copy_material_sentences

_SOFT_COPY_DIFF_PATHS = frozenset(
    {
        "summary.tldr",
        "summary.card_tldr_compact",
        "summary.executive_summary",
        "expert_comment",
        "linkedin_post",
    }
)


def artifact_diff_paths(before: Any, after: Any, path: str = "") -> set[str]:
    """Return changed leaf paths, using stable IDs and the canonical sentence grid."""

    if before == after:
        return set()
    if isinstance(before, dict) and isinstance(after, dict):
        changed: set[str] = set()
        for key in sorted(set(before) | set(after)):
            child = f"{path}.{key}" if path else str(key)
            if key not in before or key not in after:
                changed.add(child)
            else:
                changed.update(artifact_diff_paths(before[key], after[key], child))
        return changed
    if isinstance(before, list) and isinstance(after, list):
        before_ids = _stable_list_ids(before)
        after_ids = _stable_list_ids(after)
        if before_ids is not None and after_ids is not None:
            if set(before_ids) == set(after_ids) and before_ids != after_ids:
                return {path or "$"}
            before_by_id = dict(zip(before_ids, before))
            after_by_id = dict(zip(after_ids, after))
            changed = {
                changed_path
                for identity in before_ids
                if identity in after_by_id
                for changed_path in artifact_diff_paths(
                    before_by_id[identity],
                    after_by_id[identity],
                    f"{path}[item={identity}]",
                )
            }
            changed.update(
                f"{path}[item={identity}]"
                for identity in set(before_ids) ^ set(after_ids)
            )
            return changed
        changed = set()
        for index in range(max(len(before), len(after))):
            child = f"{path}[{index}]"
            if index >= len(before) or index >= len(after):
                changed.add(child)
            else:
                changed.update(artifact_diff_paths(before[index], after[index], child))
        return changed
    if (
        path in _SOFT_COPY_DIFF_PATHS
        and isinstance(before, str)
        and isinstance(after, str)
    ):
        return _soft_copy_changed_claim_paths(path, before, after)
    return {path} if path else {"$"}


def _stable_list_ids(values: list[Any]) -> list[str] | None:
    identities: list[str] = []
    for value in values:
        if not isinstance(value, dict):
            return None
        identity = next(
            (
                str(value.get(key) or "").strip()
                for key in ("id", "insight_id", "key_figure_id", "claim_id")
                if str(value.get(key) or "").strip()
            ),
            "",
        )
        if not identity:
            return None
        identities.append(identity)
    return identities if len(set(identities)) == len(identities) else None


def _soft_copy_changed_claim_paths(path: str, before: str, after: str) -> set[str]:
    before_sentences = soft_copy_material_sentences(before)
    after_sentences = soft_copy_material_sentences(after)
    matcher = SequenceMatcher(a=before_sentences, b=after_sentences, autojunk=False)
    changed: set[str] = set()
    for operation, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if operation == "equal":
            continue
        changed.update(
            f"{path}[claim_index={index}]" for index in range(old_start, old_end)
        )
        changed.update(
            f"{path}[claim_index={index}]" for index in range(new_start, new_end)
        )
    return changed or {path}
