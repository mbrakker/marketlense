from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOCPACK_ROOT = ROOT / "tests" / "fixtures" / "docpacks" / "golden"


def migrate_artifact_payload(payload: dict[str, Any]) -> bool:
    """Add current schema fields using only retained, evidence-linked text."""
    changed = False
    if "editorial_plan" not in payload:
        thesis = _thesis(payload)
        themes = _theme_candidates(payload)
        if not thesis or len(themes) < 2:
            raise ValueError(
                "Cannot derive an editorial plan without a thesis and two "
                "evidence-linked source statements."
            )
        payload["editorial_plan"] = {
            "report_thesis": thesis,
            "themes": [
                {
                    "theme": theme,
                    "priority": index,
                    "evidence_ids": [evidence_id],
                }
                for index, (theme, evidence_id) in enumerate(themes[:2], start=1)
            ],
        }
        changed = True

    for key in ("insights_candidates", "insights_final"):
        insights = payload.get(key)
        if not isinstance(insights, list):
            continue
        for insight in insights:
            if not isinstance(insight, dict):
                continue
            metric = insight.get("metric")
            text = _text(insight.get("text"))
            if (
                isinstance(metric, dict)
                and _text(metric.get("value"))
                and not _text(metric.get("label"))
                and text
            ):
                metric["label"] = text
                changed = True
    return changed


def _thesis(payload: dict[str, Any]) -> str:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return ""
    return _text(summary.get("tldr")) or _text(summary.get("executive_summary"))


def _theme_candidates(payload: dict[str, Any]) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    for key in ("insights_final", "insights_candidates", "quotes_final"):
        for item in payload.get(key) or []:
            if isinstance(item, dict):
                _append_candidate(
                    candidates,
                    text=_text(item.get("text")),
                    evidence_id=_text(item.get("evidence_id")),
                )
    summary = payload.get("summary")
    if isinstance(summary, dict):
        for claim in summary.get("claim_evidence_map") or []:
            if isinstance(claim, dict):
                _append_candidate(
                    candidates,
                    text=_text(claim.get("claim")),
                    evidence_id=_text(claim.get("evidence_id")),
                )
    return candidates


def _append_candidate(
    candidates: list[tuple[str, str]], *, text: str, evidence_id: str
) -> None:
    if not text or not evidence_id:
        return
    if any(existing_text == text for existing_text, _ in candidates):
        return
    candidates.append((text, evidence_id))


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate golden artifact fixtures to the current artifact schema."
    )
    parser.add_argument(
        "--docpack-root",
        type=Path,
        default=DEFAULT_DOCPACK_ROOT,
        help="Root containing <report>/report_analysis/artifacts.json fixtures.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if any fixture needs migration without modifying it.",
    )
    args = parser.parse_args()
    changed_paths: list[Path] = []
    for path in sorted(args.docpack_root.glob("*/report_analysis/artifacts.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Artifact fixture must contain an object: {path}")
        if not migrate_artifact_payload(payload):
            continue
        changed_paths.append(path)
        if not args.check:
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    if args.check and changed_paths:
        raise SystemExit(
            "Golden artifact fixtures require migration:\n"
            + "\n".join(str(path) for path in changed_paths)
        )
    print(f"Migrated golden artifact fixtures: {len(changed_paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
