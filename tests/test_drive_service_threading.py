import threading
from dataclasses import FrozenInstanceError

import pytest

from src.contracts.run_context import RunContext
from src.services import drive_service


def test_drive_credential_resolution_is_immutable_value() -> None:
    resolution = drive_service._DriveCredentialResolution(
        credentials=object(),
        refreshed=False,
        credential_path="sa.json",
    )

    with pytest.raises(FrozenInstanceError):
        resolution.refreshed = True


def test_drive_client_is_thread_local(monkeypatch):
    drive_service._DRIVE_CLIENTS = {}
    drive_service._FOLDER_SCOPE_CACHE = {}
    created = []

    def _fake_credentials_from_file(_sa_path: str, scopes):
        assert scopes == ["https://www.googleapis.com/auth/drive"]
        return object()

    def _fake_build(service_name: str, version: str, http, cache_discovery: bool):
        assert service_name == "drive"
        assert version == "v3"
        assert http is not None
        assert cache_discovery is False
        obj = object()
        created.append(obj)
        return obj

    monkeypatch.setattr(
        drive_service.Credentials,
        "from_service_account_file",
        staticmethod(_fake_credentials_from_file),
    )
    monkeypatch.setattr(drive_service, "build", _fake_build)
    ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")

    main_client_1 = drive_service._get_drive_client(
        auth_mode="service_account",
        service_account_path="sa.json",
        oauth_token_path=None,
        ctx=ctx,
    )
    main_client_2 = drive_service._get_drive_client(
        auth_mode="service_account",
        service_account_path="sa.json",
        oauth_token_path=None,
        ctx=ctx,
    )
    assert main_client_1 is main_client_2

    worker_client = {}

    def _worker():
        worker_ctx = RunContext(
            schema_version="1.0", run_id="r2", task_id="t2", span_id="s2"
        )
        worker_client["first"] = drive_service._get_drive_client(
            auth_mode="service_account",
            service_account_path="sa.json",
            oauth_token_path=None,
            ctx=worker_ctx,
        )
        worker_client["second"] = drive_service._get_drive_client(
            auth_mode="service_account",
            service_account_path="sa.json",
            oauth_token_path=None,
            ctx=worker_ctx,
        )

    thread = threading.Thread(target=_worker)
    thread.start()
    thread.join()

    assert worker_client["first"] is worker_client["second"]
    assert worker_client["first"] is not main_client_1
    assert len(created) == 2


def test_drive_client_isolated_under_concurrent_access(monkeypatch):
    drive_service._DRIVE_CLIENTS = {}
    drive_service._FOLDER_SCOPE_CACHE = {}
    created = []
    barrier = threading.Barrier(3)
    worker_clients: list[object] = []

    def _fake_credentials_from_file(_sa_path: str, scopes):
        assert scopes == ["https://www.googleapis.com/auth/drive"]
        return object()

    def _fake_build(service_name: str, version: str, http, cache_discovery: bool):
        assert service_name == "drive"
        assert version == "v3"
        assert http is not None
        assert cache_discovery is False
        obj = object()
        created.append(obj)
        return obj

    monkeypatch.setattr(
        drive_service.Credentials,
        "from_service_account_file",
        staticmethod(_fake_credentials_from_file),
    )
    monkeypatch.setattr(drive_service, "build", _fake_build)

    def _worker(name: str):
        worker_ctx = RunContext(
            schema_version="1.0",
            run_id=f"r-{name}",
            task_id=f"t-{name}",
            span_id=f"s-{name}",
        )
        barrier.wait()
        first = drive_service._get_drive_client(
            auth_mode="service_account",
            service_account_path="sa.json",
            oauth_token_path=None,
            ctx=worker_ctx,
        )
        second = drive_service._get_drive_client(
            auth_mode="service_account",
            service_account_path="sa.json",
            oauth_token_path=None,
            ctx=worker_ctx,
        )
        assert first is second
        worker_clients.append(first)

    threads = [
        threading.Thread(target=_worker, args=("one",)),
        threading.Thread(target=_worker, args=("two",)),
    ]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert len(worker_clients) == 2
    assert worker_clients[0] is not worker_clients[1]
    assert len(created) == 2
