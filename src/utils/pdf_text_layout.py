from __future__ import annotations

from collections import defaultdict
import re
from typing import Sequence

_WORD_RE = re.compile(r"[a-z]+", re.IGNORECASE)
_PERCENT_WORD_RE = re.compile(r"\d{1,3}(?:\.\d+)?%")
_PLATFORM_CHART_TITLE_RE = re.compile(
    r"\btop\s*1\s+(?P<platforms>.+?)\s+creators?\s+vs\.?\s+"
    r"share\s+of\s+views\s+by\s+platform\b",
    re.IGNORECASE,
)
_COHORT_LABEL_RE = re.compile(
    r"\bcreators\s+with\s+"
    r"(?P<cohort>\d+\s*m\s*\+|\d+\s*[-–]\s*\d+\s*m)\s+"
    r"total\s+views\b",
    re.IGNORECASE,
)


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


def has_two_panel_percent_chart_candidate(text: str) -> bool:
    """Cheap text gate for a positioned two-platform percentage chart."""

    normalized = str(text or "")
    return (
        bool(_PLATFORM_CHART_TITLE_RE.search(normalized))
        and len(re.findall(r"\b\d{1,3}(?:\.\d+)?\s*%", normalized)) >= 6
    )


def derive_two_panel_percent_chart_evidence(
    native_text: str,
    words: Sequence[tuple],
    *,
    page_number: int,
) -> str | None:
    """Reconstruct a narrowly recognized two-panel chart from native word geometry.

    The returned text is explicitly marked as derived. It is safe to retain beside
    the verbatim page text, but must not replace or be labelled as native text.
    """

    text = str(native_text or "")
    if not has_two_panel_percent_chart_candidate(text):
        return None
    title_match = _PLATFORM_CHART_TITLE_RE.search(text)
    if title_match is None:
        return None
    if two_panel_chart_platform_names(text) is None:
        return None

    normalized_text = re.sub(r"\s+", " ", text)
    population_match = re.search(
        r"creators? with over\s+(?P<limit>\d+(?:\.\d+)?\s*[KMB])\s+views",
        normalized_text,
        re.IGNORECASE,
    )
    definition_match = re.search(
        r"top creators defined as those with over\s+"
        r"(?P<limit>\d+(?:\.\d+)?\s*[KMB])\s+total views",
        normalized_text,
        re.IGNORECASE,
    )
    if (
        population_match is None
        or definition_match is None
        or re.sub(r"\s+", "", population_match.group("limit").casefold())
        != re.sub(r"\s+", "", definition_match.group("limit").casefold())
    ):
        return None

    axis_words = [
        word
        for word in words
        if len(word) >= 5 and str(word[4]).casefold() in {"creators", "views"}
    ]
    axis_rows: list[list[tuple]] = []
    for word in sorted(axis_words, key=lambda item: float(item[1])):
        row = next(
            (
                existing
                for existing in axis_rows
                if abs(
                    float(word[1])
                    - sum(float(item[1]) for item in existing) / len(existing)
                )
                <= 8.0
            ),
            None,
        )
        if row is None:
            axis_rows.append([word])
        else:
            row.append(word)
    valid_axis_rows = [
        sorted(row, key=lambda item: float(item[0]))
        for row in axis_rows
        if [
            str(item[4]).casefold()
            for item in sorted(row, key=lambda item: float(item[0]))
        ]
        == ["creators", "views", "creators", "views"]
    ]
    if len(valid_axis_rows) != 1:
        return None
    axes = valid_axis_rows[0]
    axis_centers = [(float(word[0]) + float(word[2])) / 2 for word in axes]
    axis_gaps = [axis_centers[index + 1] - axis_centers[index] for index in range(3)]
    if min(axis_gaps) <= 0 or axis_gaps[1] <= max(axis_gaps[0], axis_gaps[2]):
        return None

    words_by_block: dict[int, list[tuple]] = defaultdict(list)
    for word in words:
        if len(word) >= 8 and isinstance(word[5], int):
            words_by_block[word[5]].append(word)
    cohort_blocks: list[tuple[str, float, float, float, float]] = []
    for block_words in words_by_block.values():
        block_words.sort(key=lambda item: (int(item[6]), float(item[0])))
        block_text = " ".join(str(item[4]) for item in block_words)
        match = _COHORT_LABEL_RE.search(block_text)
        if match is None:
            continue
        cohort_blocks.append(
            (
                re.sub(r"\s+", "", match.group("cohort")).upper(),
                min(float(item[0]) for item in block_words),
                min(float(item[1]) for item in block_words),
                max(float(item[2]) for item in block_words),
                max(float(item[3]) for item in block_words),
            )
        )
    if len(cohort_blocks) != 4:
        return None

    panel_axes = [(axes[0], axes[1]), (axes[2], axes[3])]
    cohorts_by_panel: list[list[tuple[str, float, float, float, float]]] = [[], []]
    for cohort in cohort_blocks:
        cohort_center = (cohort[1] + cohort[3]) / 2
        distances = [
            abs(cohort_center - ((float(axis[0]) + float(axis[2])) / 2))
            for axis, _views_axis in panel_axes
        ]
        selected_panel = min(range(2), key=lambda index: distances[index])
        creator_axis = panel_axes[selected_panel][0]
        if cohort[3] >= float(creator_axis[0]):
            return None
        cohorts_by_panel[selected_panel].append(cohort)
    if any(len(cohorts) != 2 for cohorts in cohorts_by_panel):
        return None
    for cohorts in cohorts_by_panel:
        cohorts.sort(key=lambda item: item[2])
    if [cohort[0] for cohort in cohorts_by_panel[0]] != [
        cohort[0] for cohort in cohorts_by_panel[1]
    ]:
        return None

    percent_words = [
        word
        for word in words
        if len(word) >= 5 and _PERCENT_WORD_RE.fullmatch(str(word[4]).strip())
    ]
    values_by_axis: list[list[tuple[float, float]]] = []
    for axis in axes:
        axis_center = (float(axis[0]) + float(axis[2])) / 2
        matching = [
            word
            for word in percent_words
            if abs((float(word[0]) + float(word[2])) / 2 - axis_center) <= 20.0
        ]
        if len(matching) != 2:
            return None
        matching.sort(key=lambda item: float(item[1]))
        values_by_axis.append(
            [
                (float(word[1]), float(str(word[4]).strip().removesuffix("%")))
                for word in matching
            ]
        )

    for creator_values, view_values in (
        (values_by_axis[0], values_by_axis[1]),
        (values_by_axis[2], values_by_axis[3]),
    ):
        if (
            abs(sum(value for _, value in creator_values) - 100) > 1
            or abs(sum(value for _, value in view_values) - 100) > 1
        ):
            return None

    title_line = next(
        (
            re.sub(r"\s+", " ", line).strip()
            for line in text.splitlines()
            if _PLATFORM_CHART_TITLE_RE.search(line)
        ),
        re.sub(r"\s+", " ", title_match.group(0)).strip(),
    )
    population = population_match.group("limit").replace(" ", "")
    lines = [
        "Deterministic PDF layout-derived evidence; not verbatim native PDF text.",
        f"Physical source page {page_number}. Caption scope: {title_line}.",
        (
            "Positioned x-axis labels show two physical panels from left to right; "
            "each panel has a Creators axis followed by a Views axis. Platform "
            "identity is not inferred from caption order."
        ),
        (
            f"The adjacent note describes creators with over {population} views, "
            f"and the footnote defines top creators as those with over {population} "
            "total views. Keep the creator percentages within that stated creator "
            "population and retain the chart's % total scope."
        ),
    ]
    for panel_index in range(2):
        creator_values = values_by_axis[panel_index * 2]
        view_values = values_by_axis[panel_index * 2 + 1]
        for row_index, cohort in enumerate(cohorts_by_panel[panel_index]):
            creator_value = _format_percent(creator_values[row_index][1])
            view_value = _format_percent(view_values[row_index][1])
            lines.append(
                f"Panel {panel_index + 1}: the {cohort[0]} total-view cohort is "
                f"{creator_value}% of creators in the stated over-{population}-view "
                f"creator population, with {view_value}% of views in the chart's "
                "% total frame."
            )
    return "\n".join(lines)


