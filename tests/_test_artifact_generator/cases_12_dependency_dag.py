from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from threading import Event, Lock

import pytest

from src.contracts.openai import OpenAIResponseResult
from src.contracts.prompt_family_materialization import PromptFamilyReuseResponse
from src.generators.artifact_generator import generate_artifacts
from src.orchestrators._report_analysis_orchestrator.artifact_batches import (
    ArtifactStepTaskScheduler,
)
from src.utils.errors import AppError

from ._shared import (
    FakeAnalysisStore,
    FakePromptClient,
    _cover_semantics_response,
    _ctx,
    _default_editorial_plan,
    _doc_map,
    _evidence_packs,
    _settings,
)

_FAMILIES = (
    "summary",
    "insights_candidates",
    "quotes",
    "insights_final",
    "cover_semantics",
    "expert_comment",
    "linkedin_post",
)


def _responses():
    return {
        "editorial_plan": {"editorial_plan": _default_editorial_plan()},
        "summary": {
            "summary": {
                "tldr": "Retail evidence points to durable growth.",
                "card_tldr_compact": "Retail evidence points to durable growth.",
                "executive_summary": (
                    "The retained data shows revenue rising 10% year over year."
                ),
                "claim_evidence_map": [
                    {
                        "claim": "Revenue rose 10% year over year.",
                        "evidence_id": "f1",
                        "evidence": "Revenue +10% YoY",
                        "pages": [2],
                    }
                ],
            },
            "claim_provenance": [
                {
                    "claim": "Retail evidence points to durable growth.",
                    "classification": "interpretive",
                    "evidence_ids": ["f1"],
                },
                {
                    "claim": (
                        "The retained data shows revenue rising 10% year over year."
                    ),
                    "classification": "factual",
                    "evidence_ids": ["f1"],
                },
            ],
        },
        "insights_candidates": {
            "insights_candidates": [
                {
                    "id": f"c{index}",
                    "text": f"Candidate {index} is supported by retained evidence.",
                    "evidence_id": f"f{index}",
                    "evidence": f"Evidence for finding {index}",
                    "metric": {},
                    "pages": [index + 1],
                }
                for index in range(1, 6)
            ]
        },
        "quotes": {
            "quotes_final": [
                {
                    "text": "We are expanding rapidly",
                    "speaker": "CEO",
                    "citation": "Earnings call",
                    "page": 3,
                    "evidence_id": "q1",
                }
            ]
        },
        "insights_final": {
            "insights_final": [
                {
                    "id": f"f{index}",
                    "text": f"Final insight {index} is supported by evidence.",
                    "evidence_id": f"f{index}",
                    "evidence": f"Evidence for finding {index}",
                    "metric": {},
                    "pages": [index + 1],
                }
                for index in range(1, 6)
            ]
        },
        "cover_semantics": _cover_semantics_response(),
        "expert_comment": {
            "expert_comment": "Revenue growth creates a chance to reinvest.",
            "claim_provenance": [
                {
                    "claim": "Revenue growth creates a chance to reinvest.",
                    "classification": "interpretive",
                    "evidence_ids": ["f1"],
                }
            ],
        },
        "linkedin_post": {
            "linkedin_post": "Retailers should build on this momentum.",
            "claim_provenance": [
                {
                    "claim": "Retailers should build on this momentum.",
                    "classification": "recommendation",
                    "evidence_ids": ["f1"],
                }
            ],
        },
    }


