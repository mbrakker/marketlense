from __future__ import annotations

import math
import sqlite3
from dataclasses import MISSING, dataclass, field, fields
from datetime import datetime, timezone
from typing import List

from src.contracts.schema_validation import (
    empty_required_value,
    field_is_list_typed,
    field_is_required,
)
from src.services._http_transport_common import session_pool_key
from src.services._pdf.candidate_metrics import bounded_quality, candidate_ocr_density
from src.services._pdf.parallel_helpers import split_even_chunks, tally_reason
from src.services._sqlite_common import configure_sqlite_connection, table_exists
from src.utils.coercion import (
    clean_string_list,
    ordered_unique_strings,
    string_value,
    stripped_string_value,
)
from src.utils.json_utils import dump_json_object, dump_json_text
from src.utils.clock import utc_now_iso, utc_now_seconds_iso, utc_now_seconds_z


def test_shared_string_helpers_preserve_current_semantics() -> None:
    assert string_value(None) == ""
    assert string_value("  value  ") == "  value  "
    assert string_value(42) == "42"
    assert stripped_string_value(None) == ""
    assert stripped_string_value("  value  ") == "value"
    assert stripped_string_value(42) == "42"
    assert clean_string_list(
        [" First ", "first", "", None, 7],
        dedupe_casefold=True,
    ) == ["First", "7"]
    assert ordered_unique_strings([" First ", "first", "", None, 7]) == [
        "First",
        "7",
    ]


def test_shared_json_dump_helpers_preserve_fallback_policies() -> None:
    payload = {"unicode": "é", "ordered": [2, 1]}
    assert dump_json_text(payload) == '{"unicode": "é", "ordered": [2, 1]}'
    assert dump_json_object(payload) == '{"unicode": "é", "ordered": [2, 1]}'
    assert dump_json_text({"bad": object()}) == ""
    assert dump_json_object({"bad": object()}) == "{}"


def test_shared_contract_completeness_helpers_preserve_semantics() -> None:
    @dataclass
    class Example:
        required: str
        optional: str = field(default="", metadata={"required": False})

    required_field, optional_field = fields(Example)
    assert required_field.default is MISSING
    assert field_is_required(required_field) is True
    assert field_is_required(optional_field) is False
    assert field_is_list_typed(list[str]) is True
    assert field_is_list_typed(List[str]) is True
    assert empty_required_value(None) is True
    assert empty_required_value("  ") is True
    assert empty_required_value([]) is True
    assert empty_required_value(0) is False


def test_shared_utc_clock_helpers_preserve_timestamp_formats() -> None:
    fixed = datetime(2026, 6, 13, 10, 20, 30, 456789, tzinfo=timezone.utc)
    assert utc_now_iso(fixed) == "2026-06-13T10:20:30.456789+00:00"
    assert utc_now_seconds_iso(fixed) == "2026-06-13T10:20:30+00:00"
    assert utc_now_seconds_z(fixed) == "2026-06-13T10:20:30Z"


def test_sqlite_common_configures_connection_and_checks_tables() -> None:
    connection = sqlite3.connect(":memory:")
    configure_sqlite_connection(connection, busy_timeout_seconds=1.25)
    connection.execute("CREATE TABLE sample (id INTEGER)")

    assert table_exists(connection, "sample") is True
    assert table_exists(connection, "missing") is False
    assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 1250


def test_http_pool_key_normalizes_scheme_host_and_port() -> None:
    assert session_pool_key("HTTPS://Example.COM:443/path") == (
        "https://example.com:443"
    )
    assert session_pool_key("example.com/path") == "https"


def test_pdf_private_helpers_preserve_bounds_density_chunks_and_tallies() -> None:
    assert bounded_quality(math.nan) == 0.0
    assert bounded_quality(-0.5) == 0.0
    assert bounded_quality(1.5) == 1.0
    assert candidate_ocr_density(250, 0.5) == 5.0
    assert split_even_chunks([1, 2, 3, 4, 5], 2) == [[1, 3, 5], [2, 4]]
    stats: dict[str, object] = {}
    tally_reason(stats, "kept")
    tally_reason(stats, "kept")
    assert stats == {"reasons": {"kept": 2}}
