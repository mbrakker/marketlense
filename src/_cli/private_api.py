from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

import typer
from rich.table import Table
from rich import box

from src.utils.errors import AppError
from src.contracts.browser_download import BrowserRoutePrivateApiPromotionRequest
from src.contracts.files import ReadTextRequest
from src.contracts.logging import LoggingSetupRequest
from src.services.browser_report_download_service import (
    promote_private_api_evidence_to_browser_playbook,
)
from src.services.file_service import read_text
from src.services.logging_service import setup_logging
from src.utils.logging import log_event, new_run_context

from src._cli.app import cli_app, console, logger
from src._cli.runtime import sync_cli_patch_points

_CLI_PATCH_POINTS = (
    "authorize_oauth_user",
    "build_ingest_settings",
    "console",
    "default_browser_doctor_verification_url",
    "default_ui_run_registry_path",
    "execute_ui_run",
    "get_ui_run_record",
    "load_browser_download_settings",
    "load_publish_settings",
    "load_publisher_inventory_settings",
    "load_settings",
    "promote_private_api_evidence_to_browser_playbook",
    "read_text",
    "replay_ui_run",
    "run_acquisition_audit",
    "run_browser_developer_diagnostics",
    "run_candidate_extraction",
    "run_cost_reporting",
    "run_cover_image_generation",
    "run_cross_report_analysis_orchestrator",
    "run_ingest",
    "run_publish",
    "run_publisher_inventory_discovery",
    "run_publisher_sync",
    "run_recategorize",
    "run_report_download",
    "run_update_wp_categories",
    "setup_logging",
    "write_ui_run_record",
    "write_ui_run_replay_manifest",
)


def _sync_cli_patch_points() -> None:
    sync_cli_patch_points(globals(), _CLI_PATCH_POINTS)


def _string_list_payload(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _int_list_payload(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    integers: list[int] = []
    for item in value:
        if isinstance(item, int):
            integers.append(item)
            continue
        text = str(item).strip()
        if text.isdigit():
            integers.append(int(text))
    return integers


def _required_int_payload(
    payload: dict[str, Any], *, field_name: str, request_json: str
) -> int:
    value = payload.get(field_name)
    if isinstance(value, int):
        return value
    text = str(value or "").strip()
    if text.isdigit():
        return int(text)
    raise AppError(
        code="browser_route_private_api_promotion_request_invalid",
        message=f"Private-API playbook promotion field {field_name} must be an integer.",
        retryable=False,
        severity="error",
        context={"request_json": request_json, "field": field_name},
    )


def _load_private_api_promotion_request(
    *, request_json: str, ctx
) -> BrowserRoutePrivateApiPromotionRequest:
    _sync_cli_patch_points()
    response = read_text(
        ReadTextRequest(schema_version="1.0", path=request_json),
        ctx,
    )
    try:
        payload = json.loads(response.content)
    except json.JSONDecodeError as exc:
        raise AppError(
            code="browser_route_private_api_promotion_request_json_invalid",
            message="Private-API playbook promotion request JSON is invalid.",
            cause=exc,
            retryable=False,
            context={"request_json": request_json},
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            code="browser_route_private_api_promotion_request_invalid",
            message="Private-API playbook promotion request must be a JSON object.",
            retryable=False,
            context={"request_json": request_json},
        )
    expected_status_codes = _int_list_payload(payload.get("expected_status_codes"))
    if not expected_status_codes:
        expected_status_codes = [200]
    return BrowserRoutePrivateApiPromotionRequest(
        schema_version=str(payload.get("schema_version") or "").strip(),
        playbook_dir=str(payload.get("playbook_dir") or "").strip(),
        source_url=str(payload.get("source_url") or "").strip(),
        route_family=str(payload.get("route_family") or "").strip(),
        route_kind=str(payload.get("route_kind") or "").strip(),
        endpoint_pattern=str(payload.get("endpoint_pattern") or "").strip(),
        method=str(payload.get("method") or "").strip(),
        request_shape_summary=str(payload.get("request_shape_summary") or "").strip(),
        response_pdf_url_json_pointer=str(
            payload.get("response_pdf_url_json_pointer") or ""
        ).strip(),
        validated_success_count=_required_int_payload(
            payload,
            field_name="validated_success_count",
            request_json=request_json,
        ),
        fallback_route_family=str(payload.get("fallback_route_family") or "").strip(),
        expected_status_codes=expected_status_codes,
        required_response_markers=_string_list_payload(
            payload.get("required_response_markers")
        ),
        evidence_labels=_string_list_payload(payload.get("evidence_labels")),
        observed_at=str(payload.get("observed_at") or "").strip(),
    )


@cli_app.command("promote-private-api-playbook")
def promote_private_api_playbook(
    request_json: str = typer.Option(
        ...,
        "--request-json",
        help=(
            "Path to a JSON BrowserRoutePrivateApiPromotionRequest produced from "
            "validated browser network evidence."
        ),
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print the promotion response as JSON.",
    ),
):
    _sync_cli_patch_points()
    ctx = new_run_context(task_id="cli_promote_private_api_playbook")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    request = _load_private_api_promotion_request(
        request_json=request_json,
        ctx=ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_private_api_playbook_promotion_start",
            module=logger.name,
            fields={
                "request_json": request_json,
                "source_url": request.source_url,
                "route_family": request.route_family,
                "route_kind": request.route_kind,
                "validated_success_count": request.validated_success_count,
                "endpoint_pattern": request.endpoint_pattern,
            },
        )
    )
    response = promote_private_api_evidence_to_browser_playbook(
        request=request,
        ctx=ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_private_api_playbook_promotion_complete",
            module=logger.name,
            fields={
                "playbook_id": response.playbook_id,
                "version": response.version,
                "path": response.path,
                "status": response.status,
                "review_diff_line_count": len(response.review_diff.splitlines()),
            },
        )
    )
    if json_output:
        console.print(json.dumps(asdict(response), ensure_ascii=False, indent=2))
    else:
        table = Table(title="Private API Playbook Promotion", box=box.SIMPLE_HEAVY)
        table.add_column("Field")
        table.add_column("Value")
        table.add_row("Playbook", f"{response.playbook_id}@{response.version}")
        table.add_row("Status", response.status)
        table.add_row("Path", response.path)
        table.add_row("Review diff lines", str(len(response.review_diff.splitlines())))
        console.print(table)
    console.print(
        f"[green]Done: promoted private API playbook {response.playbook_id}.[/green]"
    )
