"""Shared pytest configuration.

- Tests are auto-marked by directory (unit / integration / fault), so ``-m unit`` works
  without decorating every test. ``--strict-markers`` rejects unknown markers.
- Logging configuration mutates the root logger; it is restored after every test.
"""

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

_DIR_MARKERS = {"unit": "unit", "integration": "integration", "fault": "fault"}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        for part in Path(str(item.fspath)).parts:
            marker = _DIR_MARKERS.get(part)
            if marker:
                item.add_marker(getattr(pytest.mark, marker))
                break


@pytest.fixture(autouse=True)
def _restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)
    logging.getLogger("uvicorn.access").disabled = False
