"""Storage node health state machine (ADR-0010, Phase 1 subset).

Pure functions: no I/O. States: healthy, suspect, down, retired. Hysteresis: several consecutive
failures to degrade, several consecutive successes to recover. ``retired`` is terminal.
"""

from dataclasses import dataclass
from enum import StrEnum

COUNTER_CAP = 1_000_000


class NodeState(StrEnum):
    HEALTHY = "healthy"
    SUSPECT = "suspect"
    DOWN = "down"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class HealthThresholds:
    failures_to_suspect: int = 2
    failures_to_down: int = 5
    successes_to_recover: int = 3

    def __post_init__(self) -> None:
        if min(self.failures_to_suspect, self.failures_to_down, self.successes_to_recover) < 1:
            raise ValueError("health thresholds must be at least 1")
        if self.failures_to_suspect > self.failures_to_down:
            raise ValueError("failures_to_suspect must not exceed failures_to_down")


@dataclass(frozen=True, slots=True)
class HealthRecord:
    state: NodeState
    consecutive_failures: int = 0
    consecutive_successes: int = 0


def apply_probe(record: HealthRecord, success: bool, thresholds: HealthThresholds) -> HealthRecord:
    """Return the record after one probe or observed operation outcome."""
    if record.state is NodeState.RETIRED:
        return record

    if success:
        successes = min(record.consecutive_successes + 1, COUNTER_CAP)
        state = record.state
        if (
            state in (NodeState.SUSPECT, NodeState.DOWN)
            and successes >= thresholds.successes_to_recover
        ):
            state = NodeState.HEALTHY
        return HealthRecord(state=state, consecutive_failures=0, consecutive_successes=successes)

    failures = min(record.consecutive_failures + 1, COUNTER_CAP)
    state = record.state
    if state in (NodeState.HEALTHY, NodeState.SUSPECT):
        if failures >= thresholds.failures_to_down:
            state = NodeState.DOWN
        elif failures >= thresholds.failures_to_suspect:
            state = NodeState.SUSPECT
    return HealthRecord(state=state, consecutive_failures=failures, consecutive_successes=0)
