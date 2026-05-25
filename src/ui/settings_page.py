from __future__ import annotations

import difflib
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

import streamlit as st
import yaml

from src.contracts.config import ConfigLoadRequest
from src.contracts.config_assets import (
    ConfigAssetReadRequest,
    ConfigAssetWriteRequest,
)
from src.contracts.prompts import PromptNamespaceListRequest
from src.services.config_asset_service import read_config_asset, write_config_asset
from src.services.config_service import load_browser_download_settings
from src.services.prompt_service import list_prompt_namespaces
from src.ui import state as ui_state
from src.ui._streamlit_pages.read_models import _invalidate_dashboard_read_models
from src.ui._streamlit_pages.runtime import (
    _try_load_publish_settings,
    _try_load_settings,
    _try_read_app_config,
    _try_write_app_config,
)
from src.ui._streamlit_pages.structured_config import render_structured_config_form
from src.ui.common import (
    UI_SURFACE_EXCEPTIONS,
    _append_terminal,
    _as_utc,
    _chip_html,
    _ctx,
    _page_shell,
    _tip,
)


def _refresh_runtime_state() -> None:
    settings, settings_error = _try_load_settings()
    publish_settings, publish_error = _try_load_publish_settings()
    st.session_state[ui_state.APP_SETTINGS_KEY] = settings
    st.session_state[ui_state.SETTINGS_ERROR_KEY] = settings_error
    st.session_state[ui_state.PUBLISH_SETTINGS_KEY] = publish_settings
    st.session_state[ui_state.PUBLISH_ERROR_KEY] = publish_error


def _build_asset_specs(
    settings: Any | None, browser_settings: Any | None
) -> list[dict[str, str]]:
    if settings is None:
        return []
    browser_identity_path = ""
    if browser_settings is not None:
        browser_identity_path = str(browser_settings.identity_config_path or "")
    specs = [
        {
            "key": "category_mappings",
            "label": "Category mappings",
            "path": settings.category_mapping_path,
            "format": "yaml",
            "root_type": "mapping",
            "description": "Taxonomy and recategorization source-of-truth used by ingest and publish flows.",
        },
        {
            "key": "cover_styles",
            "label": "Cover styles",
            "path": settings.cover_style_path,
            "format": "yaml",
            "root_type": "mapping",
            "description": "Cover rendering style config used for PNG asset generation.",
        },
        {
            "key": "browser_download_identity",
            "label": "Browser download identity",
            "path": browser_identity_path,
            "format": "yaml",
            "root_type": "mapping",
            "description": "Browser form identity fields and delivery emails for report acquisition.",
        },
        {
            "key": "publisher_snapshot",
            "label": "Publisher snapshot",
            "path": settings.publisher_profiles_path,
            "format": "json",
            "root_type": "any",
            "description": "Publisher inventory snapshot used by publisher sync and discovery tooling.",
        },
    ]
    return [spec for spec in specs if str(spec["path"]).strip()]


