from __future__ import annotations

from dataclasses import dataclass

# Malformed native-extraction detection.
#
# Some publisher PDFs (Mintel-class gated reports) carry broken ToUnicode
# CMaps or custom font encodings. Native extraction then returns text that is
# dense enough to pass char/word confidence checks but is actually corrupted:
# homoglyph script mixing, unusable private-use mappings, or missing word
# spacing. Detection is deterministic and content-agnostic: it inspects
# character-class statistics only and never rewrites extracted text.

_PUA_FIRST = 0xE000
_PUA_LAST = 0xF8FF
_REPLACEMENT_CHAR = 0xFFFD
_CYRILLIC_FIRST = 0x0400
_CYRILLIC_LAST = 0x04FF
_GREEK_RANGES = ((0x0370, 0x03FF), (0x1F00, 0x1FFF))
_LATIN_EXT_FIRST = 0x0100
_LATIN_EXT_LAST = 0x024F
_FORMAT_FIRST = 0x200B
_FORMAT_LAST = 0x200F

_MIN_NON_SPACE_CHARS = 64
_MIN_LETTERS = 64
_MIN_BROKEN_SPACING_CHARS = 400
_MIN_LONG_TOKENS = 40
_MIN_MIXED_SCRIPT_TOKENS = 3

_MAX_USABLE_MAPPING_RATIO = 0.05
_MAX_CONTROL_RATIO = 0.05
_MIN_NO_SPACE_RATIO = 0.02
_LONG_TOKEN_LENGTH = 20
_LONG_TOKEN_SHARE = 0.30
_LATIN_EXT_FLOOD_RATIO = 0.60
_MIN_FALLBACK_CHARS = 16


@dataclass(frozen=True)
class NativeTextQuality:
    """Deterministic malformation assessment for one page of extracted text."""

    schema_version: str = "1.0"
    is_malformed: bool = False
    reasons: tuple[str, ...] = ()
    non_space_chars: int = 0
    flag_count: int = 0


def _is_cyrillic(codepoint: int) -> bool:
    return _CYRILLIC_FIRST <= codepoint <= _CYRILLIC_LAST


def _is_greek(codepoint: int) -> bool:
    return any(first <= codepoint <= last for first, last in _GREEK_RANGES)


def _is_latin_extension(codepoint: int) -> bool:
    return _LATIN_EXT_FIRST <= codepoint <= _LATIN_EXT_LAST


def _is_unusable_mapping(codepoint: int) -> bool:
    return _PUA_FIRST <= codepoint <= _PUA_LAST or codepoint == _REPLACEMENT_CHAR


def _is_control_like(codepoint: int, char: str) -> bool:
    if char.isspace():
        return False
    if codepoint <= 0x0008 or 0x000E <= codepoint <= 0x001F:
        return True
    return _FORMAT_FIRST <= codepoint <= _FORMAT_LAST


def _token_has_ascii_and_foreign_script(token: str) -> bool:
    has_ascii = False
    has_foreign = False
    for char in token:
        codepoint = ord(char)
        if char.isascii() and char.isalpha():
            has_ascii = True
        elif _is_cyrillic(codepoint) or _is_greek(codepoint):
            has_foreign = True
        if has_ascii and has_foreign:
            return True
    return False


def _is_alpha_token(token: str) -> bool:
    return bool(token) and all(char.isalpha() for char in token)


