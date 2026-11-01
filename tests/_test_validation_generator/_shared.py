# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_validation_generator.py"
)

import json
import logging
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.contracts.config import AppSettings
from src.contracts.openai import OpenAIResponseResult
from src.contracts.protected_facts import PROTECTED_FACT_DIMENSIONS
from src.contracts.prompts import (
    PromptDependency,
    PromptDependencyManifest,
    PromptSet,
    PromptTemplate,
)
from src.contracts.report_models import Figure, Quote, ReportPayload
from src.contracts.run_context import RunContext
from src.contracts.soft_copy_claim_provenance import (
    soft_copy_claim_provenance_to_payload,
    soft_copy_material_sentences,
    soft_copy_public_text,
)
from src.contracts.validation import ValidationRequest
from src.generators.soft_copy_claim_provenance import build_soft_copy_claim_provenance
from src.generators.validation.cache import load_cached_validation
from src.generators.validation.numbers import validate_new_numbers
from src.generators.validation.registry import build_validation_rule_registry
from src.generators.validation_generator import validate_report
from src.utils.errors import AppError
from src.utils.slugify import slugify


class FakePromptClient:
    def load_prompt_set(self, request, ctx):
        tmpl = PromptTemplate(
            schema_version="1.0",
            path=f"{request.namespace}/system",
            text="system",
            sha256="s",
        )
        user_text = (
            "user metrics {{ metrics_json }}\n"
            "quotes {{ quotes_json }}\n"
            "evidence {{ evidence_json }}"
            if request.namespace == "report_vs/validate/semantic"
            else "user {{ report_json }}"
        )
        user = PromptTemplate(
            schema_version="1.0",
            path=f"{request.namespace}/user",
            text=user_text,
            sha256="u",
        )
        return PromptSet(
            schema_version="1.0",
            system=tmpl,
            user=user,
            dependency_manifest=PromptDependencyManifest(
                schema_version="1.0",
                namespace=request.namespace,
                system_root=PromptDependency(
                    schema_version="1.0",
                    path=f"{request.namespace}/system",
                    sha256="a" * 64,
                    kind="system_root",
                ),
                user_root=PromptDependency(
                    schema_version="1.0",
                    path=f"{request.namespace}/user",
                    sha256="b" * 64,
                    kind="user_root",
                ),
            ),
            prompt_content_hash="c" * 64,
        )

    def render_prompt(self, request, ctx):
        rendered = request.template.text
        for key, value in request.variables.items():
            replacement = (
                value
                if isinstance(value, str)
                else json.dumps(value, ensure_ascii=False)
            )
            rendered = rendered.replace("{{ " + key + " }}", replacement).replace(
                "{{" + key + "}}", replacement
            )
        return SimpleNamespace(text=rendered)


