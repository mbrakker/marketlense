from __future__ import annotations

from src.utils.url_utils import normalize_url


def mail_delivery_request_idempotency_key(
    *,
    generation_id: str,
    source_url: str,
    delivery_email: str,
    source_identity_id: str = "",
) -> str:
    return "|".join(
        (
            "mail_delivery",
            str(generation_id or "").strip() or "source-default",
            normalize_url(source_url),
            str(delivery_email or "").strip().casefold(),
            str(source_identity_id or "").strip(),
        )
    )


def legacy_mail_delivery_request_idempotency_key(
    *, generation_id: str, source_url: str, delivery_email: str
) -> str:
    return "|".join(
        (
            "mail_delivery",
            str(generation_id or "").strip() or "source-default",
            normalize_url(source_url),
            str(delivery_email or "").strip().casefold(),
        )
    )
