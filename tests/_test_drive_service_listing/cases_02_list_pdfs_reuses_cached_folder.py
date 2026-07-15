# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_list_pdfs_reuses_cached_folder_scope_until_invalidated(
    external_boundary_mocks_only,
):
    folder_query_root = (
        "'root-folder' in parents and mimeType='application/vnd.google-apps.folder' "
        "and trashed=false"
    )
    folder_query_child_a = (
        "'child-a' in parents and mimeType='application/vnd.google-apps.folder' "
        "and trashed=false"
    )
    folder_query_child_b = (
        "'child-b' in parents and mimeType='application/vnd.google-apps.folder' "
        "and trashed=false"
    )
    pdf_query_root = (
        "'root-folder' in parents and mimeType='application/pdf' and trashed=false"
    )
    pdf_query_child_a = (
        "'child-a' in parents and mimeType='application/pdf' and trashed=false"
    )
    pdf_query_child_b = (
        "'child-b' in parents and mimeType='application/pdf' and trashed=false"
    )
    responses: dict[Any, dict] = {
        folder_query_root: {"files": [{"id": "child-a"}], "nextPageToken": None},
        folder_query_child_a: {"files": [], "nextPageToken": None},
        pdf_query_root: {"files": [{"id": "root-pdf"}], "nextPageToken": None},
        pdf_query_child_a: {"files": [{"id": "child-a-pdf"}], "nextPageToken": None},
    }
    fake_drive = _FakeDriveClient(responses)
    external_boundary_mocks_only.setattr(
        drive_service.Credentials,
        "from_service_account_file",
        staticmethod(lambda _sa_path, scopes: object()),
    )
    external_boundary_mocks_only.setattr(
        drive_service, "build", lambda *_args, **_kwargs: fake_drive
    )
    _reset_drive_caches()

    first = list(drive_service.list_pdfs(_request(), _ctx()))
    assert [file.file_id for file in first] == ["root-pdf", "child-a-pdf"]

    responses[folder_query_root] = {
        "files": [{"id": "child-a"}, {"id": "child-b"}],
        "nextPageToken": None,
    }
    responses[folder_query_child_b] = {"files": [], "nextPageToken": None}
    responses[pdf_query_child_b] = {
        "files": [{"id": "child-b-pdf"}],
        "nextPageToken": None,
    }

    second = list(drive_service.list_pdfs(_request(), _ctx()))
    assert [file.file_id for file in second] == ["root-pdf", "child-a-pdf"]

    removed = drive_service._invalidate_folder_scope_cache(folder_id="root-folder")
    third = list(drive_service.list_pdfs(_request(), _ctx()))

    assert removed == 1
    assert [file.file_id for file in third] == [
        "root-pdf",
        "child-a-pdf",
        "child-b-pdf",
    ]


def test_drive_client_cache_expires_and_evicts_oldest(external_boundary_mocks_only):
    created: list[object] = []
    timestamps = iter([0.0, 1.0, 2.0, 3.0, 4.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0])

    def _fake_build(
        service_name: str,
        version: str,
        http,
        cache_discovery: bool,
        static_discovery: bool,
    ):
        assert service_name == "drive"
        assert version == "v3"
        assert http is not None
        assert cache_discovery is False
        assert static_discovery is True
        client = object()
        created.append(client)
        return client

    external_boundary_mocks_only.setattr(
        drive_service.Credentials,
        "from_service_account_file",
        staticmethod(lambda _sa_path, scopes: object()),
    )
    external_boundary_mocks_only.setattr(drive_service, "build", _fake_build)
    external_boundary_mocks_only.setattr(
        drive_service.time, "monotonic", lambda: next(timestamps)
    )
    external_boundary_mocks_only.setattr(
        drive_service, "DRIVE_CLIENT_CACHE_TTL_SECONDS", 5.0
    )
    external_boundary_mocks_only.setattr(
        drive_service, "DRIVE_CLIENT_CACHE_MAX_ENTRIES", 2
    )
    _reset_drive_caches()

    ctx = _ctx()
    client_a_1 = drive_service._get_drive_client(
        auth_mode="service_account",
        service_account_path="sa-a.json",
        oauth_token_path=None,
        ctx=ctx,
    )
    client_a_2 = drive_service._get_drive_client(
        auth_mode="service_account",
        service_account_path="sa-a.json",
        oauth_token_path=None,
        ctx=ctx,
    )
    client_b_1 = drive_service._get_drive_client(
        auth_mode="service_account",
        service_account_path="sa-b.json",
        oauth_token_path=None,
        ctx=ctx,
    )
    client_c_1 = drive_service._get_drive_client(
        auth_mode="service_account",
        service_account_path="sa-c.json",
        oauth_token_path=None,
        ctx=ctx,
    )
    client_a_3 = drive_service._get_drive_client(
        auth_mode="service_account",
        service_account_path="sa-a.json",
        oauth_token_path=None,
        ctx=ctx,
    )
    client_b_2 = drive_service._get_drive_client(
        auth_mode="service_account",
        service_account_path="sa-b.json",
        oauth_token_path=None,
        ctx=ctx,
    )

    assert client_a_1 is client_a_2
    assert client_a_3 is not client_a_1
    assert client_b_2 is not client_b_1
    assert client_c_1 is not client_b_1
    assert len(created) == 5


__all__ = [
    "test_list_pdfs_reuses_cached_folder_scope_until_invalidated",
    "test_drive_client_cache_expires_and_evicts_oldest",
]
