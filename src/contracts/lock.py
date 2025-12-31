from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class LockInfo:
    schema_version: str = field(metadata={"doc": "Lock info schema version."})
    lock_path: str = field(metadata={"doc": "Filesystem path to the lock file."})
    owner_id: str = field(metadata={"doc": "Identifier for the current lock owner."})
    pid: int = field(metadata={"doc": "Process ID of the owner recorded in the lock file."})
    created_at: float = field(metadata={"doc": "Epoch seconds when the lock was created."})


@dataclass(frozen=True)
class LockAcquireRequest:
    schema_version: str = field(metadata={"doc": "Lock acquire request schema version."})
    lock_path: str = field(metadata={"doc": "Filesystem path to the lock file."})
    owner_id: str = field(metadata={"doc": "Identifier for the requester that will hold the lock."})
    pid: int = field(metadata={"doc": "Process ID of the requester, captured for diagnostics."})
    ttl_seconds: float = field(default=7200.0, metadata={"doc": "Time in seconds before an existing lock is considered stale. <=0 disables stale eviction."})


@dataclass(frozen=True)
class LockAcquireResponse:
    schema_version: str = field(metadata={"doc": "Lock acquire response schema version."})
    acquired: bool = field(metadata={"doc": "True when the lock was acquired by the requester."})
    lock: Optional[LockInfo] = field(default=None, metadata={"doc": "Lock details when acquired."})
    conflict: Optional[LockInfo] = field(default=None, metadata={"doc": "Existing lock details when acquisition failed."})


@dataclass(frozen=True)
class LockReleaseRequest:
    schema_version: str = field(metadata={"doc": "Lock release request schema version."})
    lock_path: str = field(metadata={"doc": "Filesystem path to the lock file."})
    owner_id: str = field(metadata={"doc": "Identifier for the requester releasing the lock."})
    pid: int = field(metadata={"doc": "Process ID of the requester releasing the lock."})


@dataclass(frozen=True)
class LockReleaseResponse:
    schema_version: str = field(metadata={"doc": "Lock release response schema version."})
    released: bool = field(metadata={"doc": "True when the lock file was removed by the requester."})
