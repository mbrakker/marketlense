from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

from .requests import *  # noqa: F401,F403
from .shared import *  # noqa: F401,F403


def render_auth_access() -> None:
    settings = ui_state.get_app_settings()
    publish_settings = ui_state.get_publish_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return

    configured_client_path = str(settings.google_oauth_client_path or "")
    configured_token_path = str(settings.google_oauth_token_path or "")
    requires_oauth_files = settings.drive_auth_mode == "oauth_user"
    status_level = (
        "warn"
        if requires_oauth_files
        and (not configured_client_path.strip() or not configured_token_path.strip())
        else "info"
    )
    status_label = "Needs setup" if status_level == "warn" else "Ready"
    clicked, filters, main_col, detail_col = _page_shell(
        "Auth & External Access",
        status_label=status_label,
        status_level=status_level,
        primary_action="Drive OAuth Login",
        primary_help=_tip(
            "Run the interactive Drive OAuth user-consent flow.",
            "Use the configured OAuth files unless you intentionally need a one-off local override.",
        ),
        primary_key="run_drive_oauth_login",
    )
    with filters:
        _render_guided_panel(
            "Use configured OAuth files unless you are debugging",
            "Most operators should keep the configured OAuth client and token paths. Switch to custom paths only for a one-off local test.",
            tooltip=_tip(
                "Guided setup for Drive OAuth login.",
                "Configured files are the safest path for a non-technical operator because the project already expects them.",
            ),
        )
        path_mode = st.segmented_control(
            "OAuth file source",
            options=["Configured path", "Custom path"],
            default="Configured path",
            help=_tip(
                "Choose whether to use the project's configured OAuth files or type a local override.",
                "Use the configured path for the normal login flow.",
            ),
            key="auth_access_path_mode",
        )
        if path_mode == "Custom path":
            resolved_client_path = resolve_path_choice(
                mode=path_mode,
                configured_path=configured_client_path,
                custom_path=st.text_input(
                    "Custom OAuth client JSON",
                    value=configured_client_path,
                    help=_tip(
                        "Path to the OAuth desktop client JSON file used for Drive user consent.",
                        "Use a custom path only when your local machine needs a different OAuth client file.",
                    ),
                    key="auth_access_custom_client_json",
                ),
            )
            resolved_token_path = resolve_path_choice(
                mode=path_mode,
                configured_path=configured_token_path,
                custom_path=st.text_input(
                    "Custom OAuth token JSON",
                    value=configured_token_path,
                    help=_tip(
                        "Path where the authorized-user token JSON should be written or reused.",
                        "Use a custom path only when your local machine needs a different token file.",
                    ),
                    key="auth_access_custom_token_json",
                ),
            )
        else:
            resolved_client_path = resolve_path_choice(
                mode=path_mode,
                configured_path=configured_client_path,
                custom_path="",
            )
            resolved_token_path = resolve_path_choice(
                mode=path_mode,
                configured_path=configured_token_path,
                custom_path="",
            )
            _render_readonly_fields(
                [
                    {
                        "label": "Configured OAuth client JSON",
                        "value": configured_client_path or "Not configured",
                        "help": _tip(
                            "Configured OAuth desktop client JSON path used for Drive user consent.",
                            "This is the normal client file path when Drive auth mode is oauth_user.",
                        ),
                    },
                    {
                        "label": "Configured OAuth token JSON",
                        "value": configured_token_path or "Not configured",
                        "help": _tip(
                            "Configured OAuth authorized-user token path used for token reuse.",
                            "This is the normal token file path for local development.",
                        ),
                    },
                ],
                columns=2,
                key_prefix="auth_access_configured_paths",
            )
    if clicked:
        if not resolved_client_path.strip() or not resolved_token_path.strip():
            st.warning(
                "Choose configured OAuth files or provide both custom OAuth file paths before logging in."
            )
        else:
            try:
                result = authorize_oauth_user(
                    DriveOAuthAuthorizeRequest(
                        schema_version="1.0",
                        client_secret_path=resolved_client_path,
                        token_output_path=resolved_token_path,
                        open_browser=True,
                        port=0,
                    ),
                    _ctx("drive_oauth_login"),
                )
                st.session_state["last_drive_oauth_result"] = result
                st.success("Drive OAuth login complete.")
            except UI_SURFACE_EXCEPTIONS as exc:
                st.error(str(exc))
    browser_settings, _, browser_error = _load_browser_defaults()
    with main_col:
        _render_guided_panel(
            "Service readiness",
            "This page shows whether the main external connections are present and where their configuration comes from, without exposing secret values.",
            tooltip=_tip(
                "Short plain-language description of the auth status page.",
                "Use this page when you want to check what is configured before running an external workflow.",
            ),
        )
        st.subheader("Presence and source status")
        _render_readonly_fields(
            [
                {
                    "label": "Drive auth mode",
                    "value": str(settings.drive_auth_mode or ""),
                    "help": _tip(
                        "Current Google Drive authentication mode loaded from configuration.",
                        "oauth_user expects local OAuth files, while service_account uses a service-account JSON file.",
                    ),
                },
                {
                    "label": "Google OAuth client",
                    "value": oauth_file_status_label(
                        path_mode=str(path_mode or ""),
                        selected_path=resolved_client_path,
                        configured_path=configured_client_path,
                    ),
                    "help": _tip(
                        "Whether the OAuth client JSON file exists at the selected path.",
                        "This must be present before Drive OAuth login can start.",
                    ),
                },
                {
                    "label": "Google OAuth token",
                    "value": oauth_file_status_label(
                        path_mode=str(path_mode or ""),
                        selected_path=resolved_token_path,
                        configured_path=configured_token_path,
                    ),
                    "help": _tip(
                        "Whether the OAuth token JSON file exists at the selected path.",
                        "It may be missing before the first login and present after a successful OAuth flow.",
                    ),
                },
                {
                    "label": "OpenAI API key",
                    "value": "Present in environment"
                    if os.getenv("OPENAI_API_KEY", "").strip()
                    else "Missing from environment",
                    "help": _tip(
                        "Whether an OpenAI API key is available to the app.",
                        "The actual secret value is never shown here.",
                    ),
                },
                {
                    "label": "OpenRouter API key",
                    "value": "Present in environment"
                    if os.getenv("OPENROUTER_API_KEY", "").strip()
                    else "Missing from environment",
                    "help": _tip(
                        "Whether an OpenRouter API key is available to the app.",
                        "The actual secret value is never shown here.",
                    ),
                },
                {
                    "label": "WordPress auth",
                    "value": (
                        "Present"
                        if publish_settings
                        and getattr(publish_settings.wp, "app_password", "")
                        else "Missing"
                    ),
                    "help": _tip(
                        "Whether the WordPress publishing credentials are available to the app.",
                        "The secret itself is not displayed here.",
                    ),
                },
                {
                    "label": "Browser identity profile",
                    "value": str(
                        getattr(browser_settings, "identity_config_path", "")
                        or "Unavailable"
                    ),
                    "help": _tip(
                        "Path to the browser download identity profile used for gated report forms.",
                        "This file stores non-secret identity fields such as contact details and form defaults.",
                    ),
                },
            ],
            columns=2,
            key_prefix="auth_access_status",
        )
        if browser_error:
            st.warning(browser_error)
    with detail_col:
        st.subheader("Current selection")
        _render_readonly_fields(
            [
                {
                    "label": "OAuth client path for next login",
                    "value": resolved_client_path or "Not set yet",
                    "help": _tip(
                        "OAuth client JSON path that will be used for the next login action.",
                        "Review this value before launching Drive OAuth Login.",
                    ),
                },
                {
                    "label": "OAuth token path for next login",
                    "value": resolved_token_path or "Not set yet",
                    "help": _tip(
                        "OAuth token JSON path that will be used or created during the next login action.",
                        "Review this value before launching Drive OAuth Login.",
                    ),
                },
            ],
            columns=1,
            key_prefix="auth_access_selection",
        )
        st.subheader("Last OAuth result")
        oauth_result = st.session_state.get("last_drive_oauth_result")
        if oauth_result is None:
            _render_empty_state(
                "No OAuth login has run in this session",
                "Run Drive OAuth Login to store the latest local result here.",
            )
        else:
            _render_payload_area(
                "Latest OAuth result",
                oauth_result.__dict__
                if hasattr(oauth_result, "__dict__")
                else oauth_result,
                help_text=_tip(
                    "Full structured result from the latest OAuth login in this session.",
                    "Use this when you need the raw metadata behind the most recent login flow.",
                ),
                key="auth_access_oauth_result",
                height=260,
            )


__all__ = [
    name
    for name in globals()
    if not name.startswith("__") and name not in {"annotations"}
]