def _grounding_contract_payload(request, payload: dict) -> dict:
    """Complete legacy test responses at the current grounding contract boundary."""

    def classification(value: object) -> str:
        normalized = str(value or "").strip().casefold()
        return {
            "factual": "factual_claim",
            "fact": "factual_claim",
            "factual_claim": "factual_claim",
            "interpretive": "analyst_interpretation",
            "analyst_interpretation": "analyst_interpretation",
            "recommendation": "prescriptive_recommendation",
            "prescriptive_recommendation": "prescriptive_recommendation",
        }.get(normalized, "factual_claim")

    try:
        prompt_text = str(request.user_prompt)
        report_json = prompt_text.split("user ", 1)[1]
        batch = json.loads(report_json)
    except (IndexError, TypeError, ValueError):
        batch = {}
        prompt_text = str(getattr(request, "user_prompt", "") or "")
        decoder = json.JSONDecoder()
        for index, char in enumerate(prompt_text):
            if char != "{":
                continue
            try:
                candidate, _end = decoder.raw_decode(prompt_text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and any(
                key in candidate
                for key in ("retained_claims_to_ground", "public_factual_items")
            ):
                batch = candidate
                break
    if not isinstance(batch, dict):
        return payload
    expected: list[dict] = [
        item
        for key in ("retained_claims_to_ground", "public_factual_items")
        for item in batch.get(key, [])
        if isinstance(item, dict) and str(item.get("item_id") or "").strip()
    ]
    checks = [item for item in payload.get("checks", []) if isinstance(item, dict)]
    unsupported = [
        dict(item) for item in payload.get("unsupported", []) if isinstance(item, dict)
    ]
    # Older fixtures identify an unsupported item by its public section/text.
    # Translate that retained test response into the current stable item-ID
    # contract before the fake response reaches production validation.
    for item in unsupported:
        if str(item.get("item_id") or "").strip():
            continue
        section = str(item.get("section") or "").strip()
        text = str(item.get("text") or "").strip()
        matches = [
            expected_item
            for expected_item in expected
            if (section and str(expected_item.get("section") or "").strip() == section)
            or (text and str(expected_item.get("text") or "").strip() == text)
        ]
        if len(matches) > 1:
            public_matches = [
                expected_item
                for expected_item in matches
                if expected_item
                in [
                    item
                    for item in batch.get("public_factual_items", [])
                    if isinstance(item, dict)
                ]
            ]
            if len(public_matches) == 1:
                matches = public_matches
        if len(matches) == 1:
            item["item_id"] = str(matches[0]["item_id"])
            item.setdefault("section", str(matches[0].get("section") or "grounding"))
            item.setdefault("text", str(matches[0].get("text") or ""))
            item.setdefault(
                "classification",
                classification(
                    matches[0].get("declared_classification") or "factual_claim"
                ),
            )
            item.setdefault("entailment_outcome", "not_established")
            item.setdefault("violation_type", "unsupported_factual_claim")
            item.setdefault("reason", "The test response marks this item unsupported.")
    existing_ids = {
        str(item.get("item_id") or "").strip()
        for item in checks + unsupported
        if str(item.get("item_id") or "").strip()
    }

    def protected_facts(status: str) -> dict[str, dict[str, object]]:
        return {
            dimension: {
                "claim_value": None,
                "evidence_value": None,
                "status": status,
            }
            for dimension in PROTECTED_FACT_DIMENSIONS
        }

    unsupported_by_id = {
        str(item.get("item_id") or "").strip(): item
        for item in unsupported
        if str(item.get("item_id") or "").strip()
    }
    for expected_item in expected:
        item_id = str(expected_item["item_id"])
        if item_id in existing_ids:
            continue
        failed = unsupported_by_id.get(item_id)
        outcome = str(failed.get("entailment_outcome") or "") if failed else ""
        if outcome not in {"contradicted", "not_established"}:
            outcome = "entailed"
        checks.append(
            {
                "item_id": item_id,
                "section": str(expected_item.get("section") or "grounding"),
                "text": str(expected_item.get("text") or ""),
                "classification": (
                    classification(failed.get("classification") or "factual_claim")
                    if failed
                    else classification(
                        expected_item.get("declared_classification") or "factual_claim"
                    )
                ),
                "entailment_outcome": outcome,
                "proposition_status": (
                    "incompatible"
                    if outcome == "contradicted"
                    else "unknown"
                    if outcome == "not_established"
                    else "compatible"
                ),
                "protected_facts": protected_facts(
                    "incompatible"
                    if outcome == "contradicted"
                    else "unknown"
                    if outcome == "not_established"
                    else "compatible"
                ),
                "reason": (
                    str(
                        failed.get("reason")
                        or "The test response marks this item unsupported."
                    )
                    if failed
                    else "The test response accepts this item against its retained evidence."
                ),
            }
        )
    return {"checks": checks, "unsupported": unsupported}


def _semantic_contract_payload(request, payload: dict) -> dict:
    """Complete an ordinary fake semantic response without masking explicit failures."""

    sections: dict[str, list[dict]] = {}
    for line in str(request.user_prompt).splitlines():
        for key in ("metrics", "quotes"):
            prefix = f"{key} "
            if line.startswith(prefix):
                try:
                    value = json.loads(line[len(prefix) :])
                except (TypeError, ValueError):
                    value = []
                sections[key] = (
                    [item for item in value if isinstance(item, dict)]
                    if isinstance(value, list)
                    else []
                )
    completed: dict[str, list[dict]] = {}
    for key in ("metrics", "quotes"):
        provided = [
            dict(item) for item in payload.get(key, []) if isinstance(item, dict)
        ]
        provided_by_id = {
            str(item.get("id") or "").strip(): item
            for item in provided
            if str(item.get("id") or "").strip()
        }
        entries: list[dict] = []
        for expected in sections.get(key, []):
            item_id = str(expected.get("id") or "").strip()
            if not item_id:
                continue
            item = dict(provided_by_id.get(item_id) or {})
            item.update(
                {
                    "id": item_id,
                    "supported": bool(item.get("supported", True)),
                    "confidence": float(item.get("confidence", 1.0)),
                    "reason": str(
                        item.get("reason")
                        or "The fake model accepts the supplied evidence."
                    ),
                }
            )
            entries.append(item)
        entries.extend(
            item
            for item in provided
            if str(item.get("id") or "").strip()
            not in {
                str(expected.get("id") or "").strip()
                for expected in sections.get(key, [])
            }
        )
        completed[key] = entries
    return completed


class FakeOpenAI:
    def __init__(
        self,
        *payloads,
        semantic_payload=None,
        grounding_payload=None,
        complete_grounding_contract: bool = True,
    ):
        self.payloads = list(payloads) or [{}]
        self.semantic_payload = semantic_payload
        self.grounding_payload = grounding_payload
        self.complete_grounding_contract = complete_grounding_contract
        self.requests = []
        self._lock = threading.Lock()

    def _next_payload(self, ctx):
        task_id = str(getattr(ctx, "task_id", ""))
        if task_id.endswith(":semantic") and isinstance(self.semantic_payload, dict):
            return self.semantic_payload
        if task_id.endswith(":grounding") and isinstance(self.grounding_payload, dict):
            return self.grounding_payload
        with self._lock:
            if self.payloads:
                return self.payloads.pop(0)
            return {}

    def openai_chat_json(self, req, ctx):
        payload = self._next_payload(ctx)
        if (
            self.semantic_payload is None
            and str(getattr(ctx, "task_id", "")).endswith(":semantic")
            and isinstance(payload, dict)
        ):
            payload = _semantic_contract_payload(req, payload)
        if (
            self.complete_grounding_contract
            and str(getattr(ctx, "task_id", "")).endswith(":grounding")
            and isinstance(payload, dict)
        ):
            payload = _grounding_contract_payload(req, {"checks": [], **payload})
        with self._lock:
            self.requests.append(("chat", req.model, str(getattr(ctx, "task_id", ""))))
        return OpenAIResponseResult(
            schema_version="1.0",
            text=json.dumps(payload),
            parsed_json=payload,
            input_tokens=0,
            output_tokens=0,
            tool_calls=0,
            model=req.model,
        )

    def openai_respond_with_vector_store(self, req, ctx):
        with self._lock:
            self.requests.append(
                ("vector", req.vector_store_id, str(getattr(ctx, "task_id", "")))
            )
        return self.openai_chat_json(req, ctx)


class FailingOpenAI(FakeOpenAI):
    def __init__(self, *, semantic_exc=None, grounding_exc=None, semantic_payload=None):
        super().__init__(
            semantic_payload=semantic_payload or {"metrics": [], "quotes": []},
            grounding_payload={"unsupported": []},
        )
        self.semantic_exc = semantic_exc
        self.grounding_exc = grounding_exc

    def openai_chat_json(self, req, ctx):
        task_id = str(getattr(ctx, "task_id", ""))
        if task_id.endswith(":semantic") and self.semantic_exc is not None:
            raise self.semantic_exc
        if task_id.endswith(":grounding") and self.grounding_exc is not None:
            raise self.grounding_exc
        return super().openai_chat_json(req, ctx)

    def openai_respond_with_vector_store(self, req, ctx):
        task_id = str(getattr(ctx, "task_id", ""))
        if task_id.endswith(":grounding") and self.grounding_exc is not None:
            raise self.grounding_exc
        return super().openai_respond_with_vector_store(req, ctx)


class FakeAnalysisStore:
    def __init__(self):
        self.stored = []

    def store_pack(
        self, output_dir, report_id, pack_name, payload, ctx, report_slug=None
    ):
        slug = slugify(report_slug or report_id)
        path = Path(output_dir) / slug / "report_analysis" / f"{pack_name}.json"
        self.stored.append((output_dir, report_id, pack_name, payload))
        return str(path)


def _settings(
    tmp_path,
    *,
    validation_grounding_use_vector_store: bool = False,
    report_worker_limit: int = 2,
    validation_data_gap_policy: str = "warn",
):
    return AppSettings(
        schema_version="1.0",
        google_sa_path="sa.json",
        gdrive_folder_id="folder",
        openai_api_key="key",
        openai_model="gpt-4.1-mini",
        batch_limit=1,
        output_dir=str(tmp_path),
        cache_dir=str(tmp_path / "cache"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        publisher_profiles_path=str(tmp_path / "publisher-profiles.json"),
        category_mapping_path="cats.yaml",
        cover_style_path=str(
            Path(__file__).resolve().parents[1] / "src" / "config" / "cover-styles.yaml"
        ),
        ingest_lock_path=str(tmp_path / "lock"),
        ingest_lock_ttl_seconds=1.0,
        temperature=0.1,
        openai_seed=None,
        pdf_text_max_pages=1,
        pdf_text_max_chars=1000,
        rank_model="",
        rank_temperature=0.1,
        rank_seed=None,
        report_worker_limit=report_worker_limit,
        openai_timeout_seconds=5.0,
        rank_timeout_seconds=5.0,
        contents_max_pages=1,
        contents_min_headings=1,
        contents_keywords=["contents"],
        contents_preview_dpi=72,
        vector_store_keep=True,
        validation_grounding_use_vector_store=validation_grounding_use_vector_store,
        validation_data_gap_policy=validation_data_gap_policy,
        cost_ledger_path=str(tmp_path / "cost-ledger.jsonl"),
        cost_daily_path=str(tmp_path / "cost-daily.json"),
        model_pricing={
            "gpt-4.1-mini": {
                "input_tokens_per_1k_usd": 0.003,
                "output_tokens_per_1k_usd": 0.006,
                "tool_call_usd": 0.0,
            }
        },
        llm_execution_policies={
            "report_vs": {
                "schema_version": "1.0",
                "provider": "openai",
                "model": "gpt-4.1-mini",
                "temperature": 0.1,
                "seed_policy": "inherit",
                "max_output_tokens": 2048,
                "retrieval_mode": "chat_json",
                "timeout_seconds": 5.0,
                "provider_retry_count": 0,
                "structured_output_mode": "json_object",
                "fallback_policy": "same_provider_only",
                "pricing_key": "gpt-4.1-mini",
            }
        },
    )


def _ctx():
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _report():
    return ReportPayload(
        tldr="TLDR",
        title="Report",
        insights=["i1", "i2", "i3", "i4", "i5"],
        quote=Quote(text="Quoted text", author="Analyst"),
        figure=Figure(title="Figure", evidence="Fig"),
        commentary="Commentary",
        source="Source",
    )


def _low_text_status():
    path = Path(__file__).parent / "fixtures" / "low_text_status.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _set_test_soft_copy_provenance(
    artifacts: dict,
    declarations: dict[str, tuple[str, list[str]]],
) -> None:
    """Attach explicit test declarations through the production provenance builder."""

    claims = []
    for family, (classification, evidence_ids) in declarations.items():
        text = soft_copy_public_text(family, artifacts.get(family))
        sentences = soft_copy_material_sentences(text)
        if not sentences:
            continue
        claims.extend(
            build_soft_copy_claim_provenance(
                artifact_family=family,
                text=text,
                declared_claims=[
                    {
                        "claim": sentence,
                        "classification": classification,
                        "evidence_ids": list(evidence_ids),
                    }
                    for sentence in sentences
                ],
                evidence_span_index={},
                producing_prompt_identity={"namespace": f"test/{family}"},
                generation_attempt=1,
                regeneration_attempt=0,
            )
        )
    artifacts["soft_copy_claim_provenance"] = soft_copy_claim_provenance_to_payload(
        claims
    )


__all__ = [
    name
    for name in globals()
    if name
    not in {
        "__name__",
        "__annotations__",
        "__doc__",
        "__spec__",
        "__file__",
        "__package__",
        "__loader__",
        "__cached__",
        "__builtins__",
        "_SplitPath",
    }
]