class _ControlledArtifactClient:
    def __init__(self, *, blocked=(), failures=None):
        self.responses = _responses()
        self.started = {name: Event() for name in _FAMILIES + ("editorial_plan",)}
        self.completed = {name: Event() for name in _FAMILIES + ("editorial_plan",)}
        self.release = {name: Event() for name in self.started}
        for name in set(self.release) - set(blocked):
            self.release[name].set()
        self.failures = failures or {}
        self._lock = Lock()
        self.completion_order = []
        self.active_calls = 0
        self.maximum_active_calls = 0

    def _call(self, ctx):
        family = ctx.task_id.rsplit(":", 1)[-1]
        if family == "insights_final":
            assert self.completed["insights_candidates"].is_set()
        if family == "cover_semantics":
            assert self.completed["summary"].is_set()
            assert self.completed["insights_final"].is_set()
        if family in {"expert_comment", "linkedin_post"}:
            assert self.completed["insights_final"].is_set()
        self.started[family].set()
        with self._lock:
            self.active_calls += 1
            self.maximum_active_calls = max(
                self.maximum_active_calls, self.active_calls
            )
        try:
            if not self.release[family].wait(timeout=10):
                raise TimeoutError(f"test did not release {family}")
            failure = self.failures.get(family)
            if failure is not None:
                self.completed[family].set()
                raise failure
            with self._lock:
                self.completion_order.append(family)
            self.completed[family].set()
            payload = deepcopy(self.responses[family])
            return OpenAIResponseResult(
                schema_version="1.0",
                text="{}",
                parsed_json=payload,
                input_tokens=1,
                output_tokens=1,
                tool_calls=0,
                model="gpt-4.1-mini",
            )
        finally:
            with self._lock:
                self.active_calls -= 1

    def openai_chat_json(self, request, ctx):
        del request
        return self._call(ctx)

    def openai_respond_with_vector_store(self, request, ctx):
        del request
        return self._call(ctx)


def _run_artifacts(tmp_path, client, executor=None, analysis_store=None):
    analysis_store = analysis_store or FakeAnalysisStore()
    return generate_artifacts(
        report_id="r1",
        report_name="report",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path),
        vector_store_id="vs_1",
        ctx=_ctx(),
        openai_client=client,
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
        artifact_step_executor=executor,
    )


def test_artifact_families_follow_dependencies_without_stage_barriers(tmp_path):
    blocked = {
        "summary",
        "insights_candidates",
        "quotes",
        "insights_final",
        "cover_semantics",
        "expert_comment",
        "linkedin_post",
    }
    client = _ControlledArtifactClient(blocked=blocked)
    executor = ArtifactStepTaskScheduler(_settings(tmp_path))
    with ThreadPoolExecutor(max_workers=1) as coordinator:
        future = coordinator.submit(_run_artifacts, tmp_path, client, executor)
        try:
            assert all(
                client.started[name].wait(timeout=3)
                for name in (
                    "summary",
                    "insights_candidates",
                    "quotes",
                )
            )
            assert client.completed["editorial_plan"].is_set()
            assert not client.started["insights_final"].is_set()

            client.release["insights_candidates"].set()
            assert client.started["insights_final"].wait(timeout=3)
            assert not client.completed["summary"].is_set()
            assert not client.completed["quotes"].is_set()

            client.release["insights_final"].set()
            assert client.started["expert_comment"].wait(timeout=3)
            assert client.started["linkedin_post"].wait(timeout=3)
            assert not client.started["cover_semantics"].is_set()

            client.release["summary"].set()
            assert client.started["cover_semantics"].wait(timeout=3)
            assert not client.completed["expert_comment"].is_set()
            assert not client.completed["linkedin_post"].is_set()
            assert not future.done()

            for name in ("cover_semantics", "expert_comment", "linkedin_post"):
                client.release[name].set()
            assert not future.done()
            client.release["quotes"].set()
            payload = future.result(timeout=5)
        finally:
            for event in client.release.values():
                event.set()
            executor.shutdown()

    assert all(client.started[name].is_set() for name in _FAMILIES)
    assert payload["family_status"]["summary"]["status"] == "generated"
    assert payload["family_status"]["quotes"]["status"] == "generated"
    assert payload["_cache"]["family_reuse_telemetry"]["actual_model_calls"] == 8
    assert client.maximum_active_calls <= executor.max_workers
    assert {
        claim["artifact_family"]
        for claim in payload["soft_copy_claim_provenance"]["claims"]
    } == {
        "summary",
        "expert_comment",
        "linkedin_post",
    }


