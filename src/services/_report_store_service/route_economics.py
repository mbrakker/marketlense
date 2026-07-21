from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

from src.contracts.report_store import (
    AcquisitionRouteEconomicsCohort,
    AcquisitionRouteEconomicsRecommendation,
    AcquisitionRouteEconomicsRequest,
    AcquisitionRouteEconomicsResponse,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

from .common import logger


def read_acquisition_route_economics(
    request: AcquisitionRouteEconomicsRequest,
    ctx: RunContext,
) -> AcquisitionRouteEconomicsResponse:
    """Compare compatible retained attempts without mutating route state or config."""

    _validate_request(request)
    path = Path(request.db_path)
    if not path.exists():
        return AcquisitionRouteEconomicsResponse(schema_version="1.0")
    try:
        with sqlite3.connect(
            f"file:{path.resolve().as_posix()}?mode=ro", uri=True
        ) as conn:
            exists = conn.execute(
                "select 1 from sqlite_master "
                "where type = 'table' and name = 'acquisition_attempt_resources'"
            ).fetchone()
            rows = (
                list(
                    conn.execute(
                        """
                    select publisher_id, source_policy_compatibility_hash, route_family,
                           elapsed_ms, terminal_outcome, estimated_cost_usd,
                           browser_launches, browser_model_calls,
                           avoided_operations_json, incomplete_fields_json
                    from acquisition_attempt_resources
                    order by publisher_id, source_policy_compatibility_hash,
                             route_family, completed_at_utc, attempt_id
                    """
                    )
                )
                if exists is not None
                else []
            )
    except sqlite3.Error as exc:
        raise AppError(
            code="route_economics_read_failed",
            message="Route-economics report could not read acquisition attempts",
            cause=exc,
            retryable=False,
            context={"db_path": str(path)},
        ) from exc

    grouped: dict[tuple[str, str, str], list[tuple[object, ...]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row[0]), str(row[1]), str(row[2]))].append(row)
    cohorts = [_cohort(key, records) for key, records in sorted(grouped.items())]
    recommendations = _recommend(cohorts, request)
    response = AcquisitionRouteEconomicsResponse(
        schema_version="1.0", cohorts=cohorts, recommendations=recommendations
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="acquisition_route_economics_read",
            module=logger.name,
            fields={
                "cohort_count": len(cohorts),
                "recommendation_count": len(recommendations),
                "proposal_count": sum(
                    item.disposition == "proposal" for item in recommendations
                ),
                "provider_calls": 0,
                "route_history_mutations": 0,
            },
        )
    )
    return response


def _validate_request(request: AcquisitionRouteEconomicsRequest) -> None:
    if request.schema_version != "1.0" or not str(request.db_path or "").strip():
        raise AppError(
            code="route_economics_request_invalid",
            message="Route-economics report requires a reports database path",
            retryable=False,
        )
    if int(request.minimum_sample_size) < 3:
        raise AppError(
            code="route_economics_minimum_sample_invalid",
            message="Route-economics recommendations require at least three attempts",
            retryable=False,
        )
    for value in (
        request.minimum_success_rate_improvement,
        request.minimum_cost_reduction_fraction,
    ):
        if not 0.0 <= float(value) <= 1.0:
            raise AppError(
                code="route_economics_threshold_invalid",
                message=(
                    "Route-economics improvement thresholds must be between zero "
                    "and one"
                ),
                retryable=False,
            )


def _json_list(value: object) -> tuple[str, ...]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return ()
    return tuple(str(item) for item in parsed) if isinstance(parsed, list) else ()