def evaluate_native_text_quality(text: str) -> NativeTextQuality:
    """Assess extracted text for extraction-malformation signatures.

    Pure and deterministic: character-class statistics only, no content
    rewriting, no language assumptions beyond script identity.
    """
    stripped = text or ""
    total = len(stripped)
    if not stripped.strip():
        return NativeTextQuality()

    non_space = 0
    whitespace = 0
    letters = 0
    ascii_letters = 0
    latin_ext_letters = 0
    unusable_mapping = 0
    control_like = 0
    mixed_script_tokens = 0
    alpha_tokens = 0
    long_alpha_tokens = 0
    token: list[str] = []

    def close_token() -> None:
        nonlocal mixed_script_tokens, alpha_tokens, long_alpha_tokens
        if not token:
            return
        token_text = "".join(token)
        if _token_has_ascii_and_foreign_script(token_text):
            mixed_script_tokens += 1
        if _is_alpha_token(token_text):
            alpha_tokens += 1
            if len(token_text) > _LONG_TOKEN_LENGTH:
                long_alpha_tokens += 1
        token.clear()

    for char in stripped:
        codepoint = ord(char)
        if char.isspace():
            whitespace += 1
            close_token()
            continue
        non_space += 1
        if char.isalpha():
            letters += 1
            if char.isascii():
                ascii_letters += 1
            elif _is_latin_extension(codepoint):
                latin_ext_letters += 1
        if _is_unusable_mapping(codepoint):
            unusable_mapping += 1
        if _is_control_like(codepoint, char):
            control_like += 1
        token.append(char)
    close_token()

    reasons: list[str] = []
    if (
        non_space >= _MIN_NON_SPACE_CHARS
        and unusable_mapping / non_space > _MAX_USABLE_MAPPING_RATIO
    ):
        reasons.append("unusable_character_mapping")
    if (
        non_space >= _MIN_NON_SPACE_CHARS
        and control_like / total > _MAX_CONTROL_RATIO
    ):
        reasons.append("control_character_flood")
    if (
        non_space >= _MIN_NON_SPACE_CHARS
        and mixed_script_tokens >= _MIN_MIXED_SCRIPT_TOKENS
    ):
        reasons.append("homoglyph_script_mixing")
    if letters >= _MIN_LETTERS and latin_ext_letters / letters > _LATIN_EXT_FLOOD_RATIO:
        reasons.append("latin_extension_flood")
    if non_space >= _MIN_BROKEN_SPACING_CHARS and (
        whitespace / total < _MIN_NO_SPACE_RATIO
    ):
        reasons.append("broken_spacing")
    if (
        alpha_tokens >= _MIN_LONG_TOKENS
        and long_alpha_tokens / alpha_tokens > _LONG_TOKEN_SHARE
    ):
        reasons.append("broken_word_boundaries")

    return NativeTextQuality(
        is_malformed=bool(reasons),
        reasons=tuple(reasons),
        non_space_chars=non_space,
        flag_count=len(reasons),
    )


@dataclass(frozen=True)
class NativeTextSelection:
    """Outcome of choosing between two native extractions of one page."""

    schema_version: str = "1.0"
    text: str = ""
    used_fallback: bool = False
    primary_reasons: tuple[str, ...] = ()
    fallback_reasons: tuple[str, ...] = ()


def select_healthier_native_text(primary: str, fallback: str) -> NativeTextSelection:
    """Return the healthier of two native extractions of the same page.

    The primary extraction is kept unless it is flagged as malformed and the
    fallback extraction is strictly healthier (clean, or fewer distinct
    malformation flags with usable content). Empty fallbacks never replace a
    primary extraction, so scan-only pages keep the existing behavior.
    """
    primary_quality = evaluate_native_text_quality(primary)
    if not primary_quality.is_malformed:
        return NativeTextSelection(
            text=primary, primary_reasons=primary_quality.reasons
        )
    fallback_quality = evaluate_native_text_quality(fallback)
    fallback_usable = len(fallback.strip()) >= _MIN_FALLBACK_CHARS
    strictly_healthier = (
        fallback_usable
        and not fallback_quality.is_malformed
        or (
            fallback_usable
            and fallback_quality.flag_count < primary_quality.flag_count
        )
    )
    if strictly_healthier:
        return NativeTextSelection(
            text=fallback,
            used_fallback=True,
            primary_reasons=primary_quality.reasons,
            fallback_reasons=fallback_quality.reasons,
        )
    return NativeTextSelection(
        text=primary,
        primary_reasons=primary_quality.reasons,
        fallback_reasons=fallback_quality.reasons,
    )

