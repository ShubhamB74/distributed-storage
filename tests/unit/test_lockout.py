import pytest

from distributed_storage.auth.lockout import lockout_seconds


@pytest.mark.parametrize(
    ("failures", "expected"),
    [(0, 0), (1, 0), (4, 0), (5, 30), (6, 60), (7, 120), (8, 240), (12, 3600), (500, 3600)],
)
def test_backoff_doubles_from_the_threshold_and_is_capped(failures: int, expected: int) -> None:
    assert lockout_seconds(failures, max_failures=5, base_seconds=30, max_seconds=3600) == expected


def test_huge_counts_do_not_overflow() -> None:
    assert lockout_seconds(10**9, max_failures=1, base_seconds=1, max_seconds=60) == 60