def _nearest_rank(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    index = max(0, min(len(values) - 1, int((len(values) * percentile) - 0.000001)))
    return values[index]


def _nonnegative_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return max(0, int(value))
    return 0


def _nonnegative_float(value: object) -> float:
    if isinstance(value, (int, float, str)):
        return max(0.0, float(value))
    return 0.0


def _cohort(
    key: tuple[str, str, str], records: list[tuple[object, ...]]
) -> AcquisitionRouteEconomicsCohort:
    complete = [record for record in records if not _json_list(record[9])]
    elapsed = sorted(_nonnegative_int(record[3]) for record in complete)
    successes = sum(str(record[4]) == "success" for record in complete)
    known_cost = round(sum(_nonnegative_float(record[5]) for record in complete), 6)
    return AcquisitionRouteEconomicsCohort(
        schema_version="1.0",
        publisher_id=key[0],
        route_policy_hash=key[1],
        route_family=key[2],
        sample_size=len(records),
        complete_sample_size=len(complete),
        verified_success_rate=(
            round(successes / len(complete), 6) if complete else 0.0
        ),
        median_elapsed_ms=_nearest_rank(elapsed, 0.5),
        p95_elapsed_ms=_nearest_rank(elapsed, 0.95),
        estimated_cost_usd=known_cost if len(complete) == len(records) else None,
        browser_launches=sum(_nonnegative_int(record[6]) for record in complete),
        browser_model_calls=sum(_nonnegative_int(record[7]) for record in complete),
        avoided_operation_count=sum(len(_json_list(record[8])) for record in records),
    )


def _recommend(
    cohorts: list[AcquisitionRouteEconomicsCohort],
    request: AcquisitionRouteEconomicsRequest,
) -> list[AcquisitionRouteEconomicsRecommendation]:
    groups: dict[tuple[str, str], list[AcquisitionRouteEconomicsCohort]] = defaultdict(
        list
    )
    for cohort in cohorts:
        groups[(cohort.publisher_id, cohort.route_policy_hash)].append(cohort)
    recommendations: list[AcquisitionRouteEconomicsRecommendation] = []
    for (publisher_id, policy_hash), group in sorted(groups.items()):
        direct = next(
            (item for item in group if item.route_family.startswith("direct")), None
        )
        if direct is None:
            recommendations.append(
                _abstain(publisher_id, policy_hash, "no_compatible_direct_baseline")
            )
            continue
        if direct.complete_sample_size < request.minimum_sample_size:
            recommendations.append(
                _abstain(publisher_id, policy_hash, "insufficient_direct_sample")
            )
            continue
        candidates = [
            item
            for item in group
            if item.route_family != direct.route_family
            and item.complete_sample_size >= request.minimum_sample_size
            and item.estimated_cost_usd is not None
        ]
        direct_cost = direct.estimated_cost_usd
        if direct_cost is None or not candidates:
            recommendations.append(
                _abstain(
                    publisher_id,
                    policy_hash,
                    "insufficient_compatible_complete_evidence",
                )
            )
            continue
        candidate = sorted(
            candidates,
            key=lambda item: (
                -item.verified_success_rate,
                item.estimated_cost_usd
                if item.estimated_cost_usd is not None
                else float("inf"),
                item.route_family,
            ),
        )[0]
        candidate_cost = candidate.estimated_cost_usd
        if candidate_cost is None:
            continue
        success_gain = candidate.verified_success_rate - direct.verified_success_rate
        cost_reduction = (
            (direct_cost - candidate_cost) / direct_cost if direct_cost > 0 else 0.0
        )
        if (
            success_gain >= request.minimum_success_rate_improvement
            and cost_reduction >= request.minimum_cost_reduction_fraction
        ):
            recommendations.append(
                AcquisitionRouteEconomicsRecommendation(
                    schema_version="1.0",
                    publisher_id=publisher_id,
                    route_policy_hash=policy_hash,
                    disposition="proposal",
                    baseline_route_family=direct.route_family,
                    candidate_route_family=candidate.route_family,
                    proposal=(
                        "operator_review: retain direct-first globally; consider "
                        f"publisher-scoped {candidate.route_family} preference"
                    ),
                    reasons=(
                        "compatible_policy_hash",
                        "minimum_sample_met",
                        "material_success_rate_improvement",
                        "material_cost_reduction",
                    ),
                )
            )
        else:
            recommendations.append(
                _abstain(
                    publisher_id, policy_hash, "material_improvement_threshold_not_met"
                )
            )
    return recommendations


def _abstain(
    publisher_id: str, policy_hash: str, reason: str
) -> AcquisitionRouteEconomicsRecommendation:
    return AcquisitionRouteEconomicsRecommendation(
        schema_version="1.0",
        publisher_id=publisher_id,
        route_policy_hash=policy_hash,
        disposition="no_recommendation",
        reasons=(reason,),
    )
