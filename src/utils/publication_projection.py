"""Deterministic helpers shared by render readiness and WordPress publication."""

from __future__ import annotations

import hashlib
import re

from src.utils.html_utils import (
    extract_body_html,
    replace_image_sources,
    strip_image_srcset_and_sizes,
    strip_publication_internal_metadata,
)

_IMAGE_SOURCE_RX = re.compile(r'(<img\b[^>]*?\bsrc=["\'])([^"\']+)(["\'])', re.I)


def build_publication_projection(html_text: str) -> str:
    """Build the exact WordPress body shape with media locations canonicalized.

    WordPress replaces local image sources after readiness is decided.  The
    projection preserves the body byte-for-byte apart from those opaque media
    locations, which are represented by stable positional tokens.
    """
    body = strip_publication_internal_metadata(extract_body_html(html_text))
    body = strip_image_srcset_and_sizes(body)
    counter = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal counter
        counter += 1
        return f"{match.group(1)}marketlense-media://{counter}{match.group(3)}"

    return _IMAGE_SOURCE_RX.sub(_replace, body)


def publication_projection_hash(html_text: str) -> str:
    return hashlib.sha256(
        build_publication_projection(html_text).encode("utf-8")
    ).hexdigest()


def apply_publication_media_projection(
    html_text: str, image_mapping: dict[str, str]
) -> str:
    """Apply the production WordPress projection before hash verification."""
    return strip_publication_internal_metadata(
        strip_image_srcset_and_sizes(
            replace_image_sources(extract_body_html(html_text), image_mapping)
        )
    )


__all__ = [
    "apply_publication_media_projection",
    "build_publication_projection",
    "publication_projection_hash",
]
