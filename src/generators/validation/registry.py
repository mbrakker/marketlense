from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Iterable, List, Sequence, Tuple

from src.contracts.validation import ValidationIssue
from src.utils.logging import log_event

from .grounding import run_grounding_rule
from .family_confidence import run_family_confidence_rule
from .metrics import run_metric_rule
from .models import ValidationRuntime
from .numbers import run_number_rule
from .quotes import run_quote_rule
from .semantic import run_semantic_rule
from .shared import LOGGER_NAME, logger
from .topic_sections import run_topic_section_rule


@dataclass(frozen=True)
class ValidationRule:
    rule_id: str
    stage: str
    execute: Callable[[ValidationRuntime], List[ValidationIssue]]


def build_validation_rule_registry() -> tuple[ValidationRule, ...]:
    return (
        ValidationRule(
            rule_id="toc_integrity",
            stage="bootstrap",
            execute=run_topic_section_rule,
        ),
        ValidationRule(
            rule_id="family_confidence",
            stage="bootstrap",
            execute=run_family_confidence_rule,
        ),
        ValidationRule(
            rule_id="semantic", stage="bootstrap", execute=run_semantic_rule
        ),
        ValidationRule(rule_id="metrics", stage="dependent", execute=run_metric_rule),
        ValidationRule(rule_id="quotes", stage="dependent", execute=run_quote_rule),
        ValidationRule(rule_id="numbers", stage="independent", execute=run_number_rule),
        ValidationRule(
            rule_id="grounding",
            stage="independent",
            execute=run_grounding_rule,
        ),
    )


def run_validation_rule_registry(
    runtime: ValidationRuntime,
    *,
    parallel_workers: int,
) -> List[ValidationIssue]:
    registry = build_validation_rule_registry()
    if parallel_workers > 1:
        run_validation_rules_in_parallel(
            runtime=runtime,
            registry=registry,
            parallel_workers=parallel_workers,
        )
    else:
        for rule in registry:
            runtime.issues_by_rule[rule.rule_id] = execute_rule(rule, runtime)
    ordered_issues: List[ValidationIssue] = []
    for rule in registry:
        ordered_issues.extend(runtime.issues_by_rule.get(rule.rule_id, []))
    return ordered_issues


def run_validation_rules_in_parallel(
    *,
    runtime: ValidationRuntime,
    registry: Sequence[ValidationRule],
    parallel_workers: int,
) -> None:
    bootstrap_rules = [rule for rule in registry if rule.stage == "bootstrap"]
    independent_rules = [rule for rule in registry if rule.stage == "independent"]
    dependent_rules = [rule for rule in registry if rule.stage == "dependent"]
    logger.info(
        log_event(
            runtime.ctx,
            role="generator",
            event="validation_parallel_start",
            module=LOGGER_NAME,
            fields={
                "report_id": runtime.request.report_id,
                "workers": parallel_workers,
                "tasks": [rule.rule_id for rule in registry],
            },
        )
    )
    max_workers = min(
        parallel_workers, max(1, len(bootstrap_rules) + len(independent_rules))
    )
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        bootstrap_futures = submit_rules(executor, bootstrap_rules, runtime)
        independent_futures = submit_rules(executor, independent_rules, runtime)
        try:
            collect_rule_results(bootstrap_futures, runtime)
        except Exception:
            cancel_futures(independent_futures)
            raise
        dependent_futures = submit_rules(executor, dependent_rules, runtime)
        collect_rule_results(independent_futures, runtime)
        collect_rule_results(dependent_futures, runtime)
    logger.info(
        log_event(
            runtime.ctx,
            role="generator",
            event="validation_parallel_complete",
            module=LOGGER_NAME,
            fields={
                "report_id": runtime.request.report_id,
                "workers": parallel_workers,
                "rule_issue_counts": {
                    rule.rule_id: len(runtime.issues_by_rule.get(rule.rule_id, []))
                    for rule in registry
                },
            },
        )
    )


def submit_rules(
    executor: ThreadPoolExecutor,
    rules: Iterable[ValidationRule],
    runtime: ValidationRuntime,
) -> List[Tuple[Future[List[ValidationIssue]], ValidationRule]]:
    return [(executor.submit(execute_rule, rule, runtime), rule) for rule in rules]


def collect_rule_results(
    futures: Sequence[Tuple[Future[List[ValidationIssue]], ValidationRule]],
    runtime: ValidationRuntime,
) -> None:
    for future, rule in futures:
        runtime.issues_by_rule[rule.rule_id] = future.result()


def cancel_futures(
    futures: Sequence[Tuple[Future[List[ValidationIssue]], ValidationRule]],
) -> None:
    for future, _rule in futures:
        future.cancel()


def execute_rule(
    rule: ValidationRule, runtime: ValidationRuntime
) -> List[ValidationIssue]:
    logger.info(
        log_event(
            runtime.ctx,
            role="generator",
            event="validation_rule_start",
            module=LOGGER_NAME,
            fields={"rule_id": rule.rule_id, "stage": rule.stage},
        )
    )
    issues = rule.execute(runtime)
    logger.info(
        log_event(
            runtime.ctx,
            role="generator",
            event="validation_rule_complete",
            module=LOGGER_NAME,
            fields={
                "rule_id": rule.rule_id,
                "stage": rule.stage,
                "issue_count": len(issues),
            },
        )
    )
    return issues
