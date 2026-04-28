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