def two_panel_chart_platform_names(text: str) -> tuple[str, str] | None:
    """Return the two identity candidates named by a chart caption, without binding them."""

    match = _PLATFORM_CHART_TITLE_RE.search(str(text or ""))
    if match is None:
        return None
    parts = re.split(r"\s+and\s+", match.group("platforms"), flags=re.IGNORECASE)
    names = tuple(re.sub(r"\s+", " ", part.strip(" ,;:")) for part in parts)
    if len(names) != 2 or not all(names) or names[0].casefold() == names[1].casefold():
        return None
    return names[0], names[1]


def two_panel_chart_image_bbox(
    native_text: str,
    words: Sequence[tuple],
    page_rect: tuple[float, float, float, float],
) -> tuple[float, float, float, float] | None:
    """Locate the visual label band between the caption and chart cohorts."""

    if not has_two_panel_percent_chart_candidate(native_text):
        return None
    blocks: dict[int, list[tuple]] = defaultdict(list)
    for word in words:
        if len(word) >= 8 and isinstance(word[5], int):
            blocks[word[5]].append(word)
    caption_bounds = []
    for block_words in blocks.values():
        block_text = " ".join(str(word[4]) for word in block_words)
        if _PLATFORM_CHART_TITLE_RE.search(block_text):
            caption_bounds.extend(block_words)
    if not caption_bounds:
        return None

    cohort_bounds = []
    for block_words in blocks.values():
        block_text = " ".join(str(word[4]) for word in block_words)
        if _COHORT_LABEL_RE.search(block_text):
            cohort_bounds.append(
                (
                    min(float(word[1]) for word in block_words),
                    max(float(word[3]) for word in block_words),
                )
            )
    if len(cohort_bounds) != 4:
        return None

    axis_words = [
        word
        for word in words
        if len(word) >= 5 and str(word[4]).casefold() in {"creators", "views"}
    ]
    axis_rows: list[list[tuple]] = []
    for word in sorted(axis_words, key=lambda item: float(item[1])):
        row = next(
            (
                existing
                for existing in axis_rows
                if abs(
                    float(word[1])
                    - sum(float(item[1]) for item in existing) / len(existing)
                )
                <= 8.0
            ),
            None,
        )
        if row is None:
            axis_rows.append([word])
        else:
            row.append(word)
    valid_axis_rows = [
        row
        for row in axis_rows
        if [
            str(item[4]).casefold()
            for item in sorted(row, key=lambda item: float(item[0]))
        ]
        == ["creators", "views", "creators", "views"]
    ]
    if len(valid_axis_rows) != 1:
        return None

    page_x0, page_y0, page_x1, page_y1 = (float(value) for value in page_rect)
    y0 = max(float(word[3]) for word in caption_bounds) + 2.0
    y1 = min(top for top, _bottom in cohort_bounds) - 2.0
    if (
        y0 < page_y0
        or y1 > page_y1
        or y0 >= y1
        or y1 - y0 < 16.0
        or min(float(word[1]) for word in valid_axis_rows[0]) <= y1
    ):
        return None
    return page_x0, y0, page_x1, y1


def _format_percent(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:g}"
