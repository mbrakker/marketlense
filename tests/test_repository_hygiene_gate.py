from __future__ import annotations

from datetime import date
from pathlib import Path

from scripts.ci.check_repository_hygiene import (
    HygieneAllowlistEntry,
    scan_tracked_paths,
    validate_dotenv_policy,
)


def test_repository_hygiene_rejects_runtime_secret_and_tmp_artifacts(
    tmp_path: Path,
) -> None:
    for relative in (
        "tmp_probe/result.json",
        "google_oauth_token.json",
        "coverage.xml",
        "logs/run.json",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

    violations = scan_tracked_paths(
        (
            "tmp_probe/result.json",
            "google_oauth_token.json",
            "coverage.xml",
            "logs/run.json",
        ),
        root=tmp_path,
        today=date(2026, 4, 25),
    )

    assert [item.path for item in violations] == [
        "tmp_probe/result.json",
        "google_oauth_token.json",
        "coverage.xml",
        "logs/run.json",
    ]
    assert all(item.reason for item in violations)


def test_repository_hygiene_allowlist_requires_unexpired_size_bound(
    tmp_path: Path,
) -> None:
    path = tmp_path / "tmp_fixture/result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    allowlist = (
        HygieneAllowlistEntry(
            pattern="tmp_fixture/*.json",
            owner="quality",
            reason="temporary test fixture",
            max_size_bytes=10,
            expires_on=date(2026, 5, 1),
        ),
    )

    assert (
        scan_tracked_paths(
            ("tmp_fixture/result.json",),
            root=tmp_path,
            allowlist=allowlist,
            today=date(2026, 4, 25),
        )
        == ()
    )
    assert scan_tracked_paths(
        ("tmp_fixture/result.json",),
        root=tmp_path,
        allowlist=allowlist,
        today=date(2026, 5, 2),
    )


def test_dotenv_policy_requires_ignore_and_safe_template(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text(".env\n!.env.example\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("OPENAI_API_KEY=\n", encoding="utf-8")

    assert validate_dotenv_policy(root=tmp_path, tracked_paths=(".env.example",)) == ()

    (tmp_path / ".env.example").write_text(
        "OPENAI_API_KEY=sk-examplevalue1234567890\n", encoding="utf-8"
    )
    violations = validate_dotenv_policy(root=tmp_path, tracked_paths=(".env",))
    assert {item.path for item in violations} == {".env", ".env.example"}
