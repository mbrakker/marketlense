from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BrowserDownloadWarmWorkerPoolPolicy:
    schema_version: str = field(
        metadata={"doc": "Browser warm-worker-pool policy schema version."}
    )
    enabled: bool = field(
        default=False,
        metadata={"doc": "Whether same-publisher batch jobs may use warm workers."},
    )
    max_workers: int = field(
        default=1,
        metadata={"doc": "Maximum warm worker processes retained per local runtime."},
    )
    max_runs_per_worker: int = field(
        default=3,
        metadata={"doc": "Number of jobs a warm worker may process before restart."},
    )
    max_memory_mb: int = field(
        default=768,
        metadata={"doc": "RSS memory ceiling that triggers warm worker restart."},
    )
    idle_ttl_seconds: float = field(
        default=300.0,
        metadata={"doc": "Maximum idle age before a warm worker is restarted."},
    )
    fallback_to_subprocess: bool = field(
        default=True,
        metadata={
            "doc": "Whether to fall back to the existing one-shot subprocess path when warm dispatch fails."
        },
    )


@dataclass(frozen=True)
class BrowserDownloadWarmWorkerPoolDecision:
    schema_version: str = field(
        metadata={"doc": "Browser warm-worker-pool decision schema version."}
    )
    enabled: bool = field(metadata={"doc": "Whether warm pooling was requested."})
    accepted: bool = field(
        metadata={"doc": "Whether this request may use a warm worker."}
    )
    publisher_scope: str = field(metadata={"doc": "Normalized publisher host scope."})
    pool_key_hash: str = field(
        metadata={"doc": "Short hash identifying the same-publisher warm pool."}
    )
    max_runs_per_worker: int = field(
        metadata={"doc": "Effective restart limit for the selected worker."}
    )
    max_memory_mb: int = field(
        metadata={"doc": "Effective memory ceiling for the selected worker."}
    )
    rejection_reason: str = field(
        default="",
        metadata={"doc": "Typed rejection reason when warm pooling is not accepted."},
    )
