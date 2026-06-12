from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

from src.services import drive_service as boundary

from .shared import *  # noqa: F401,F403
from .auth import _build_drive_client, _resolve_drive_credentials


def _invalidate_drive_client_cache(*, auth_mode: str, credential_path: str) -> int:
    with boundary._DRIVE_CLIENTS_LOCK:
        removed = 0
        for cache_key in list(boundary._DRIVE_CLIENTS.keys()):
            if cache_key[0] != auth_mode or cache_key[1] != credential_path:
                continue
            boundary._DRIVE_CLIENTS.pop(cache_key, None)
            removed += 1
        return removed


def _prune_drive_client_cache(now: float) -> int:
    removed = 0
    for cache_key, entry in list(boundary._DRIVE_CLIENTS.items()):
        if entry.expires_at > now:
            continue
        boundary._DRIVE_CLIENTS.pop(cache_key, None)
        removed += 1
    return removed


def _evict_drive_client_cache(limit: int) -> int:
    evicted = 0
    while len(boundary._DRIVE_CLIENTS) > max(0, int(limit)):
        oldest_key = min(
            boundary._DRIVE_CLIENTS.items(),
            key=lambda item: (item[1].last_access_at, item[0]),
        )[0]
        boundary._DRIVE_CLIENTS.pop(oldest_key, None)
        evicted += 1
    return evicted


def _get_drive_client(
    *,
    auth_mode: str,
    service_account_path: str,
    oauth_token_path: str | None,
    ctx: RunContext,
):
    thread_id = threading.get_ident()
    credential_path = _principal_path(
        auth_mode=auth_mode,
        service_account_path=service_account_path,
        oauth_token_path=oauth_token_path,
    )
    cache_key = (auth_mode, credential_path, thread_id)
    with boundary._DRIVE_CLIENTS_LOCK:
        now = _now_monotonic_seconds()
        expired = _prune_drive_client_cache(now)
        cached = boundary._DRIVE_CLIENTS.get(cache_key)
        if cached is not None and cached.expires_at > now:
            cached.last_access_at = now
            cached.expires_at = now + boundary.DRIVE_CLIENT_CACHE_TTL_SECONDS
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="drive_client_reuse",
                    module=logger.name,
                    fields={
                        "auth_mode": auth_mode,
                        "credential_path": credential_path,
                        "thread_id": thread_id,
                        "expired_evictions": expired,
                        "cache_size": len(boundary._DRIVE_CLIENTS),
                    },
                )
            )
            return cached.client

    logger.info(
        log_event(
            ctx,
            role="service",
            event="drive_client_build_start",
            module=logger.name,
            fields={
                "auth_mode": auth_mode,
                "credential_path": credential_path,
                "thread_id": thread_id,
                "expired_evictions": expired,
            },
        )
    )
    client = _build_drive_client(
        auth_mode=auth_mode,
        service_account_path=service_account_path,
        oauth_token_path=oauth_token_path,
        ctx=ctx,
    )

    with boundary._DRIVE_CLIENTS_LOCK:
        now = _now_monotonic_seconds()
        expired_after_build = _prune_drive_client_cache(now)
        cached = boundary._DRIVE_CLIENTS.get(cache_key)
        if cached is not None and cached.expires_at > now:
            cached.last_access_at = now
            cached.expires_at = now + boundary.DRIVE_CLIENT_CACHE_TTL_SECONDS
            cache_size = len(boundary._DRIVE_CLIENTS)
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="drive_client_reuse_after_build",
                    module=logger.name,
                    fields={
                        "auth_mode": auth_mode,
                        "credential_path": credential_path,
                        "thread_id": thread_id,
                        "expired_evictions": expired + expired_after_build,
                        "cache_size": cache_size,
                    },
                )
            )
            return cached.client
        boundary._DRIVE_CLIENTS[cache_key] = _DriveClientCacheEntry(
            client=client,
            expires_at=now + boundary.DRIVE_CLIENT_CACHE_TTL_SECONDS,
            last_access_at=now,
        )
        evicted = _evict_drive_client_cache(boundary.DRIVE_CLIENT_CACHE_MAX_ENTRIES)
        cache_size = len(boundary._DRIVE_CLIENTS)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="drive_client_created",
            module=logger.name,
            fields={
                "auth_mode": auth_mode,
                "credential_path": credential_path,
                "thread_id": thread_id,
                "expired_evictions": expired + expired_after_build,
                "max_entry_evictions": evicted,
                "cache_size": cache_size,
            },
        )
    )
    return client


__all__ = [
    name
    for name in globals()
    if not name.startswith("__") and name not in {"annotations"}
]
