from __future__ import annotations

import re

_WORD_RE = re.compile(r"[a-z]+", re.IGNORECASE)


def detached_percent_label_tokens(text: str) -> set[str]:
    """Identify labels preceding a detached run of standalone percent values."""

    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    for start, line in enumerate(lines):
        if not any(char.isalpha() for char in line) or any(
            char.isdigit() for char in line
        ):
            continue
        labels = []
        index = start
        while (
            index < len(lines)
            and any(char.isalpha() for char in lines[index])
            and not any(char.isdigit() for char in lines[index])
        ):
            labels.append(lines[index])
            index += 1
        if len(labels) < 3:
            continue
        values = 0
        while index < len(lines):
            value_line = lines[index]
            if (
                "%" in value_line
                and any(char.isdigit() for char in value_line)
                and not any(char.isalpha() for char in value_line)
            ):
                values += 1
                index += 1
                continue
            break
        if values < 3:
            continue
        token_counts: dict[str, int] = {}
        for label in labels:
            normalized = re.sub(r"won['’]t", "no", label.casefold())
            for token in set(_WORD_RE.findall(normalized)):
                token_counts[token] = token_counts.get(token, 0) + 1
        return {token for token, count in token_counts.items() if count == 1}
    return set()


def layout_text_preserves_label_value_rows(primary: str, layout_ordered: str) -> bool:
    """Use coordinate order only when it rejoins a detached numeric series."""

    if not detached_percent_label_tokens(primary):
        return False
    associated_rows = sum(
        1
        for line in str(layout_ordered or "").splitlines()
        if "%" in line
        and any(char.isalpha() for char in line)
        and any(char.isdigit() for char in line)
    )
    return associated_rows >= 3
