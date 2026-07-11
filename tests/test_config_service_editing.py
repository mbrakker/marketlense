from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import yaml

from src.contracts.browser_download import (
    BrowserDownloadIdentityFieldUpsertRequest,
    BrowserDownloadRequiredSelectEvidence,
    BrowserDownloadRequiredSelectOverrideRequest,
)
from src.contracts.config import (
    AppConfigReadRequest,
    AppConfigWriteRequest,
)
from src.contracts.run_context import RunContext
from src.services.config_service import (
    read_app_config,
    upsert_browser_download_identity_fields,
    upsert_browser_download_required_select_overrides,
    write_app_config,
)
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _write_app_config_fixture(tmp_path: Path) -> tuple[Path, Path]:
    identity_path = tmp_path / "browser_download_identity.yaml"
    identity_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "fields": [
                    {
                        "schema_version": "1.0",
                        "key": "work_email",
                        "label": "Work email",
                        "value": "ops@example.com",
                        "aliases": ["email"],
                    },
                    {
                        "schema_version": "1.0",
                        "key": "company",
                        "label": "Company",
                        "value": "Market Lense",
                        "aliases": ["business"],
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "app.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "paths": {
                    "output_dir": str(tmp_path / "out"),
                    "cache_dir": str(tmp_path / "cache"),
                    "state_db": str(tmp_path / "state" / "index.sqlite"),
                    "reports_db": str(tmp_path / "state" / "reports.sqlite"),
                },
                "ingest": {
                    "google_sa_path": str(tmp_path / "sa.json"),
                    "gdrive_folder_id": "folder",
                    "openai_model": "gpt-5",
                },
                "browser_download": {
                    "identity_config_path": str(identity_path),
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return config_path, identity_path


def test_read_and_write_app_config_round_trip(tmp_path: Path) -> None:
    config_path, _ = _write_app_config_fixture(tmp_path)

    read_response = read_app_config(
        AppConfigReadRequest(schema_version="1.0", path=str(config_path)),
        _ctx(),
    )

    updated_payload = yaml.safe_load(read_response.content)
    updated_payload["ingest"]["batch_limit"] = 37
    write_response = write_app_config(
        AppConfigWriteRequest(
            schema_version="1.0",
            path=str(config_path),
            content=yaml.safe_dump(updated_payload, sort_keys=False),
            make_backup=True,
        ),
        _ctx(),
    )

    assert "ingest" in read_response.payload
    assert read_response.size_bytes > 0
    assert read_response.modified_utc is not None
    assert write_response.bytes_written > 0
    assert "ingest" in write_response.top_level_keys
    assert write_response.backup_path
    assert Path(str(write_response.backup_path)).exists()
    assert (
        yaml.safe_load(config_path.read_text(encoding="utf-8"))["ingest"]["batch_limit"]
        == 37
    )


def test_app_config_editor_uses_env_bootstrap_path_when_request_path_blank(
    tmp_path: Path,
) -> None:
    config_path, _ = _write_app_config_fixture(tmp_path)

    with patch.dict(
        os.environ,
        {"MARKET_LENSE_CONFIG_PATH": str(config_path)},
        clear=True,
    ):
        read_response = read_app_config(
            AppConfigReadRequest(schema_version="1.0", path=""),
            _ctx(),
        )
        write_response = write_app_config(
            AppConfigWriteRequest(
                schema_version="1.0",
                path="",
                content=read_response.content,
                make_backup=False,
            ),
            _ctx(),
        )

    assert Path(read_response.path) == config_path.resolve()
    assert Path(write_response.path) == config_path.resolve()


def test_read_app_config_missing_file_raises_not_found_code(tmp_path: Path) -> None:
    with patch.dict(os.environ, {}, clear=True):
        missing_path = tmp_path / "missing.yaml"
        try:
            read_app_config(
                AppConfigReadRequest(schema_version="1.0", path=str(missing_path)),
                _ctx(),
            )
        except AppError as exc:
            assert exc.code == "config_file_not_found"
        else:  # pragma: no cover
            raise AssertionError("Expected AppError")


def test_read_app_config_invalid_yaml_raises_invalid_code(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_path.write_text("schema_version: [1,\n", encoding="utf-8")

    try:
        read_app_config(
            AppConfigReadRequest(schema_version="1.0", path=str(config_path)),
            _ctx(),
        )
    except AppError as exc:
        assert exc.code == "config_yaml_invalid"
    else:  # pragma: no cover
        raise AssertionError("Expected AppError")


def test_write_app_config_rejects_non_mapping_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_path.write_text("schema_version: '1.0'\n", encoding="utf-8")

    try:
        write_app_config(
            AppConfigWriteRequest(
                schema_version="1.0",
                path=str(config_path),
                content="- one\n- two\n",
                make_backup=False,
            ),
            _ctx(),
        )
    except AppError as exc:
        assert exc.code == "config_yaml_root_invalid"
        assert "mapping" in str(exc).lower()
    else:  # pragma: no cover
        raise AssertionError("Expected AppError")


def test_upsert_browser_download_identity_fields_adds_and_filters_keys(
    tmp_path: Path,
) -> None:
    _, identity_path = _write_app_config_fixture(tmp_path)

    response = upsert_browser_download_identity_fields(
        BrowserDownloadIdentityFieldUpsertRequest(
            schema_version="1.0",
            path=str(identity_path),
            encountered_form_fields=[
                "Submit",
                "Download report",
                "Download Now (button, type=submit)",
                "reCAPTCHA notice (visible)",
                "Opt in for Marketing Communications (checkbox)",
                "submit - input type=submit (index=110)",
                "newsletter opt-in / 'Yes, send me updates!' - checkbox (visible)",
                "firstname (name=firstname) - input (index=32)",
                "I work for a(n) (select)",
                "Any questions or specific topics you'd like to see? (textarea)",
                "Email (C_EmailAddress)",
                "Agreement / Privacy & Terms (required consent checkbox)",
                "Complete the form to download Mintel's Predictive Insights",
                "*all fields are required",
                "Loading...",
                "Download insights (CTA visible)",
                "Business Email Address (name=emailaddress1)",
                "Email (Business email)",
                "Company Size (name=hisol_companysizeoptionset)",
                "- Enterprise (1,000+ Employees)",
                "- Food and Drink",
                "- Select...",
                "- ***REDACTED***",
                "Company Size (options shown: Enterprise (1,000+ Employees); Large (201-999 Employees))",
                "Username (input name=username) - visible shadow input (index 8)",
                "Password (input name=password) - visible shadow input (index 9)",
                "Remember Me (checkbox name=remember) - visible (index 15)",
                "Log In (link/button) - visible CTA (index 19)",
                "Forgot Username / Password (link) - visible CTA (index 20)",
                "Budget Range",
                "Name",
                "Budget Range",
            ],
        ),
        _ctx(),
    )

    payload = yaml.safe_load(identity_path.read_text(encoding="utf-8"))
    assert response.added_field_keys == ["budget_range", "name"]
    assert response.total_fields == 4
    assert [field["key"] for field in payload["fields"]] == [
        "work_email",
        "company",
        "budget_range",
        "name",
    ]


def test_required_select_evidence_writes_safe_host_override_idempotently(
    tmp_path: Path,
) -> None:
    _, identity_path = _write_app_config_fixture(tmp_path)

    request = BrowserDownloadRequiredSelectOverrideRequest(
        schema_version="1.0",
        path=str(identity_path),
        evidence=[
            BrowserDownloadRequiredSelectEvidence(
                schema_version="1.0",
                host="go.example.com",
                url="https://go.example.com/report",
                field_label="Company Size",
                field_name="company_size",
                options=[
                    "Please select",
                    "1-10 employees",
                    "11-50 employees",
                    "51-200 employees",
                ],
                classifier_confidence=0.94,
            ),
            BrowserDownloadRequiredSelectEvidence(
                schema_version="1.0",
                host="go.example.com",
                url="https://go.example.com/report",
                field_label="Job Role",
                field_name="job_role",
                options=["CEO", "Marketing Manager", "Student"],
                classifier_confidence=0.96,
            ),
        ],
        approved_defaults={"company_size": "11-50 employees"},
    )

    first = upsert_browser_download_required_select_overrides(request, _ctx())
    second = upsert_browser_download_required_select_overrides(request, _ctx())
    payload = yaml.safe_load(identity_path.read_text(encoding="utf-8"))

    assert first.applied_count == 1
    assert first.refused_count == 1
    assert first.proposals[0].status == "applied"
    assert first.proposals[0].semantic_family == "company_size"
    assert first.proposals[1].status == "refused_sensitive_field"
    assert second.applied_count == 0
    override = payload["publisher_overrides"][0]
    assert override["host_pattern"] == "go.example.com"
    assert override["field_values"][0]["key"] == "company_size"
    assert override["field_values"][0]["value"] == "11-50 employees"
    assert override["field_values"][0]["option_aliases"] == ["11-50 employees"]


def test_required_select_evidence_matches_existing_identity_fact(tmp_path: Path) -> None:
    _, identity_path = _write_app_config_fixture(tmp_path)
    payload = yaml.safe_load(identity_path.read_text(encoding="utf-8"))
    payload["fields"].append(
        {
            "schema_version": "1.0",
            "key": "country",
            "label": "Country",
            "value": "United States",
            "aliases": ["Country/Region"],
            "option_aliases": [],
        }
    )
    identity_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    response = upsert_browser_download_required_select_overrides(
        BrowserDownloadRequiredSelectOverrideRequest(
            schema_version="1.0",
            path=str(identity_path),
            evidence=[
                BrowserDownloadRequiredSelectEvidence(
                    schema_version="1.0",
                    host="forms.example.com",
                    url="https://forms.example.com/a",
                    field_label="Country/Region",
                    field_name="Country",
                    options=["Select...", "United States", "Canada"],
                    classifier_confidence=0.91,
                )
            ],
            approved_defaults={},
        ),
        _ctx(),
    )

    payload = yaml.safe_load(identity_path.read_text(encoding="utf-8"))
    assert response.applied_count == 1
    assert response.proposals[0].match_source == "identity_fact"
    assert payload["publisher_overrides"][0]["field_values"][0]["key"] == "country"
