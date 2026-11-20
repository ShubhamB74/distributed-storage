from pathlib import Path

import pytest

from distributed_storage.storage.base import StorageNode
from distributed_storage.storage.local import LocalBlobStorage

# Register new adapters here (SeaweedFS, S3, ...): every adapter must pass the whole
# conformance suite in test_storage_node_conformance.py.
ADAPTERS = ["local"]


@pytest.fixture(params=ADAPTERS)
def node(request: pytest.FixtureRequest, tmp_path: Path) -> StorageNode:
    if request.param == "local":
        return LocalBlobStorage(tmp_path / "node")
    raise AssertionError(f"unknown adapter {request.param!r}")
