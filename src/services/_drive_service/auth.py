from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

from src.services import drive_service as boundary

from .shared import *  # noqa: F401,F403
from .shared import (
    DRIVE_BOUNDARY_EXCEPTIONS,
    DRIVE_HTTP_TIMEOUT_SECONDS,
    DRIVE_SCOPES,
    _DRIVE_CLIENTS,
    _DRIVE_CLIENTS_LOCK,
    _DriveCredentialResolution,
    AppError,
    AuthorizedHttp,
    AuthorizedUserCredentials,
    Credentials,
    DriveOAuthAuthorizeRequest,
    DriveOAuthAuthorizeResponse,
    GoogleAuthRequest,
    Path,
    RefreshError,
    RunContext,
    httplib2,
    json,
    logger,
    log_event,
)


def _persist_authorized_user_credentials(credentials, token_path: str) -> None:
    path = Path(token_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(credentials.to_json(), encoding="utf-8")


def _load_authorized_user_credentials(*, token_path: str, ctx: RunContext):
    return _resolve_authorized_user_credentials(
        token_path=token_path,
        ctx=ctx,
    ).credentials


def _resolve_authorized_user_credentials(
    *, token_path: str, ctx: RunContext
) -> _DriveCredentialResolution:
    if not token_path:
        raise AppError(
            code="drive_oauth_token_path_missing",
            message="OAuth token path is required when Drive auth mode is oauth_user",
            retryable=False,
        )
    token_file = Path(token_path)
    if not token_file.exists():
        raise AppError(
            code="drive_oauth_token_missing",
            message="OAuth token JSON was not found; run drive-oauth-login first",
            retryable=False,
            context={"oauth_token_path": token_path},
        )
    try:
        credentials = AuthorizedUserCredentials.from_authorized_user_file(
            str(token_file), DRIVE_SCOPES
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise AppError(
            code="drive_oauth_token_invalid",
            message="OAuth token JSON is invalid",
            cause=exc,
            retryable=False,
            context={"oauth_token_path": token_path},
        ) from exc
    if credentials.valid:
        return _DriveCredentialResolution(
            credentials=credentials,
            refreshed=False,
            credential_path=token_path,
        )
    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(GoogleAuthRequest())
        except RefreshError as exc:
            raise AppError(
                code="drive_oauth_refresh_failed",
                message="OAuth token refresh failed",
                cause=exc,
                retryable=False,
                context={"oauth_token_path": token_path},
            ) from exc
        _persist_authorized_user_credentials(credentials, token_path)
        logger.info(
            log_event(
                ctx,
                role="service",
                event="drive_oauth_token_refreshed",
                module=logger.name,
                fields={"oauth_token_path": token_path},
            )
        )
        boundary._invalidate_drive_client_cache(
            auth_mode="oauth_user", credential_path=token_path
        )
        return _DriveCredentialResolution(
            credentials=credentials,
            refreshed=True,
            credential_path=token_path,
        )
    raise AppError(
        code="drive_oauth_refresh_token_missing",
        message="OAuth token is not valid and cannot be refreshed; run drive-oauth-login again",
        retryable=False,
        context={"oauth_token_path": token_path},
    )


def _resolve_drive_credentials(
    *,
    auth_mode: str,
    service_account_path: str,
    oauth_token_path: str | None,
    ctx: RunContext,
) -> _DriveCredentialResolution:
    if auth_mode == "service_account":
        try:
            creds = Credentials.from_service_account_file(
                service_account_path, scopes=DRIVE_SCOPES
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise AppError(
                code="drive_service_account_invalid",
                message="Service account credentials could not be loaded",
                cause=exc,
                retryable=False,
                context={"service_account_path": service_account_path},
            ) from exc
        return _DriveCredentialResolution(
            credentials=creds,
            refreshed=False,
            credential_path=service_account_path,
        )
    return _resolve_authorized_user_credentials(
        token_path=str(oauth_token_path or ""),
        ctx=ctx,
    )


def _build_drive_client(
    *,
    auth_mode: str,
    service_account_path: str,
    oauth_token_path: str | None,
    ctx: RunContext,
):
    resolution = _resolve_drive_credentials(
        auth_mode=auth_mode,
        service_account_path=service_account_path,
        oauth_token_path=oauth_token_path,
        ctx=ctx,
    )
    return boundary.build(
        "drive",
        "v3",
        http=_build_authorized_drive_http(resolution.credentials),
        cache_discovery=False,
        static_discovery=True,
    )


def _build_authorized_drive_http(credentials) -> AuthorizedHttp:
    return AuthorizedHttp(
        credentials,
        http=httplib2.Http(timeout=DRIVE_HTTP_TIMEOUT_SECONDS),
    )


def authorize_oauth_user(
    request: DriveOAuthAuthorizeRequest, ctx: RunContext
) -> DriveOAuthAuthorizeResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="drive_oauth_authorize_start",
            module=logger.name,
            fields={
                "client_secret_path": request.client_secret_path,
                "token_output_path": request.token_output_path,
                "open_browser": request.open_browser,
                "port": request.port,
            },
        )
    )
    client_secret_path = str(request.client_secret_path or "").strip()
    token_output_path = str(request.token_output_path or "").strip()
    if not client_secret_path:
        raise AppError(
            code="drive_oauth_client_path_missing",
            message="OAuth client JSON path is required",
            retryable=False,
        )
    if not token_output_path:
        raise AppError(
            code="drive_oauth_token_path_missing",
            message="OAuth token output path is required",
            retryable=False,
        )
    if not Path(client_secret_path).exists():
        raise AppError(
            code="drive_oauth_client_path_invalid",
            message="OAuth client JSON path does not exist",
            retryable=False,
            context={"client_secret_path": client_secret_path},
        )
    if boundary.InstalledAppFlow is None:
        raise AppError(
            code="drive_oauth_dependency_missing",
            message="google-auth-oauthlib is required for drive-oauth-login",
            retryable=False,
        )
    try:
        flow = boundary.InstalledAppFlow.from_client_secrets_file(
            client_secret_path, DRIVE_SCOPES
        )
        credentials = flow.run_local_server(
            port=int(request.port),
            open_browser=bool(request.open_browser),
        )
    except DRIVE_BOUNDARY_EXCEPTIONS as exc:
        raise AppError(
            code="drive_oauth_authorize_failed",
            message="Drive OAuth authorization failed",
            cause=exc,
            retryable=False,
            context={"client_secret_path": client_secret_path},
        ) from exc
    _persist_authorized_user_credentials(credentials, token_output_path)
    with _DRIVE_CLIENTS_LOCK:
        for cache_key in list(_DRIVE_CLIENTS.keys()):
            if cache_key[0] == "oauth_user" and cache_key[1] == token_output_path:
                _DRIVE_CLIENTS.pop(cache_key, None)
    response = DriveOAuthAuthorizeResponse(
        schema_version="1.0",
        token_output_path=token_output_path,
        scopes=list(getattr(credentials, "scopes", DRIVE_SCOPES) or DRIVE_SCOPES),
        refresh_token_present=bool(getattr(credentials, "refresh_token", None)),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="drive_oauth_authorize_complete",
            module=logger.name,
            fields={
                "token_output_path": response.token_output_path,
                "scope_count": len(response.scopes),
                "refresh_token_present": response.refresh_token_present,
            },
        )
    )
    return response


__all__ = [
    name
    for name in globals()
    if not name.startswith("__") and name not in {"annotations"}
]
