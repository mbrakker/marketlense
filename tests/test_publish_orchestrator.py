from __future__ import annotations

import src.orchestrators.publish_orchestrator as publish_orchestrator

from ._test_publish_orchestrator._shared import *  # noqa: F401,F403
from ._test_publish_orchestrator.cases_01_publish_runs_when_processed import *  # noqa: F401,F403
from ._test_publish_orchestrator.cases_02_publish_batches_preflight_and_term import *  # noqa: F401,F403
from ._test_publish_orchestrator.cases_03_report_queue_cohort import *  # noqa: F401,F403


def test_publish_interval_waits_before_next_write() -> None:
    sleeps: list[float] = []
    clock = iter((150.0, 220.0))

    started_at = publish_orchestrator._wait_for_publish_interval(
        previous_write_started_at=100.0,
        minimum_interval_seconds=120,
        monotonic_fn=lambda: next(clock),
        sleep_fn=sleeps.append,
    )

    assert sleeps == [70.0]
    assert started_at == 220.0
