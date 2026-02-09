import hashlib
import logging

from src.contracts.prompts import PromptLoadRequest
from src.contracts.prompts import PromptNamespaceListRequest
from src.contracts.run_context import RunContext
from src.services.prompt_service import list_prompt_namespaces, load_prompt_set


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_load_prompt_set_hashes(caplog):
    caplog.set_level(logging.INFO, logger="market_lense.prompt_service")
    prompt_set = load_prompt_set(PromptLoadRequest(schema_version="1.0", namespace="report_vs/doc_map"), _ctx())
    assert prompt_set.system.text
    assert prompt_set.user.text
    sys_hash = hashlib.sha256(prompt_set.system.text.encode("utf-8")).hexdigest()
    usr_hash = hashlib.sha256(prompt_set.user.text.encode("utf-8")).hexdigest()
    assert prompt_set.system.sha256 == sys_hash
    assert prompt_set.user.sha256 == usr_hash
    # ensure logs mention paths and hashes
    loaded_logs = [rec.message for rec in caplog.records if "prompt_load_complete" in rec.message]
    assert loaded_logs, "expected load logs"


def test_list_prompt_namespaces_returns_hashes() -> None:
    response = list_prompt_namespaces(
        PromptNamespaceListRequest(schema_version="1.0", reload_if_changed=True, force_reload=False),
        _ctx(),
    )
    assert response.namespaces
    first = response.namespaces[0]
    assert first.namespace
    assert first.system_sha256
    assert first.user_sha256
