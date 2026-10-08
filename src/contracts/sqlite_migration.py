from __future__ import annotations

from dataclasses import dataclass, field

from src.contracts.run_context import RunContext


@dataclass(frozen=True)
class SqliteMigrationAppliedStep:
    schema_version: str = field(
        metadata={"doc": "SQLite migration applied-step schema version."}
    )
    migration_id: str = field(
        metadata={"doc": "Stable ordered migration identifier recorded in the ledger."}
    )
    version: int = field(
        metadata={"doc": "Monotonic schema version after the migration completed."}
    )
    duration_ms: int = field(
        metadata={
            "doc": "Elapsed wall-clock duration for the migration in milliseconds."
        }
    )


@dataclass(frozen=True)
class SqliteMigrationApplyRequest:
    schema_version: str = field(
        metadata={"doc": "SQLite migration apply request schema version."}
    )
    database_key: str = field(
        metadata={
            "doc": "Stable logical database boundary key, for example reports_db."
        }
    )
    db_path: str = field(
        metadata={"doc": "Resolved SQLite database path receiving schema migrations."}
    )
    target_version: int = field(
        metadata={
            "doc": "Highest expected schema version for the selected database boundary."
        }
    )
    ctx: RunContext = field(
        metadata={"doc": "Run context used for structured migration logging."}
    )


@dataclass(frozen=True)
class SqliteMigrationApplyResponse:
    schema_version: str = field(
        metadata={"doc": "SQLite migration apply response schema version."}
    )
    database_key: str = field(
        metadata={"doc": "Stable logical database boundary key that was migrated."}
    )
    current_version: int = field(
        metadata={"doc": "Current schema version persisted after migration processing."}
    )
    applied_steps: tuple[SqliteMigrationAppliedStep, ...] = field(
        metadata={"doc": "Ordered migration steps applied during this execution."}
    )


@dataclass(frozen=True)
class SqliteCapabilityInspectionRequest:
    schema_version: str = field(
        metadata={"doc": "SQLite capability inspection request version."}
    )
    database_key: str = field(
        metadata={"doc": "Canonical migration registry key for this database."}
    )
    db_path: str = field(metadata={"doc": "Existing SQLite database path to inspect."})
    lock_timeout_seconds: float = field(
        default=0.1,
        metadata={"doc": "Maximum wait for a reversible writer-lock probe."},
    )


@dataclass(frozen=True)
class SqliteCapabilityInspectionResponse:
    schema_version: str = field(
        metadata={"doc": "SQLite capability inspection response version."}
    )
    database_key: str = field(
        metadata={"doc": "Canonical migration registry key inspected."}
    )
    status: str = field(
        metadata={"doc": "Inspection outcome: ready, degraded, or blocked."}
    )
    reason_code: str = field(
        metadata={"doc": "Stable machine-readable inspection reason."}
    )
    retryable: bool = field(
        metadata={"doc": "Whether an operator may safely retry this inspection."}
    )
    current_version: int = field(
        metadata={"doc": "Recorded migration version, or zero when unavailable."}
    )
    expected_version: int = field(
        metadata={"doc": "Latest version in the canonical migration registry."}
    )
    integrity_ok: bool = field(
        metadata={"doc": "Whether SQLite quick_check reported an intact database."}
    )
    foreign_keys_ok: bool = field(
        metadata={"doc": "Whether PRAGMA foreign_key_check found no violations."}
    )
    write_lock_available: bool = field(
        metadata={"doc": "Whether a bounded BEGIN IMMEDIATE/ROLLBACK succeeded."}
    )
