from __future__ import annotations

# ruff: noqa: F401

from src.services._browser_report_download._browser_runtime._session_lifecycle.cleanup import (
    _cleanup_browser_profile_dir,
    _cleanup_managed_browser_profile_dirs,
    _cleanup_new_browser_use_temp_dirs,
    _cleanup_stale_browser_use_temp_dirs,
    _default_session_reuse_base_dir,
    _list_browser_use_temp_dirs,
    _log_browser_cleanup_failure,
    _new_managed_browser_profile_dir,
    _remove_browser_use_temp_dirs,
)
from src.services._browser_report_download._browser_runtime._session_lifecycle.history import (
    BrowserAgentHistoryResult,
    _prime_agent_timing_fields,
    _read_completed_agent_history,
    _resolve_agent_run_timeout_seconds,
    _run_agent_history_with_timeout,
    _signal_agent_stop,
)
from src.services._browser_report_download._browser_runtime._session_lifecycle.partial_history import (
    _SyntheticActionResult,
    _SyntheticAgentHistory,
    _SyntheticHistoryEntry,
    _SyntheticHistoryState,
    _collect_agent_history_text,
    _infer_encountered_form_fields,
    _read_distinct_history_urls,
    _read_email_domain_blocker_partial_history,
    _read_lookup_blocker_partial_history,
    _read_terminal_blocker_partial_history,
    _resolve_lookup_blocker_label,
    _serialize_history_fragment,
    _truncate_partial_history_excerpt,
)
from src.services._browser_report_download._browser_runtime._session_lifecycle.shutdown import (
    _force_stop_local_browser_process,
    _kill_browser,
    _kill_browser_with_timeout,
    _prepare_browser_for_shutdown,
)