def test_two_worker_dag_prioritizes_candidate_critical_path_over_quotes(tmp_path):
    client = _ControlledArtifactClient(
        blocked={"summary", "insights_candidates", "quotes", "insights_final"}
    )
    settings = replace(
        _settings(tmp_path),
        artifact_parallel_workers=2,
        artifact_global_max_in_flight=2,
    )
    executor = ArtifactStepTaskScheduler(settings)
    with ThreadPoolExecutor(max_workers=1) as coordinator:
        future = coordinator.submit(_run_artifacts, tmp_path, client, executor)
        try:
            assert client.started["summary"].wait(timeout=3)
            assert client.started["insights_candidates"].wait(timeout=3)
            assert not client.started["quotes"].is_set()

            client.release["summary"].set()
            assert client.completed["summary"].wait(timeout=3)
            assert not client.started["quotes"].is_set()

            client.release["insights_candidates"].set()
            assert client.started["insights_final"].wait(timeout=3)
            assert client.started["quotes"].wait(timeout=3)
            client.release["insights_final"].set()
            client.release["quotes"].set()
            payload = future.result(timeout=5)
        finally:
            for event in client.release.values():
                event.set()
            executor.shutdown()

    assert payload["family_status"]["quotes"]["status"] == "generated"
    assert client.maximum_active_calls <= 2


def test_artifact_family_failure_stops_dependents_and_keeps_running_work_safe(
    tmp_path,
):
    blocked = {"summary", "insights_candidates", "quotes"}
    failure = AppError(
        code="artifact_test_failure",
        message="candidate failed",
        retryable=False,
    )
    client = _ControlledArtifactClient(
        blocked=blocked,
        failures={"insights_candidates": failure},
    )
    executor = ArtifactStepTaskScheduler(_settings(tmp_path))
    analysis_store = FakeAnalysisStore()
    with ThreadPoolExecutor(max_workers=1) as coordinator:
        future = coordinator.submit(
            _run_artifacts, tmp_path, client, executor, analysis_store
        )
        try:
            assert all(client.started[name].wait(timeout=3) for name in blocked)
            client.release["insights_candidates"].set()
            with pytest.raises(AppError) as raised:
                future.result(timeout=3)
            assert raised.value.code == "artifact_test_failure"
            assert not client.started["insights_final"].is_set()
            assert not client.started["expert_comment"].is_set()
            assert not client.started["linkedin_post"].is_set()
            assert not client.started["cover_semantics"].is_set()
        finally:
            for event in client.release.values():
                event.set()
            executor.shutdown()
    assert client.completed["summary"].is_set()
    assert client.completed["quotes"].is_set()
    assert analysis_store.stored == []


def _run_gated_dag(tmp_path, initial_order, terminal_order):
    client = _ControlledArtifactClient(blocked=_FAMILIES)
    executor = ArtifactStepTaskScheduler(_settings(tmp_path))
    with ThreadPoolExecutor(max_workers=1) as coordinator:
        future = coordinator.submit(_run_artifacts, tmp_path, client, executor)
        try:
            assert all(
                client.started[name].wait(timeout=3)
                for name in ("summary", "insights_candidates", "quotes")
            )
            for family in initial_order:
                client.release[family].set()
                assert client.completed[family].wait(timeout=3)
            assert client.started["insights_final"].wait(timeout=3)
            client.release["insights_final"].set()
            assert client.completed["insights_final"].wait(timeout=3)
            for family in ("cover_semantics", "expert_comment", "linkedin_post"):
                assert client.started[family].wait(timeout=3)
            for family in terminal_order:
                client.release[family].set()
                assert client.completed[family].wait(timeout=3)
            return future.result(timeout=5)
        finally:
            for event in client.release.values():
                event.set()
            executor.shutdown()


def _artifact_semantics(payload):
    public_fields = (
        "editorial_plan",
        "summary",
        "cover_semantics",
        "insights_candidates",
        "insights_final",
        "quotes_final",
        "expert_comment",
        "linkedin_post",
        "family_status",
        "soft_copy_claim_provenance",
    )
    return {field: payload[field] for field in public_fields}


