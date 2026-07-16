from __future__ import annotations

import json
import logging
import shutil
import time
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from src.contracts.browser_download import (
    BrowserDownloadSessionReuseDecision,
    BrowserDownloadSessionReusePolicy,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.logging import (
    browser_session_reuse_log_fields,
)
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service.session_reuse")

_SESSION_REUSE_SCHEMA_VERSION = "1.0"
_SESSION_REUSE_INDEX_FILE = "session_key_index.json"
_SESSION_REUSE_LEDGER_FILE = "session_reuse_ledger.json"
_SESSION_REUSE_DIR_PREFIX = "browser-session-reuse"
_ALLOWED_REUSE_MODES = {"developer_canary", "same_publisher_batch"}
_MAX_TTL_SECONDS = 24 * 60 * 60.0


def disabled_browser_session_reuse_decision() -> BrowserDownloadSessionReuseDecision:
    return BrowserDownloadSessionReuseDecision(
        schema_version=_SESSION_REUSE_SCHEMA_VERSION,
        enabled=False,
        accepted=False,
        mode="disabled",
        session_key_hash="",
        publisher_scope="",
        profile_path="",
        profile_reused=False,
        ttl_seconds=0.0,
        expires_at_epoch_seconds=0.0,
        cleanup_removed_count=0,
        rejection_reason="disabled",
    )


def resolve_browser_session_reuse(
    *,
    policy: BrowserDownloadSessionReusePolicy,
    default_base_dir: Path,
    normalized_url: str,
    ctx: RunContext,
) -> BrowserDownloadSessionReuseDecision:
    normalized_policy = _normalize_policy(policy)
    if not normalized_policy.enabled:
        decision = disabled_browser_session_reuse_decision()
        _log_resolution(ctx=ctx, normalized_url=normalized_url, decision=decision)
        return decision
    base_dir = _resolve_base_dir(
        raw_base_dir=normalized_policy.base_dir,
        default_base_dir=default_base_dir,
    )
    cleanup_removed_count = (
        _cleanup_expired_session_dirs(base_dir)
        if normalized_policy.cleanup_expired
        else 0
    )
    mode = _normalize_mode(normalized_policy.mode)
    session_key = str(normalized_policy.session_key or "").strip()
    publisher_scope = _normalize_publisher_scope(normalized_policy.publisher_scope)
    rejection_reason = _reject_reason(
        mode=mode,
        session_key=session_key,
        publisher_scope=publisher_scope,
        ttl_seconds=float(normalized_policy.ttl_seconds),
    )
    key_hash = _hash_token(session_key)
    if not rejection_reason:
        rejection_reason = _cross_publisher_rejection_reason(
            base_dir=base_dir,
            key_hash=key_hash,
            publisher_scope=publisher_scope,
            allow_cross_publisher=bool(normalized_policy.allow_cross_publisher),
        )
    if rejection_reason:
        decision = BrowserDownloadSessionReuseDecision(
            schema_version=_SESSION_REUSE_SCHEMA_VERSION,
            enabled=True,
            accepted=False,
            mode=mode,
            session_key_hash=key_hash,
            publisher_scope=publisher_scope,
            profile_path="",
            profile_reused=False,
            ttl_seconds=_effective_ttl_seconds(normalized_policy.ttl_seconds),
            expires_at_epoch_seconds=0.0,
            cleanup_removed_count=cleanup_removed_count,
            rejection_reason=rejection_reason,
        )
        _log_resolution(ctx=ctx, normalized_url=normalized_url, decision=decision)
        return decision
    profile_dir = _profile_dir_for(
        base_dir=base_dir,
        mode=mode,
        key_hash=key_hash,
        publisher_scope=publisher_scope,
    )
    profile_reused = _is_fresh_profile(profile_dir)
    ttl_seconds = _effective_ttl_seconds(normalized_policy.ttl_seconds)
    expires_at = time.time() + ttl_seconds
    profile_dir.mkdir(parents=True, exist_ok=True)
    _write_session_ledger(
        profile_dir=profile_dir,
        mode=mode,
        key_hash=key_hash,
        publisher_scope=publisher_scope,
        ttl_seconds=ttl_seconds,
        expires_at=expires_at,
    )
    _write_key_index(
        base_dir=base_dir,
        key_hash=key_hash,
        mode=mode,
        publisher_scope=publisher_scope,
        profile_path=profile_dir,
        allow_cross_publisher=bool(normalized_policy.allow_cross_publisher),
    )
    decision = BrowserDownloadSessionReuseDecision(
        schema_version=_SESSION_REUSE_SCHEMA_VERSION,
        enabled=True,
        accepted=True,
        mode=mode,
        session_key_hash=key_hash,
        publisher_scope=publisher_scope,
        profile_path=str(profile_dir),
        profile_reused=profile_reused,
        ttl_seconds=ttl_seconds,
        expires_at_epoch_seconds=expires_at,
        cleanup_removed_count=cleanup_removed_count,
        rejection_reason="",
    )
    _log_resolution(ctx=ctx, normalized_url=normalized_url, decision=decision)
    return decision


def finalize_browser_session_reuse(
    *,
    decision: BrowserDownloadSessionReuseDecision,
    ctx: RunContext,
    normalized_url: str,
    verified_artifact_count: int = 0,
) -> None:
    if not decision.accepted or not decision.profile_path:
        return
    profile_dir = Path(decision.profile_path).resolve()
    ledger = _read_json(profile_dir / _SESSION_REUSE_LEDGER_FILE)
    ledger.update(
        {
            "last_used_at_epoch_seconds": time.time(),
            "last_normalized_url": normalized_url,
            "last_verified_artifact_count": int(max(0, verified_artifact_count)),
        }
    )
    _write_json(profile_dir / _SESSION_REUSE_LEDGER_FILE, ledger)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_session_reuse_finalized",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "session_key_hash": decision.session_key_hash,
                "publisher_scope": decision.publisher_scope,
                "profile_path": decision.profile_path,
                "profile_reused": decision.profile_reused,
                "verified_artifact_count": int(max(0, verified_artifact_count)),
            },
        )
    )


