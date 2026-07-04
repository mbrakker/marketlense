from __future__ import annotations

from src.contracts.mailbox_acquisition import MailboxAcquisitionSettings
from src.services._config_service.common import *


def load_mailbox_acquisition_settings(
    request: ConfigLoadRequest, ctx: RunContext
) -> MailboxAcquisitionSettings:
    load_dotenv(find_dotenv(filename=".env", usecwd=True))
    config_path = _resolve_bootstrap_config_path(request.path)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="mailbox_acquisition_config_load_start",
            module=logger.name,
            fields={"path": str(config_path)},
        )
    )
    data = _load_config(str(config_path))
    runtime_base_path = _resolve_runtime_base_path(config_path)
    mailbox_cfg = data.get("mailbox_acquisition", {}) or {}
    paths = data.get("paths", {}) or {}
    output_root = (
        mailbox_cfg.get("output_dir")
        or _env_value("MAILBOX_OUTPUT_DIR")
        or str(Path(paths.get("output_dir") or "./out") / "mailbox_acquisition")
    )
    settings = MailboxAcquisitionSettings(
        schema_version=str(data.get("schema_version", "1.0")),
        provider=str(
            mailbox_cfg.get("provider") or _env_value("MAILBOX_PROVIDER") or "imap"
        )
        .strip()
        .lower(),
        output_dir=_resolve_optional_path(output_root, base_path=runtime_base_path),
        search_window_minutes=max(
            _to_int(
                mailbox_cfg.get("search_window_minutes")
                if not _is_missing(mailbox_cfg.get("search_window_minutes"))
                else _env_value("MAILBOX_SEARCH_WINDOW_MINUTES"),
                120,
            ),
            1,
        ),
        max_results=max(
            _to_int(
                mailbox_cfg.get("max_results")
                if not _is_missing(mailbox_cfg.get("max_results"))
                else _env_value("MAILBOX_MAX_RESULTS"),
                10,
            ),
            1,
        ),
        poll_timeout_seconds=max(
            _to_float(
                mailbox_cfg.get("poll_timeout_seconds")
                if not _is_missing(mailbox_cfg.get("poll_timeout_seconds"))
                else _env_value("MAILBOX_POLL_TIMEOUT_SECONDS"),
                900.0,
            ),
            0.0,
        ),
        poll_interval_seconds=max(
            _to_float(
                mailbox_cfg.get("poll_interval_seconds")
                if not _is_missing(mailbox_cfg.get("poll_interval_seconds"))
                else _env_value("MAILBOX_POLL_INTERVAL_SECONDS"),
                60.0,
            ),
            1.0,
        ),
        gmail_oauth_client_path=_resolve_optional_path(
            mailbox_cfg.get("gmail_oauth_client_path")
            or _env_value("GMAIL_OAUTH_CLIENT_PATH"),
            base_path=runtime_base_path,
        ),
        gmail_oauth_token_path=_resolve_optional_path(
            mailbox_cfg.get("gmail_oauth_token_path")
            or _env_value("GMAIL_OAUTH_TOKEN_PATH"),
            base_path=runtime_base_path,
        ),
        gmail_user_id=str(
            mailbox_cfg.get("gmail_user_id") or _env_value("GMAIL_USER_ID") or "me"
        ).strip(),
        imap_host=str(mailbox_cfg.get("imap_host") or _env_value("IMAP_HOST")).strip(),
        imap_port=max(
            _to_int(mailbox_cfg.get("imap_port") or _env_value("IMAP_PORT"), 993),
            1,
        ),
        imap_user=str(mailbox_cfg.get("imap_user") or _env_value("IMAP_USER")).strip(),
        imap_password=str(_env_value("IMAP_PASS")).strip(),
        imap_mailbox=str(
            mailbox_cfg.get("imap_mailbox") or _env_value("IMAP_MAILBOX") or "INBOX"
        ).strip(),
    )
    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="mailbox_acquisition_config_load_complete",
            module=logger.name,
            fields={
                "provider": settings.provider,
                "output_dir": settings.output_dir,
                "search_window_minutes": settings.search_window_minutes,
                "max_results": settings.max_results,
                "poll_timeout_seconds": settings.poll_timeout_seconds,
                "poll_interval_seconds": settings.poll_interval_seconds,
                "has_gmail_oauth_client_path": bool(settings.gmail_oauth_client_path),
                "has_gmail_oauth_token_path": bool(settings.gmail_oauth_token_path),
                "gmail_user_id": settings.gmail_user_id,
                "has_imap_host": bool(settings.imap_host),
                "has_imap_user": bool(settings.imap_user),
                "has_imap_password": bool(settings.imap_password),
                "imap_mailbox": settings.imap_mailbox,
            },
        )
    )
    return settings


__all__ = ["load_mailbox_acquisition_settings"]
