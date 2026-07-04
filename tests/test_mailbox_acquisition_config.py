from __future__ import annotations

import os
from unittest.mock import patch

from src.contracts.config import ConfigLoadRequest
from src.services.config_service import load_mailbox_acquisition_settings
from src.services.mailbox_acquisition_service import mailbox_provider_order


def test_load_mailbox_acquisition_settings_reads_yaml_and_env(
    tmp_path, run_context
) -> None:
    config_path = tmp_path / "app.yaml"
    config_path.write_text(
        """
schema_version: "1.0"
paths:
  output_dir: "./out"
mailbox_acquisition:
  provider: "imap"
  output_dir: "./mail-out"
  search_window_minutes: 45
  max_results: 7
  poll_timeout_seconds: 300
  poll_interval_seconds: 15
  imap_host: "imap.example.test"
  imap_port: 993
  imap_user: "reader@example.test"
  imap_mailbox: "Reports"
""",
        encoding="utf-8",
    )
    with patch.dict(os.environ, {"IMAP_PASS": "secret"}, clear=False):
        settings = load_mailbox_acquisition_settings(
            ConfigLoadRequest(schema_version="1.0", path=str(config_path)),
            run_context,
        )

    assert settings.provider == "imap"
    assert settings.output_dir.endswith("mail-out")
    assert settings.search_window_minutes == 45
    assert settings.max_results == 7
    assert settings.poll_timeout_seconds == 300
    assert settings.poll_interval_seconds == 15
    assert settings.imap_host == "imap.example.test"
    assert settings.imap_user == "reader@example.test"
    assert settings.imap_password == "secret"
    assert settings.imap_mailbox == "Reports"


def test_mailbox_provider_order_falls_back_from_gmail_to_configured_imap(
    tmp_path, run_context
) -> None:
    config_path = tmp_path / "app.yaml"
    config_path.write_text(
        """
schema_version: "1.0"
mailbox_acquisition:
  provider: "gmail"
  gmail_oauth_client_path: "client.json"
  gmail_oauth_token_path: "token.json"
  imap_host: "imap.example.test"
  imap_port: 993
  imap_user: "reader@example.test"
  imap_mailbox: "INBOX"
""",
        encoding="utf-8",
    )
    with patch.dict(os.environ, {"IMAP_PASS": "secret"}, clear=False):
        settings = load_mailbox_acquisition_settings(
            ConfigLoadRequest(schema_version="1.0", path=str(config_path)),
            run_context,
        )

    assert mailbox_provider_order(settings) == ["gmail", "imap"]


def test_mailbox_provider_order_auto_prefers_configured_imap(
    tmp_path, run_context
) -> None:
    config_path = tmp_path / "app.yaml"
    config_path.write_text(
        """
schema_version: "1.0"
mailbox_acquisition:
  provider: "auto"
  gmail_oauth_token_path: "token.json"
  imap_host: "imap.example.test"
  imap_port: 993
  imap_user: "reader@example.test"
  imap_mailbox: "INBOX"
""",
        encoding="utf-8",
    )
    with patch.dict(os.environ, {"IMAP_PASS": "secret"}, clear=False):
        settings = load_mailbox_acquisition_settings(
            ConfigLoadRequest(schema_version="1.0", path=str(config_path)),
            run_context,
        )

    assert mailbox_provider_order(settings) == ["imap", "gmail"]