def build_settings_workspace_metrics(
    *,
    config_doc: Any | None,
    asset_specs: list[dict[str, str]],
    prompt_rows: list[dict[str, Any]],
    auth_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    prompt_count = len(prompt_rows)
    missing_auth = len([row for row in auth_rows if row["status"] == "missing"])
    key_count = 0
    if config_doc is not None and isinstance(config_doc.payload, dict):
        key_count = len(config_doc.payload)
    return [
        {
            "label": "app.yaml keys",
            "value": str(key_count),
            "delta": "structured form ready",
        },
        {
            "label": "Operational assets",
            "value": str(len(asset_specs)),
            "delta": "service-backed editors",
        },
        {
            "label": "Prompt namespaces",
            "value": str(prompt_count),
            "delta": "system + user files",
        },
        {
            "label": "Auth issues",
            "value": str(missing_auth),
            "delta": "resolve missing secrets/files"
            if missing_auth
            else "all required sources present",
        },
    ]


def build_settings_auth_rows(
    *,
    settings: Any | None,
    publish_settings: Any | None,
) -> list[dict[str, str]]:
    return [
        {
            "name": "Drive auth mode",
            "status": str(getattr(settings, "drive_auth_mode", "unknown") or "unknown"),
            "source": "app.yaml",
        },
        {
            "name": "Google OAuth client",
            "status": (
                "present"
                if settings
                and settings.google_oauth_client_path
                and Path(str(settings.google_oauth_client_path)).exists()
                else "missing"
            ),
            "source": str(settings.google_oauth_client_path or "") if settings else "",
        },
        {
            "name": "Google OAuth token",
            "status": (
                "present"
                if settings
                and settings.google_oauth_token_path
                and Path(str(settings.google_oauth_token_path)).exists()
                else "missing"
            ),
            "source": str(settings.google_oauth_token_path or "") if settings else "",
        },
        {
            "name": "OPENAI_API_KEY",
            "status": "present"
            if os.getenv("OPENAI_API_KEY", "").strip()
            else "missing",
            "source": "env",
        },
        {
            "name": "OPENROUTER_API_KEY",
            "status": "present"
            if os.getenv("OPENROUTER_API_KEY", "").strip()
            else "missing",
            "source": "env",
        },
        {
            "name": "WordPress credentials",
            "status": (
                "present"
                if publish_settings
                and (
                    publish_settings.wp.app_password or publish_settings.wp.bearer_token
                )
                else "missing"
            ),
            "source": "config-service",
        },
    ]


def build_settings_env_override_rows(env_keys: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for key in env_keys:
        rows.append(
            {
                "key": key,
                "source": "env" if os.getenv(key, "").strip() else "yaml/default",
            }
        )
    return rows


def build_runtime_summary(
    *,
    settings: Any | None,
    publish_settings: Any | None,
) -> list[dict[str, str]]:
    wp_mode = "unavailable"
    if publish_settings is not None:
        if publish_settings.wp.app_password:
            wp_mode = "application password"
        elif publish_settings.wp.bearer_token:
            wp_mode = "bearer token"
        else:
            wp_mode = "missing"
    return [
        {
            "area": "Ingest",
            "summary": (
                f"model={getattr(settings, 'openai_model', 'n/a')} | "
                f"batch_limit={getattr(settings, 'batch_limit', 'n/a')}"
            ),
        },
        {
            "area": "Storage",
            "summary": (
                f"output={getattr(settings, 'output_dir', '')} | "
                f"state_db={getattr(settings, 'state_db', '')}"
            ),
        },
        {
            "area": "Publishing",
            "summary": f"wordpress auth={wp_mode}",
        },
        {
            "area": "Drive",
            "summary": (
                f"auth_mode={getattr(settings, 'drive_auth_mode', 'n/a')} | "
                f"oauth_client={str(getattr(settings, 'google_oauth_client_path', '') or '')}"
            ),
        },
    ]


def _try_read_asset(
    *,
    path: str,
    format_name: str,
    root_type: str,
) -> tuple[Any | None, str | None]:
    try:
        response = read_config_asset(
            ConfigAssetReadRequest(
                schema_version="1.0",
                path=path,
                format=format_name,
                expected_root_type=root_type,
            ),
            _ctx("read_config_asset"),
        )
    except UI_SURFACE_EXCEPTIONS as exc:
        return None, str(exc)
    return response, None


def _try_write_asset(
    *,
    path: str,
    format_name: str,
    content: str,
    root_type: str,
    make_backup: bool,
) -> tuple[Any | None, str | None]:
    try:
        response = write_config_asset(
            ConfigAssetWriteRequest(
                schema_version="1.0",
                path=path,
                format=format_name,
                content=content,
                expected_root_type=root_type,
                make_backup=make_backup,
            ),
            _ctx("write_config_asset"),
        )
    except UI_SURFACE_EXCEPTIONS as exc:
        return None, str(exc)
    return response, None


def _render_diff(previous: str, current: str, *, label: str) -> None:
    if previous == current:
        st.caption(f"{label} is in sync with disk.")
        return
    diff = "\n".join(
        difflib.unified_diff(
            previous.splitlines(),
            current.splitlines(),
            fromfile="disk",
            tofile="editor",
            lineterm="",
        )
    )
    if not diff.strip():
        st.caption(f"{label} has whitespace-only differences.")
        return
    st.code(diff, language="diff")


def _render_asset_editor(
    *,
    spec: dict[str, str],
    state_prefix: str,
    save_notice_prefix: str,
) -> None:
    response, error = _try_read_asset(
        path=spec["path"],
        format_name=spec["format"],
        root_type=spec["root_type"],
    )
    if error:
        st.error(f"Unable to load {spec['label']}: {error}")
        return
    assert response is not None

    editor_key = f"{state_prefix}:editor:{spec['key']}"
    saved_key = f"{state_prefix}:saved:{spec['key']}"
    if editor_key not in st.session_state:
        st.session_state[editor_key] = response.content
    if saved_key not in st.session_state:
        st.session_state[saved_key] = response.content

    metrics = st.columns(3)
    metrics[0].metric("Size", f"{response.size_bytes:,} bytes")
    metrics[1].metric("Modified (UTC)", _as_utc(response.modified_utc) or "n/a")
    metrics[2].metric("SHA-256", response.sha256[:12])
    st.caption(spec["description"])
    st.code(response.path)

    preview_tab, editor_tab = st.tabs(["Structured preview", "Raw editor"])
    with preview_tab:
        if response.payload is None:
            st.caption("No decoded structured payload for this asset.")
        else:
            st.json(response.payload)
    with editor_tab:
        editor_text = st.text_area(
            f"{spec['label']} editor",
            key=editor_key,
            height=420,
            help=_tip(
                "Raw editor for the selected config asset.",
                "Edit the file here, review the diff, then save through the config-asset service.",
            ),
            label_visibility="collapsed",
        )
        unsaved = editor_text != st.session_state.get(saved_key, "")
        top_cols = st.columns([1.15, 1.15, 2.7])
        with top_cols[0]:
            save_clicked = st.button(
                f"Save {spec['label']}",
                key=f"{state_prefix}:save:{spec['key']}",
                type="primary",
                width="stretch",
            )
        with top_cols[1]:
            make_backup = st.toggle(
                "Backup",
                key=f"{state_prefix}:backup:{spec['key']}",
                value=True,
                help=_tip(
                    "Create a timestamped backup before overwriting the asset.",
                    "Leave enabled for most edits.",
                ),
            )
        with top_cols[2]:
            if unsaved:
                st.warning("Unsaved changes detected.")
            else:
                st.success("Editor is in sync with disk.")
        with st.expander("Diff vs disk", expanded=unsaved):
            _render_diff(st.session_state[saved_key], editor_text, label=spec["label"])
        if save_clicked:
            write_response, write_error = _try_write_asset(
                path=spec["path"],
                format_name=spec["format"],
                content=editor_text,
                root_type=spec["root_type"],
                make_backup=bool(make_backup),
            )
            if write_error:
                st.error(f"Save failed: {write_error}")
                return
            assert write_response is not None
            refreshed, refresh_error = _try_read_asset(
                path=spec["path"],
                format_name=spec["format"],
                root_type=spec["root_type"],
            )
            if refreshed is not None and not refresh_error:
                st.session_state[editor_key] = refreshed.content
                st.session_state[saved_key] = refreshed.content
            else:
                st.session_state[saved_key] = editor_text
            _invalidate_dashboard_read_models(st.session_state, reason="settings")
            _refresh_runtime_state()
            _append_terminal(
                f"{spec['label']} saved ({write_response.bytes_written} bytes)"
            )
            notice_key = (
                save_notice_prefix
                if save_notice_prefix == "prompt_editor_notice"
                else f"{save_notice_prefix}:{spec['key']}"
            )
            st.session_state[notice_key] = f"Saved `{write_response.path}`" + (
                f" with backup `{write_response.backup_path}`."
                if write_response.backup_path
                else "."
            )
            st.rerun()


def render_settings_and_prompts(
    settings: Any | None,
    publish_settings: Any | None,
    publish_error: str | None,
    settings_error: str | None = None,
) -> None:
    clicked, filters, main_col, detail_col = _page_shell(
        "Settings & Prompts",
        status_label="Config Error" if settings_error else "Config Studio",
        status_level="error" if settings_error else "success",
        primary_action="Reload From Disk",
        primary_help=_tip(
            "Reload editor content from disk and discard unsaved edits.",
            "Use after external file changes or a failed validation attempt.",
        ),
        primary_key="reload_control_panel_config",
    )
    with filters:
        st.caption(
            "Full control of runtime YAML, operational assets, prompt files, and auth visibility through service-backed editors."
        )

    config_doc, config_error = _try_read_app_config()
    editor_key = "app_yaml_editor_text"
    saved_key = "app_yaml_saved_text"
    if config_doc and editor_key not in st.session_state:
        st.session_state[editor_key] = config_doc.content
    if config_doc and saved_key not in st.session_state:
        st.session_state[saved_key] = config_doc.content
    if clicked and config_doc:
        st.session_state[editor_key] = config_doc.content
        st.session_state[saved_key] = config_doc.content
        st.session_state["app_yaml_notice"] = "Reloaded app.yaml from disk."
    elif clicked and config_error:
        st.session_state["app_yaml_notice"] = f"Reload failed: {config_error}"

    prompt_rows: list[dict[str, Any]] = []
    prompt_error = None
    try:
        prompt_namespaces = list_prompt_namespaces(
            PromptNamespaceListRequest(
                schema_version="1.0",
                reload_if_changed=True,
                force_reload=False,
            ),
            _ctx("prompt_namespaces"),
        )
        prompt_rows = [asdict(item) for item in prompt_namespaces.namespaces]
    except UI_SURFACE_EXCEPTIONS as exc:
        prompt_error = str(exc)

    browser_settings = None
    browser_settings_error = None
    try:
        browser_settings = load_browser_download_settings(
            ConfigLoadRequest(schema_version="1.0", path=""),
            _ctx("load_browser_download_settings"),
        )
    except UI_SURFACE_EXCEPTIONS as exc:
        browser_settings_error = str(exc)

    sanitized_settings: dict[str, Any]
    if settings is not None:
        sanitized_settings = asdict(settings)
        sanitized_settings["openai_api_key"] = "***REDACTED***"
    else:
        sanitized_settings = {
            "error": settings_error or "ingest settings unavailable",
        }

    if publish_settings is not None:
        publish_snapshot = asdict(publish_settings)
        if publish_snapshot.get("wp"):
            publish_snapshot["wp"]["app_password"] = (
                "***REDACTED***" if publish_snapshot["wp"].get("app_password") else None
            )
            publish_snapshot["wp"]["bearer_token"] = (
                "***REDACTED***" if publish_snapshot["wp"].get("bearer_token") else None
            )
    else:
        publish_snapshot = {
            "error": publish_error or "publish settings unavailable",
        }

    asset_specs = _build_asset_specs(settings, browser_settings)
    auth_rows = build_settings_auth_rows(
        settings=settings,
        publish_settings=publish_settings,
    )
    env_keys = [
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        "GDRIVE_FOLDER_ID",
        "OPENAI_MODEL",
        "OPENAI_TIMEOUT_SECONDS",
        "WP_SITE_URL",
        "WP_USERNAME",
        "WP_APP_PASSWORD",
        "WP_BEARER_TOKEN",
        "OUTPUT_DIR",
        "CACHE_DIR",
        "STATE_DB",
        "REPORTS_DB",
    ]
    env_override_rows = build_settings_env_override_rows(env_keys)

    if "app_yaml_notice" in st.session_state:
        st.info(str(st.session_state.pop("app_yaml_notice")))
    for spec in asset_specs:
        notice_key = f"asset_notice:{spec['key']}"
        if notice_key in st.session_state:
            st.info(str(st.session_state.pop(notice_key)))
    if "prompt_editor_notice" in st.session_state:
        st.info(str(st.session_state.pop("prompt_editor_notice")))

    with main_col:
        if settings_error:
            st.error(f"Runtime settings validation failed: {settings_error}")
        if config_error:
            st.error(f"Unable to load app.yaml: {config_error}")

        form_payload = config_doc.payload if config_doc else {}
        form_payload_source = "disk"
        form_payload_error = ""
        editor_candidate = str(st.session_state.get(editor_key, "") or "")
        if editor_candidate.strip():
            try:
                parsed_editor_payload = yaml.safe_load(editor_candidate) or {}
                if isinstance(parsed_editor_payload, dict):
                    form_payload = parsed_editor_payload
                    form_payload_source = "yaml editor"
                else:
                    form_payload_error = "Current YAML editor root is not a mapping; structured form is using disk content."
            except yaml.YAMLError:
                form_payload_error = "Current YAML editor is invalid; structured form is using disk content."

        with st.container(horizontal=True):
            for metric in build_settings_workspace_metrics(
                config_doc=config_doc,
                asset_specs=asset_specs,
                prompt_rows=prompt_rows,
                auth_rows=auth_rows,
            ):
                st.metric(
                    metric["label"],
                    metric["value"],
                    metric["delta"],
                    border=True,
                )

        workspace = st.segmented_control(
            "Workspace",
            options=["Common", "Assets", "Prompts", "Advanced"],
            default="Common",
            help=_tip(
                "Switch between the everyday operator flow, operational assets, prompt editing, and the raw advanced editor.",
                "Start with Common for structured app.yaml changes and move to Advanced only for raw file edits.",
            ),
        )
        if workspace == "Common":
            with st.container(border=True):
                st.subheader("Common controls")
                st.caption(
                    f"Form source: {form_payload_source}. Use this structured editor for routine operator changes without dropping to raw YAML."
                )
                if form_payload_error:
                    st.warning(form_payload_error)
                render_structured_config_form(form_payload, editor_key=editor_key)
            with st.container(border=True):
                left, right = st.columns(2, gap="large")
                with left:
                    st.subheader("Runtime summary")
                    st.dataframe(
                        build_runtime_summary(
                            settings=settings,
                            publish_settings=publish_settings,
                        ),
                        width="stretch",
                        hide_index=True,
                        column_config={
                            "area": "Area",
                            "summary": st.column_config.TextColumn(
                                "Summary", width="large"
                            ),
                        },
                    )
                with right:
                    st.subheader("Auth status")
                    st.dataframe(
                        auth_rows,
                        width="stretch",
                        hide_index=True,
                    )
        elif workspace == "Assets":
            with st.container(border=True):
                st.subheader("Operational assets")
                if not asset_specs:
                    st.info(
                        "Operational asset editors become available once app.yaml validates and runtime settings load."
                    )
                else:
                    selected_asset_key = st.selectbox(
                        "Asset",
                        options=[spec["key"] for spec in asset_specs],
                        format_func=lambda key: next(
                            spec["label"] for spec in asset_specs if spec["key"] == key
                        ),
                        help=_tip(
                            "Choose which service-backed operational asset to edit.",
                            "Select browser download identity to update form-fill values for acquisition routes.",
                        ),
                    )
                    selected_asset = next(
                        spec
                        for spec in asset_specs
                        if spec["key"] == selected_asset_key
                    )
                    _render_asset_editor(
                        spec=selected_asset,
                        state_prefix="config_asset",
                        save_notice_prefix="asset_notice",
                    )
        elif workspace == "Prompts":
            with st.container(border=True):
                st.subheader("Prompt workspace")
                if prompt_error:
                    st.error(f"Prompt namespace load failed: {prompt_error}")
                elif not prompt_rows:
                    st.caption("No prompt namespaces discovered.")
                else:
                    namespace_names = [row["namespace"] for row in prompt_rows]
                    selected_namespace = st.selectbox(
                        "Prompt namespace",
                        options=namespace_names,
                        help=_tip(
                            "Choose a prompt namespace to inspect and edit its system/user YAML files.",
                            "Select publisher_inventory/discovery to adjust discovery prompt behavior.",
                        ),
                    )
                    selected_prompt_row = next(
                        row
                        for row in prompt_rows
                        if row["namespace"] == selected_namespace
                    )
                    prompt_kind = st.segmented_control(
                        "Prompt file",
                        options=["system", "user"],
                        default="system",
                        help=_tip(
                            "Switch between system and user prompt files inside the selected namespace.",
                            "Edit system.yaml for instruction-level changes and user.yaml for template wording.",
                        ),
                    )
                    with st.expander("Prompt registry table"):
                        st.dataframe(prompt_rows, width="stretch", hide_index=True)
                    prompt_path = str(selected_prompt_row[f"{prompt_kind}_path"])
                    st.caption(
                        f"{prompt_kind}.yaml | sha256={selected_prompt_row[f'{prompt_kind}_sha256'][:12]}"
                    )
                    _render_asset_editor(
                        spec={
                            "key": f"{selected_namespace}:{prompt_kind}",
                            "label": f"{selected_namespace} / {prompt_kind}.yaml",
                            "path": prompt_path,
                            "format": "yaml",
                            "root_type": "mapping",
                            "description": "Prompt file editor with service-backed validation and diff against disk.",
                        },
                        state_prefix="prompt_editor",
                        save_notice_prefix="prompt_editor_notice",
                    )
        else:
            with st.container(border=True):
                st.subheader("Advanced editor")
                st.caption(
                    "Use the raw app.yaml editor for changes that do not map cleanly onto the structured form."
                )
                if editor_key not in st.session_state:
                    st.session_state[editor_key] = (
                        config_doc.content if config_doc else ""
                    )
                if saved_key not in st.session_state:
                    st.session_state[saved_key] = st.session_state.get(editor_key, "")
                editor_text = st.text_area(
                    "app.yaml",
                    key=editor_key,
                    height=640,
                    help=_tip(
                        "Full app.yaml editor.",
                        "Edit any key here, review the diff, then save through the config service.",
                    ),
                )
                unsaved = editor_text != st.session_state.get(saved_key, "")
                action_cols = st.columns([1.15, 1.15, 2.7])
                with action_cols[0]:
                    save_clicked = st.button(
                        "Save app.yaml",
                        type="primary",
                        width="stretch",
                    )
                with action_cols[1]:
                    make_backup = st.toggle(
                        "Backup",
                        key="app_yaml_make_backup",
                        value=True,
                        help=_tip(
                            "Create a timestamped .bak before overwriting app.yaml.",
                            "Leave enabled for normal config edits.",
                        ),
                    )
                with action_cols[2]:
                    if unsaved:
                        st.warning("Unsaved changes detected.")
                    else:
                        st.success("Editor is in sync with disk.")
                with st.expander("Diff vs disk", expanded=unsaved):
                    _render_diff(
                        st.session_state[saved_key], editor_text, label="app.yaml"
                    )
                if save_clicked:
                    save_response, save_error = _try_write_app_config(
                        editor_text,
                        make_backup=bool(make_backup),
                    )
                    if save_error:
                        st.error(f"Save failed: {save_error}")
                    elif save_response is None:
                        st.error("Save failed: empty response from config service.")
                    else:
                        refreshed_doc, refresh_error = _try_read_app_config()
                        if refreshed_doc and not refresh_error:
                            st.session_state[editor_key] = refreshed_doc.content
                            st.session_state[saved_key] = refreshed_doc.content
                        else:
                            st.session_state[saved_key] = editor_text
                        _invalidate_dashboard_read_models(
                            st.session_state, reason="settings"
                        )
                        _refresh_runtime_state()
                        _append_terminal(
                            f"app.yaml saved ({save_response.bytes_written} bytes)"
                        )
                        st.success(
                            f"Saved `{save_response.path}`"
                            + (
                                f" with backup `{save_response.backup_path}`."
                                if save_response.backup_path
                                else "."
                            )
                        )
                        st.rerun()
            with st.container(border=True):
                st.subheader("Resolved settings")
                st.json({"ingest": sanitized_settings, "publish": publish_snapshot})
                if config_doc:
                    with st.expander("Top-level app.yaml keys"):
                        st.code(
                            "\n".join(str(key) for key in config_doc.payload.keys())
                        )

    with detail_col:
        with st.container(border=True):
            st.subheader("Config file")
            if config_doc is not None:
                st.metric("Size", f"{config_doc.size_bytes:,} bytes")
                st.metric("Modified (UTC)", _as_utc(config_doc.modified_utc) or "n/a")
                st.code(config_doc.path)
            else:
                st.caption("app.yaml metadata unavailable.")

        with st.container(border=True):
            st.subheader("Auth & secret status")
            st.dataframe(auth_rows, width="stretch", hide_index=True)
            if browser_settings is not None:
                st.caption("Browser download identity path")
                st.code(browser_settings.identity_config_path)
            elif browser_settings_error:
                st.warning(browser_settings_error)

        with st.container(border=True):
            st.subheader("Env override badges")
            for row in env_override_rows:
                level = "success" if row["source"] == "env" else "info"
                st.markdown(
                    f"{row['key']} {_chip_html(row['source'].upper(), level)}",
                    unsafe_allow_html=True,
                )

        with st.container(border=True):
            st.subheader("Operator guidance")
            st.caption(
                "Use `Common` for routine runtime changes, `Assets` for operational YAML/JSON files, `Prompts` for prompt content, and `Advanced` only when you need the raw editor."
            )
