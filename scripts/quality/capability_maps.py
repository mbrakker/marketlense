from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MAP_PATH = Path("docs/quality/capability_maps.json")


def build_capability_maps() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "external_systems": {
            "browser": {
                "canonical_service": "src/services/browser_report_download_service.py",
                "private_roots": ["src/services/_browser_report_download/"],
            },
            "drive": {"canonical_service": "src/services/drive_service.py"},
            "mailbox": {
                "canonical_service": "src/services/mailbox_acquisition_service.py"
            },
            "openai": {
                "canonical_service": "src/services/llm_service.py",
                "private_roots": ["src/services/_llm_service/"],
            },
            "wordpress": {"canonical_service": "src/services/wordpress_service.py"},
        },
        "workflows": {
            "mail_acquisition": {
                "orchestrator": "src/orchestrators/mail_report_acquisition_orchestrator.py",
                "generator": "src/generators/mail_report_acquisition_generator.py",
                "contracts": ["src/contracts/mailbox_acquisition.py"],
                "services": [
                    "src/services/mailbox_acquisition_service.py",
                    "src/services/state_service.py",
                    "src/services/report_store_service.py",
                ],
            },
            "report_download": {
                "orchestrator": "src/orchestrators/report_download_orchestrator.py",
                "contracts": ["src/contracts/browser_download.py"],
                "services": [
                    "src/services/browser_report_download_service.py",
                    "src/services/report_store_service.py",
                ],
            },
            "report_generation": {
                "orchestrator": "src/orchestrators/report_pipeline_orchestrator.py",
                "generator": "src/generators/artifact_generator.py",
                "contracts": [
                    "src/contracts/report_generation.py",
                    "src/contracts/report_artifacts.py",
                ],
            },
        },
        "artifacts": {
            "report_artifacts": {
                "schema": "src/schemas/artifacts.schema.json",
                "generator": "src/generators/artifact_generator.py",
                "validator": "src/services/schema_validator_service.py",
                "prompt_root": "src/prompts/report_vs/artifacts/",
            }
        },
        "state_tables": {
            "mail_delivery_requests": "src/services/_state_service/mail_delivery.py",
            "mailbox_candidate_rejections": "src/services/_state_service/mail_delivery.py",
            "workflow_control_observations": "src/services/_state_service/workflow_control.py",
        },
        "side_effects": {
            "browser_identity_updates": {
                "owner": "report_download_orchestrator",
                "idempotency_scope": "browser_identity_config",
            },
            "drive_uploads": {
                "owner": "report_download_orchestrator",
                "idempotency_scope": "drive_archive_upload",
            },
            "mail_delivery_requests": {
                "owner": "report_download_orchestrator",
                "idempotency_scope": "mail_delivery_request",
            },
            "mailbox_candidate_rejections": {
                "owner": "mail_report_acquisition_orchestrator",
                "idempotency_scope": "request_id/provider_message_id/link_host/reason_code",
            },
            "publisher_route_history": {
                "owner": "report_download_orchestrator",
                "idempotency_scope": "publisher_route_history",
            },
            "wordpress_posts": {
                "owner": "publish_orchestrator",
                "idempotency_scope": "wordpress_publish",
            },
        },
        "failure_codes": {
            "mail_report_not_arrived_yet": "docs/ops/top_failure_runbooks.md",
            "openai_chat_failed": "docs/ops/top_failure_runbooks.md",
            "public_metadata_governance_blocked": "README.md",
        },
        "smoke_suites": {
            "autonomous_happy_path": {
                "command": "python scripts/quality/autonomous_happy_path_smoke.py",
                "covers": [
                    "mail_delivery_requests",
                    "mailbox_attachment_acquisition",
                    "publisher_route_history",
                ],
            }
        },
    }


def diff_capability_maps(
    *, expected: dict[str, Any], actual: dict[str, Any]
) -> list[str]:
    missing: list[str] = []

    def walk(prefix: str, left: Any, right: Any) -> None:
        if isinstance(left, dict):
            if not isinstance(right, dict):
                missing.append(f"{prefix} missing")
                return
            for key in sorted(left):
                child_prefix = f"{prefix}.{key}" if prefix else str(key)
                if key not in right:
                    missing.append(f"{child_prefix} missing")
                else:
                    walk(child_prefix, left[key], right[key])

    walk("", expected, actual)
    return missing


def main() -> int:
    payload = build_capability_maps()
    MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    MAP_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
