from itertools import product

import pytest

from distributed_storage.storage.health import (
    COUNTER_CAP,
    HealthRecord,
    HealthThresholds,
    NodeState,
    apply_probe,
)

THRESHOLDS = HealthThresholds(failures_to_suspect=2, failures_to_down=4, successes_to_recover=3)


def _run(record: HealthRecord, outcomes: list[bool]) -> HealthRecord:
    for outcome in outcomes:
        record = apply_probe(record, outcome, THRESHOLDS)
    return record


@pytest.mark.parametrize(
    ("suspect", "down", "recover"), [(0, 1, 1), (1, 0, 1), (1, 1, 0), (3, 2, 1)]
)
def test_invalid_thresholds_are_rejected(suspect: int, down: int, recover: int) -> None:
    with pytest.raises(ValueError):
        HealthThresholds(
            failures_to_suspect=suspect, failures_to_down=down, successes_to_recover=recover
        )


def test_failures_degrade_in_steps() -> None:
    record = HealthRecord(NodeState.HEALTHY)
    states = []
    for _ in range(5):
        record = apply_probe(record, False, THRESHOLDS)
        states.append(record.state)
    assert states == [
        NodeState.HEALTHY,
        NodeState.SUSPECT,
        NodeState.SUSPECT,
        NodeState.DOWN,
        NodeState.DOWN,
    ]


def test_a_single_success_resets_the_failure_streak_without_changing_state() -> None:
    record = _run(HealthRecord(NodeState.HEALTHY), [False, False])
    assert record.state is NodeState.SUSPECT
    record = apply_probe(record, True, THRESHOLDS)
    assert record.state is NodeState.SUSPECT
    assert record.consecutive_failures == 0
    assert record.consecutive_successes == 1


@pytest.mark.parametrize("start", [NodeState.SUSPECT, NodeState.DOWN])
def test_recovery_needs_consecutive_successes(start: NodeState) -> None:
    record = HealthRecord(start)
    record = _run(record, [True, True])
    assert record.state is start
    assert _run(record, [True]).state is NodeState.HEALTHY


def test_a_failure_during_recovery_restarts_the_count() -> None:
    record = _run(HealthRecord(NodeState.DOWN), [True, True, False, True, True])
    assert record.state is NodeState.DOWN
    assert _run(record, [True]).state is NodeState.HEALTHY


def test_retired_is_terminal() -> None:
    record = HealthRecord(NodeState.RETIRED)
    assert apply_probe(record, True, THRESHOLDS) == record
    assert apply_probe(record, False, THRESHOLDS) == record


def test_counters_are_capped() -> None:
    record = HealthRecord(NodeState.HEALTHY, consecutive_successes=COUNTER_CAP)
    assert apply_probe(record, True, THRESHOLDS).consecutive_successes == COUNTER_CAP


def test_every_short_sequence_from_every_state_holds_the_invariants() -> None:
    order = {NodeState.HEALTHY: 0, NodeState.SUSPECT: 1, NodeState.DOWN: 2}
    for start in (NodeState.HEALTHY, NodeState.SUSPECT, NodeState.DOWN):
        for outcomes in product([True, False], repeat=8):
            record = HealthRecord(start)
            for outcome in outcomes:
                before = record
                record = apply_probe(record, outcome, THRESHOLDS)
                # One streak counter is always zero.
                assert record.consecutive_failures == 0 or record.consecutive_successes == 0
                # Failures never improve the state; successes never worsen it.
                if outcome:
                    assert order[record.state] <= order[before.state]
                else:
                    assert order[record.state] >= order[before.state]
                # Recovery only happens after enough consecutive successes.
                if order[record.state] < order[before.state]:
                    assert record.consecutive_successes >= THRESHOLDS.successes_to_recover
                # Degradation only happens after enough consecutive failures.
                if order[record.state] > order[before.state]:
                    assert record.consecutive_failures >= THRESHOLDS.failures_to_suspect
