import threading

from src.contracts.run_context import RunContext
from src.services import drive_service


def test_drive_client_is_thread_local(monkeypatch):
    drive_service._DRIVE_CLIENTS = {}
    created = []

    def _fake_build(sa_path: str):
        obj = object()
        created.append(obj)
        return obj

    monkeypatch.setattr(drive_service, "_build_drive_client", _fake_build)
    ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")

    main_client_1 = drive_service._get_drive_client("sa.json", ctx)
    main_client_2 = drive_service._get_drive_client("sa.json", ctx)
    assert main_client_1 is main_client_2

    worker_client = {}

    def _worker():
        worker_ctx = RunContext(schema_version="1.0", run_id="r2", task_id="t2", span_id="s2")
        worker_client["first"] = drive_service._get_drive_client("sa.json", worker_ctx)
        worker_client["second"] = drive_service._get_drive_client("sa.json", worker_ctx)

    thread = threading.Thread(target=_worker)
    thread.start()
    thread.join()

    assert worker_client["first"] is worker_client["second"]
    assert worker_client["first"] is not main_client_1
    assert len(created) == 2
