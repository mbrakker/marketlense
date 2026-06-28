from __future__ import annotations

from types import SimpleNamespace

from src.ui import settings_page


def test_build_settings_workspace_metrics_counts_missing_auth() -> None:
    config_doc = SimpleNamespace(payload={"ingest": {}, "publish": {}, "analysis": {}})
    metrics = settings_page.build_settings_workspace_metrics(
        config_doc=config_doc,
        asset_specs=[{"key": "category_mappings"}, {"key": "cover_styles"}],
        prompt_rows=[{"namespace": "publish"}, {"namespace": "analysis"}],
        auth_rows=[
            {"name": "OPENAI_API_KEY", "status": "present", "source": "env"},
            {"name": "WordPress credentials", "status": "missing", "source": "config"},
        ],
    )

    assert metrics == [
        {"label": "app.yaml keys", "value": "3", "delta": "structured form ready"},
        {
            "label": "Operational assets",
            "value": "2",
            "delta": "service-backed editors",
        },
        {"label": "Prompt namespaces", "value": "2", "delta": "system + user files"},
        {
            "label": "Auth issues",
            "value": "1",
            "delta": "resolve missing secrets/files",
        },
    ]


def test_build_settings_auth_rows_uses_file_service_boundary() -> None:
    requests = []

    def fake_file_exists(request, _ctx):
        requests.append(request)
        return SimpleNamespace(exists=request.path == "client.json")

    settings = SimpleNamespace(
        drive_auth_mode="oauth_user",
        google_oauth_client_path="client.json",
        google_oauth_token_path="token.json",
    )

    rows = settings_page.build_settings_auth_rows(
        settings=settings,
        publish_settings=None,
        file_exists_fn=fake_file_exists,
    )

    by_name = {row["name"]: row for row in rows}
    assert by_name["Google OAuth client"]["status"] == "present"
    assert by_name["Google OAuth token"]["status"] == "missing"
    assert [request.path for request in requests] == ["client.json", "token.json"]


def test_build_runtime_summary_prefers_available_publish_auth() -> None:
    settings = SimpleNamespace(
        openai_model="gpt-5.4",
        batch_limit=12,
        output_dir="out",
        state_db="state.sqlite",
        drive_auth_mode="oauth_user",
        google_oauth_client_path="google_oauth_client.json",
    )
    publish_settings = SimpleNamespace(
        wp=SimpleNamespace(app_password="app-pass", bearer_token="")
    )

    rows = settings_page.build_runtime_summary(
        settings=settings,
        publish_settings=publish_settings,
    )

    assert rows[0]["summary"] == "model=gpt-5.4 | batch_limit=12"
    assert rows[1]["summary"] == "output=out | state_db=state.sqlite"
    assert rows[2]["summary"] == "wordpress auth=application password"
    assert rows[3]["summary"] == (
        "auth_mode=oauth_user | oauth_client=google_oauth_client.json"
    )