def test_artifact_output_is_order_independent_and_matches_sequential_generation(
    tmp_path,
):
    sequential = _run_artifacts(tmp_path / "sequential", _ControlledArtifactClient())
    first_dag = _run_gated_dag(
        tmp_path / "first-dag",
        initial_order=("summary", "quotes", "insights_candidates"),
        terminal_order=("cover_semantics", "expert_comment", "linkedin_post"),
    )
    second_dag = _run_gated_dag(
        tmp_path / "second-dag",
        initial_order=("quotes", "insights_candidates", "summary"),
        terminal_order=("linkedin_post", "expert_comment", "cover_semantics"),
    )

    assert _artifact_semantics(sequential) == _artifact_semantics(first_dag)
    assert _artifact_semantics(first_dag) == _artifact_semantics(second_dag)
    assert sequential["_cache"]["key"] == first_dag["_cache"]["key"]
    assert (
        first_dag["_cache"]["family_outputs"] == second_dag["_cache"]["family_outputs"]
    )
    for payload in (sequential, first_dag, second_dag):
        telemetry = payload["_cache"]["family_reuse_telemetry"]
        assert telemetry["actual_model_calls"] == 8
        assert telemetry["input_tokens"] == 8
        assert telemetry["output_tokens"] == 8


def test_reused_prompt_families_and_soft_copy_provenance_survive_dag(tmp_path):
    source_id = "source:dag-family-reuse"
    fresh_root = tmp_path / "fresh"
    replay_root = tmp_path / "replay"
    fresh_root.mkdir()
    replay_root.mkdir()
    fresh_client = _ControlledArtifactClient()
    fresh = generate_artifacts(
        report_id="dag-family-reuse",
        report_name="DAG Family Reuse",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(fresh_root),
        ctx=replace(_ctx(), source_identity_id=source_id),
        openai_client=fresh_client,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    retained = fresh["_cache"]["family_outputs"]

    dag_reuse_requests = {}

    def reuse_reader(request, _ctx):
        dag_reuse_requests[request.family_id] = request.relevant_input_hash
        return PromptFamilyReuseResponse(
            schema_version="1.0",
            reusable=True,
            reason="reused",
            output_payload=retained[request.family_id],
            artifact_id="retained:" + request.family_id,
            output_hash="retained-hash",
        )

    replay_client = _ControlledArtifactClient()
    executor = ArtifactStepTaskScheduler(_settings(replay_root))
    try:
        replay = generate_artifacts(
            report_id="dag-family-reuse",
            report_name="DAG Family Reuse",
            doc_map=_doc_map(),
            evidence_packs=_evidence_packs(),
            settings=_settings(replay_root),
            ctx=replace(_ctx(), source_identity_id=source_id),
            openai_client=replay_client,
            prompt_client=FakePromptClient(),
            analysis_store=FakeAnalysisStore(),
            artifact_step_executor=executor,
            prompt_family_reuse_reader=reuse_reader,
        )
    finally:
        executor.shutdown()

    assert replay_client.completion_order == []
    telemetry = replay["_cache"]["family_reuse_telemetry"]
    assert telemetry["actual_model_calls"] == 0
    assert telemetry["model_calls_avoided"] == 8
    assert telemetry["reused_families"] == sorted(retained)
    assert dag_reuse_requests == {
        family: identity["relevant_input_hash"]
        for family, identity in fresh["_cache"]["family_reuse"].items()
    }
    assert replay["summary"] == fresh["summary"]
    assert replay["expert_comment"] == fresh["expert_comment"]
    assert replay["linkedin_post"] == fresh["linkedin_post"]
    for family in ("summary", "expert_comment", "linkedin_post"):
        fresh_claim = next(
            claim
            for claim in fresh["soft_copy_claim_provenance"]["claims"]
            if claim["artifact_family"] == family
        )
        replay_claim = next(
            claim
            for claim in replay["soft_copy_claim_provenance"]["claims"]
            if claim["artifact_family"] == family
        )
        assert replay_claim["evidence_ids"] == fresh_claim["evidence_ids"]
        assert replay_claim["source_spans"] == fresh_claim["source_spans"]
        assert (
            replay_claim["producing_prompt_identity"]
            == fresh_claim["producing_prompt_identity"]
        )
