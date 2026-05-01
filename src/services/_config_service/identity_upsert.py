from __future__ import annotations

from src.services._config_service.common import *

def upsert_browser_download_identity_fields(
    request: BrowserDownloadIdentityFieldUpsertRequest,
    ctx: RunContext,
) -> BrowserDownloadIdentityFieldUpsertResponse:
    identity_path = Path(request.path).expanduser().resolve()
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_download_identity_upsert_start",
            module=logger.name,
            fields={
                "path": str(identity_path),
                "encountered_form_fields": request.encountered_form_fields,
            },
        )
    )
    identity_profile = _load_browser_download_identity(
        str(identity_path),
        load_yaml_mapping=_load_yaml_mapping,
        is_missing=_is_missing,
    )
    added_fields = _plan_browser_download_identity_field_upserts(
        identity_profile,
        encountered_form_fields=request.encountered_form_fields,
    )
    if added_fields:
        payload = _serialize_browser_download_identity(
            identity_profile,
            extra_fields=added_fields,
        )
        identity_path.parent.mkdir(parents=True, exist_ok=True)
        identity_path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
            encoding="utf-8",
        )

    response = BrowserDownloadIdentityFieldUpsertResponse(
        schema_version="1.0",
        path=str(identity_path),
        added_field_keys=[field.key for field in added_fields],
        total_fields=len(identity_profile.fields) + len(added_fields),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_download_identity_upsert_complete",
            module=logger.name,
            fields=asdict(response),
        )
    )
    return response

__all__ = [name for name in globals() if not name.startswith("__")]
