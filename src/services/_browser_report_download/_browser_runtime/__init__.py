"""Internal runtime capabilities for browser-report acquisition.

The package isolates terminal inspection, evidence acquisition, bounded
recovery, worker transport, and browser lifecycle mechanics while preserving
``browser_report_download_service`` as the single external-system boundary.
"""

import re

_TERMINAL_TRANSIENT_MARKERS = (
    "please wait",
    "submitting",
    "processing",
    "loading",
    "one moment",
)
_TERMINAL_SUCCESS_URL_MARKERS = ("thank", "success", "confirm", "complete", "done")
_TERMINAL_SUCCESS_TEXT_MARKERS = (
    "thank you",
    "thanks for",
    "request received",
    "submission received",
    "download link",
    "check your email",
    "emailed",
    "sent to your email",
)
_TERMINAL_REPORT_TEXT_MARKERS = (
    "report",
    "research",
    "insight",
    "analysis",
    "survey",
    "outlook",
    "white paper",
    "whitepaper",
)
_TERMINAL_TEXT_EXCERPT_MAX_CHARS = 600
_TERMINAL_STABILIZATION_DEFAULT_POLL_SCHEDULE_SECONDS = (0.25, 0.5, 1.0)
_TERMINAL_STABILIZATION_EMAIL_POLL_SCHEDULE_SECONDS = (0.25, 0.5, 1.0, 1.5)
_AGENT_RUN_TIMEOUT_MIN_BUFFER_SECONDS = 1.0
_AGENT_RUN_TIMEOUT_STEP_BUFFER_SECONDS = 0.5
_AGENT_RUN_TIMEOUT_MAX_BUFFER_SECONDS = 30.0
_BROWSER_KILL_TIMEOUT_SECONDS = 15.0
_BROWSER_RESET_TIMEOUT_SECONDS = 10.0
_BROWSER_CLEANUP_GRACE_SECONDS = 5.0
_BROWSER_PROFILE_DIR_PREFIX = "browser-use-user-data-dir-profile"
_BROWSER_USE_TEMP_DIR_PATTERNS = (
    "browser-use-user-data-dir-*",
    "browser-use-downloads-*",
    "browseruse-tmp-*",
)
_STALE_BROWSER_USE_TEMP_DIR_MIN_AGE_SECONDS = 15 * 60.0
_TEMP_CLEANUP_LOG_SAMPLE_LIMIT = 5
_TIMED_OUT_COMPLETED_HISTORY_GRACE_SECONDS = 2.0
_TIMED_OUT_RECOVERY_OPERATION_TIMEOUT_SECONDS = 5.0
_AGENT_COMPLETED_HISTORY_POLL_SECONDS = 0.25
_BROWSER_AGENT_WORKER_ENV = "MARKET_LENSE_BROWSER_AGENT_WORKER"
# Let the worker finish its own timeout stop/cleanup path and write a typed
# response instead of being killed by the outer subprocess envelope mid-exit.
_BROWSER_AGENT_WORKER_TIMEOUT_BUFFER_SECONDS = 45.0
_BROWSER_AGENT_WORKER_OUTPUT_MAX_CHARS = 1200
_ANSI_ESCAPE_PATTERN = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
_BROWSER_AGENT_USE_JUDGE = False
_LOOKUP_FIELD_MARKERS = (
    "location",
    "country",
    "state",
    "province",
    "region",
    "territory",
)
_LOOKUP_FAILURE_MARKERS = (
    "could not",
    "did not",
    "failed",
    "failure",
    "incorrect",
    "not correctly",
    "not processed",
    "not resolve",
    "not selected",
    "not work",
    "unsuccessful",
    "unverified",
)
_LOOKUP_SUBMIT_MARKERS = (
    "submit",
    "submitted",
    "submission",
)
_EMAIL_DOMAIN_BLOCK_MARKERS = (
    "business email",
    "work email",
    "corporate email",
    "company email",
    "professional email",
    "valid business email",
)
_EMAIL_DOMAIN_FAILURE_MARKERS = (
    "email error",
    "email address error",
    "invalid email",
    "not a business email",
    "not a work email",
    "not a corporate email",
    "not a professional email",
    "requires a business email",
    "require a business email",
    "please use a business email",
    "please enter a business email",
    "rejected",
)
_PARTIAL_HISTORY_TEXT_MAX_CHARS = 12000

__all__ = [
    "_TERMINAL_TRANSIENT_MARKERS",
    "_TERMINAL_SUCCESS_URL_MARKERS",
    "_TERMINAL_SUCCESS_TEXT_MARKERS",
    "_TERMINAL_REPORT_TEXT_MARKERS",
    "_TERMINAL_TEXT_EXCERPT_MAX_CHARS",
    "_TERMINAL_STABILIZATION_DEFAULT_POLL_SCHEDULE_SECONDS",
    "_TERMINAL_STABILIZATION_EMAIL_POLL_SCHEDULE_SECONDS",
    "_AGENT_RUN_TIMEOUT_MIN_BUFFER_SECONDS",
    "_AGENT_RUN_TIMEOUT_STEP_BUFFER_SECONDS",
    "_AGENT_RUN_TIMEOUT_MAX_BUFFER_SECONDS",
    "_BROWSER_KILL_TIMEOUT_SECONDS",
    "_BROWSER_RESET_TIMEOUT_SECONDS",
    "_BROWSER_CLEANUP_GRACE_SECONDS",
    "_BROWSER_PROFILE_DIR_PREFIX",
    "_BROWSER_USE_TEMP_DIR_PATTERNS",
    "_STALE_BROWSER_USE_TEMP_DIR_MIN_AGE_SECONDS",
    "_TEMP_CLEANUP_LOG_SAMPLE_LIMIT",
    "_TIMED_OUT_COMPLETED_HISTORY_GRACE_SECONDS",
    "_TIMED_OUT_RECOVERY_OPERATION_TIMEOUT_SECONDS",
    "_AGENT_COMPLETED_HISTORY_POLL_SECONDS",
    "_BROWSER_AGENT_WORKER_ENV",
    "_BROWSER_AGENT_WORKER_TIMEOUT_BUFFER_SECONDS",
    "_BROWSER_AGENT_WORKER_OUTPUT_MAX_CHARS",
    "_ANSI_ESCAPE_PATTERN",
    "_BROWSER_AGENT_USE_JUDGE",
    "_LOOKUP_FIELD_MARKERS",
    "_LOOKUP_FAILURE_MARKERS",
    "_LOOKUP_SUBMIT_MARKERS",
    "_EMAIL_DOMAIN_BLOCK_MARKERS",
    "_EMAIL_DOMAIN_FAILURE_MARKERS",
    "_PARTIAL_HISTORY_TEXT_MAX_CHARS",
]
