from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class PublisherInventorySettings:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory discovery settings schema version."}
    )
    openrouter_api_key: str = field(
        metadata={
            "doc": "OpenRouter API key used when browser-render fallback is required."
        }
    )
    model: str = field(
        metadata={"doc": "Model ID used by the browser-render fallback flow."}
    )
    temperature: float = field(
        metadata={"doc": "Sampling temperature for browser-render discovery."}
    )
    timeout_seconds: float = field(
        metadata={"doc": "Per-model timeout in seconds for browser-render discovery."}
    )
    max_steps: int = field(
        metadata={"doc": "Maximum browser-use agent steps per discovery run."}
    )
    output_dir: str = field(
        metadata={"doc": "Root directory used for temporary browser discovery output."}
    )
    reports_db: str = field(
        metadata={
            "doc": "SQLite reports DB path used for publisher lookups and snapshot indexing."
        }
    )
    google_sa_path: str = field(
        metadata={
            "doc": "Filesystem path to the Google service account JSON used for Drive access when drive_auth_mode=service_account."
        }
    )
    prompt_namespace: str = field(
        metadata={
            "doc": "Prompt namespace used for browser-render inventory discovery."
        }
    )
    pagination_max_pages: int = field(
        metadata={
            "doc": "Hard upper bound on inventory pages traversed in one discovery run."
        }
    )
    http_timeout_seconds: float = field(
        metadata={"doc": "HTTP timeout in seconds for direct HTML fetch discovery."}
    )
    drive_parent_folder_id: str = field(
        default="",
        metadata={
            "doc": "Drive parent folder ID where publisher discovery should create missing publisher artifact folders."
        },
    )
    command_time_budget_seconds: float = field(
        default=570.0,
        metadata={
            "doc": "Hard per-publisher workflow budget in seconds. The orchestrator must stop the run before this budget is exceeded so the command fails explicitly instead of hanging until an external shell timeout."
        },
    )
    drive_auth_mode: str = field(
        default="service_account",
        metadata={"doc": "Drive auth mode: service_account or oauth_user."},
    )
    google_oauth_client_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional OAuth desktop client JSON path when drive_auth_mode=oauth_user."
        },
    )
    google_oauth_token_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional OAuth authorized-user token JSON path when drive_auth_mode=oauth_user."
        },
    )
    openrouter_http_referer: Optional[str] = field(
        default=None,
        metadata={"doc": "Optional HTTP-Referer header sent to OpenRouter."},
    )
    headed: bool = field(
        default=False,
        metadata={
            "doc": "Whether browser-render discovery should run in a visible browser."
        },
    )
    force_browser: bool = field(
        default=False,
        metadata={
            "doc": "Whether discovery must use the browser-render route instead of direct HTTP parsing."
        },
    )
    enable_deferred_candidate_recovery: bool = field(
        default=True,
        metadata={
            "doc": "Whether the orchestrator may schedule deferred second-pass recovery for strong candidates rejected only due to recoverable landing-page failures."
        },
    )
    enable_structured_route_reuse: bool = field(
        default=True,
        metadata={
            "doc": "Whether discovery route planning may prefer typed remembered route traces over legacy free-text route summaries."
        },
    )
    enable_preflight_classifier_and_direct_detail: bool = field(
        default=True,
        metadata={
            "doc": "Whether discovery may use cheap scenario classification and direct-detail short-circuiting before broader archive traversal."
        },
    )
    retry_retries: int = field(
        default=1,
        metadata={"doc": "Retry count for orchestrated inventory discovery attempts."},
    )
    retry_base_delay_seconds: float = field(
        default=1.0,
        metadata={"doc": "Base delay before the first inventory discovery retry."},
    )
    retry_backoff_step_seconds: float = field(
        default=1.0,
        metadata={"doc": "Linear backoff step added per inventory discovery retry."},
    )
    retry_jitter_seconds: float = field(
        default=0.25,
        metadata={"doc": "Maximum jitter added to inventory discovery retry delays."},
    )
    openai_api_key: str = field(
        default="",
        metadata={
            "doc": "OpenAI API key used for candidate screening before report_sources persistence when candidate_screening_enabled=true."
        },
    )
    openai_models: dict[str, str] = field(
        default_factory=dict,
        metadata={
            "doc": "Optional per-namespace OpenAI model overrides used by publisher-inventory candidate screening."
        },
    )
    llm_execution_policies: dict[str, dict[str, object]] = field(
        default_factory=dict,
        metadata={
            "doc": "Versioned provider-call policies retained for publisher-inventory prompt preparation."
        },
    )
    openai_seed: Optional[int] = field(
        default=None,
        metadata={
            "doc": "Optional OpenAI seed used for publisher-inventory candidate screening."
        },
    )
    candidate_screening_enabled: bool = field(
        default=True,
        metadata={
            "doc": "Whether new diff candidates should be screened by OpenAI before insertion into report_sources."
        },
    )
    candidate_screening_model: str = field(
        default="gpt-5-nano",
        metadata={
            "doc": "Base OpenAI model used for candidate screening before report_sources persistence."
        },
    )
    candidate_screening_temperature: float = field(
        default=1.0,
        metadata={
            "doc": "Sampling temperature for publisher-inventory candidate screening."
        },
    )
    candidate_screening_timeout_seconds: float = field(
        default=120.0,
        metadata={
            "doc": "Timeout in seconds for publisher-inventory candidate screening calls."
        },
    )
    candidate_screening_batch_size: int = field(
        default=20,
        metadata={
            "doc": "Maximum number of candidates sent to a single publisher-inventory screening LLM call."
        },
    )
    candidate_screening_prompt_namespace: str = field(
        default="publisher_inventory/meaningful_candidate_screen",
        metadata={
            "doc": "Prompt namespace used to screen new publisher-inventory diff candidates before queueing them for download."
        },
    )
    candidate_quality_check_enabled: bool = field(
        default=True,
        metadata={
            "doc": "Whether landing-page quality checks should run after LLM screening and before report_sources persistence."
        },
    )
    candidate_quality_check_timeout_seconds: float = field(
        default=15.0,
        metadata={
            "doc": "Per-candidate HTTP timeout in seconds for landing-page quality checks before report_sources persistence."
        },
    )
    candidate_quality_check_max_workers: int = field(
        default=6,
        metadata={
            "doc": "Maximum parallel landing-page fetch workers used by the candidate quality-check service."
        },
    )
    resource_quality_ranking_enabled: bool = field(
        default=True,
        metadata={
            "doc": "Whether qualified publisher candidates should be ordered by rolling source-page value consistency before report_sources persistence."
        },
    )
    resource_quality_score_window_size: int = field(
        default=5,
        metadata={
            "doc": "Maximum recent scored reports per publisher resource used for consistency ranking."
        },
    )
    resource_quality_min_sample_size: int = field(
        default=2,
        metadata={
            "doc": "Minimum scored report count before a publisher resource can be promoted by consistency."
        },
    )
    resource_quality_consistency_weight: float = field(
        default=0.35,
        metadata={"doc": "Ranking weight assigned to rolling value-score consistency."},
    )
    resource_quality_average_weight: float = field(
        default=0.50,
        metadata={"doc": "Ranking weight assigned to average report value score."},
    )
    resource_quality_confidence_weight: float = field(
        default=0.15,
        metadata={"doc": "Ranking weight assigned to sample-size confidence."},
    )
    resource_quality_low_score_demotion_threshold: float = field(
        default=45.0,
        metadata={
            "doc": "Average report value score below which a publisher resource is demoted."
        },
    )
    cost_ledger_path: str = field(
        default="./out/cost-ledger.jsonl",
        metadata={
            "doc": "Filesystem path for OpenAI cost ledger entries produced by candidate screening."
        },
    )
    cost_daily_path: str = field(
        default="./out/cost-daily.json",
        metadata={
            "doc": "Filesystem path for daily OpenAI cost rollups produced by candidate screening."
        },
    )
    model_pricing: dict = field(
        default_factory=dict,
        metadata={
            "doc": "Per-model pricing table used for candidate-screening cost estimation."
        },
    )
    llm_retry_retries: int = field(
        default=0,
        metadata={
            "doc": "Legacy compatibility value; candidate-screening service retries are disabled."
        },
    )
    llm_retry_base_delay_seconds: float = field(
        default=0.0,
        metadata={
            "doc": "Legacy compatibility value; candidate-screening service retry delay is disabled."
        },
    )
    llm_retry_backoff_step_seconds: float = field(
        default=0.0,
        metadata={
            "doc": "Legacy compatibility value; candidate-screening service backoff is disabled."
        },
    )
    llm_retry_jitter_seconds: float = field(
        default=0.0,
        metadata={
            "doc": "Legacy compatibility value; candidate-screening service retry jitter is disabled."
        },
    )
    llm_circuit_breaker_failure_threshold: int = field(
        default=3,
        metadata={
            "doc": "Consecutive retryable candidate-screening LLM failures required to open the circuit breaker."
        },
    )
    llm_circuit_breaker_recovery_seconds: float = field(
        default=30.0,
        metadata={
            "doc": "Cooldown in seconds before the candidate-screening LLM circuit breaker allows a probe call."
        },
    )