def _normalize_policy(
    policy: BrowserDownloadSessionReusePolicy,
) -> BrowserDownloadSessionReusePolicy:
    if isinstance(policy, BrowserDownloadSessionReusePolicy):
        return policy
    return BrowserDownloadSessionReusePolicy(schema_version="1.0")


def _resolve_base_dir(*, raw_base_dir: str, default_base_dir: Path) -> Path:
    token = str(raw_base_dir or "").strip()
    if token:
        return Path(token).expanduser().resolve()
    return (default_base_dir / "browser_session_reuse").resolve()


def _normalize_mode(raw_mode: str) -> str:
    token = str(raw_mode or "").strip().casefold()
    return token or "disabled"


def _normalize_publisher_scope(raw_scope: str) -> str:
    token = str(raw_scope or "").strip().casefold()
    if "://" in token:
        host = str(urlsplit(token).netloc or "").strip().casefold()
        return host[4:] if host.startswith("www.") else host
    return token[4:] if token.startswith("www.") else token


def _reject_reason(
    *,
    mode: str,
    session_key: str,
    publisher_scope: str,
    ttl_seconds: float,
) -> str:
    if mode not in _ALLOWED_REUSE_MODES:
        return "unsupported_mode"
    if not session_key:
        return "missing_session_key"
    if not publisher_scope:
        return "missing_publisher_scope"
    if ttl_seconds <= 0:
        return "invalid_ttl"
    if ttl_seconds > _MAX_TTL_SECONDS:
        return "ttl_too_large"
    return ""


def _cross_publisher_rejection_reason(
    *,
    base_dir: Path,
    key_hash: str,
    publisher_scope: str,
    allow_cross_publisher: bool,
) -> str:
    if allow_cross_publisher:
        return ""
    index = _read_json(base_dir / _SESSION_REUSE_INDEX_FILE)
    existing = index.get(key_hash)
    if not isinstance(existing, dict):
        return ""
    existing_scope = _normalize_publisher_scope(
        str(existing.get("publisher_scope") or "")
    )
    if existing_scope and existing_scope != publisher_scope:
        return "cross_publisher_scope_mismatch"
    return ""


