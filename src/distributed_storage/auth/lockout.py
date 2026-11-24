"""Failed-login backoff (pure function; state lives in PostgreSQL, no Redis)."""


def lockout_seconds(
    failed_count: int, *, max_failures: int, base_seconds: int, max_seconds: int
) -> int:
    """Seconds an account stays locked after ``failed_count`` consecutive failures.

    Zero below the threshold; then ``base`` doubling with each further failure, capped.
    """
    if failed_count < max_failures:
        return 0
    exponent = min(failed_count - max_failures, 30)
    return min(base_seconds * (2**exponent), max_seconds)