def _profile_dir_for(
    *,
    base_dir: Path,
    mode: str,
    key_hash: str,
    publisher_scope: str,
) -> Path:
    scope_hash = _hash_token(publisher_scope)
    return base_dir / f"{_SESSION_REUSE_DIR_PREFIX}-{mode}-{scope_hash}-{key_hash}"


def _hash_token(value: str) -> str:
    token = str(value or "").strip()
    if not token:
        return ""
    return sha256(token.encode("utf-8")).hexdigest()[:16]


def _is_fresh_profile(profile_dir: Path) -> bool:
    ledger = _read_json(profile_dir / _SESSION_REUSE_LEDGER_FILE)
    if not ledger:
        return False
    expires_at = _coerce_float(ledger.get("expires_at_epoch_seconds"))
    return profile_dir.exists() and expires_at > time.time()


def _effective_ttl_seconds(raw_ttl_seconds: float) -> float:
    return max(1.0, min(float(raw_ttl_seconds or 0.0), _MAX_TTL_SECONDS))


def _write_session_ledger(
    *,
    profile_dir: Path,
    mode: str,
    key_hash: str,
    publisher_scope: str,
    ttl_seconds: float,
    expires_at: float,
) -> None:
    ledger_path = profile_dir / _SESSION_REUSE_LEDGER_FILE
    existing = _read_json(ledger_path)
    created_at = _coerce_float(existing.get("created_at_epoch_seconds")) or time.time()
    payload = {
        "schema_version": _SESSION_REUSE_SCHEMA_VERSION,
        "mode": mode,
        "session_key_hash": key_hash,
        "publisher_scope": publisher_scope,
        "created_at_epoch_seconds": created_at,
        "last_used_at_epoch_seconds": time.time(),
        "ttl_seconds": ttl_seconds,
        "expires_at_epoch_seconds": expires_at,
    }
    _write_json(ledger_path, payload)


def _write_key_index(
    *,
    base_dir: Path,
    key_hash: str,
    mode: str,
    publisher_scope: str,
    profile_path: Path,
    allow_cross_publisher: bool,
) -> None:
    index_path = base_dir / _SESSION_REUSE_INDEX_FILE
    index = _read_json(index_path)
    index[key_hash] = {
        "schema_version": _SESSION_REUSE_SCHEMA_VERSION,
        "mode": mode,
        "publisher_scope": publisher_scope,
        "profile_path": str(profile_path),
        "allow_cross_publisher": bool(allow_cross_publisher),
        "updated_at_epoch_seconds": time.time(),
    }
    _write_json(index_path, index)


def _cleanup_expired_session_dirs(base_dir: Path) -> int:
    if not base_dir.exists():
        return 0
    removed = 0
    for candidate in base_dir.glob(f"{_SESSION_REUSE_DIR_PREFIX}-*"):
        if not candidate.is_dir():
            continue
        ledger = _read_json(candidate / _SESSION_REUSE_LEDGER_FILE)
        expires_at = _coerce_float(ledger.get("expires_at_epoch_seconds"))
        if expires_at and expires_at > time.time():
            continue
        try:
            shutil.rmtree(candidate, ignore_errors=True)
            removed += 1
        except OSError:
            continue
    if removed:
        _drop_missing_index_entries(base_dir)
    return removed


def _drop_missing_index_entries(base_dir: Path) -> None:
    index_path = base_dir / _SESSION_REUSE_INDEX_FILE
    index = _read_json(index_path)
    updated: dict[str, Any] = {}
    for key_hash, raw_entry in index.items():
        if not isinstance(raw_entry, dict):
            continue
        profile_path = Path(str(raw_entry.get("profile_path") or ""))
        if profile_path.exists():
            updated[str(key_hash)] = raw_entry
    _write_json(index_path, updated)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, sort_keys=True),
        encoding="utf-8",
    )


def _coerce_float(value: object) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def _log_resolution(
    *,
    ctx: RunContext,
    normalized_url: str,
    decision: BrowserDownloadSessionReuseDecision,
) -> None:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_session_reuse_resolved",
            module=logger.name,
            fields=browser_session_reuse_log_fields(
                normalized_url=normalized_url,
                decision=decision,
            ),
        )
    )
