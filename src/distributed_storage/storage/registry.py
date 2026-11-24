"""Storage node registry and passive health tracking (PostgreSQL is authoritative)."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from distributed_storage.core.config import Settings
from distributed_storage.db.models import StorageNode as StorageNodeRow
from distributed_storage.storage.health import (
    HealthRecord,
    HealthThresholds,
    NodeState,
    apply_probe,
)

logger = logging.getLogger("distributed_storage.storage")


def thresholds_from(settings: Settings) -> HealthThresholds:
    return HealthThresholds(
        failures_to_suspect=settings.node_failures_to_suspect,
        failures_to_down=settings.node_failures_to_down,
        successes_to_recover=settings.node_successes_to_recover,
    )


async def ensure_local_node(session: AsyncSession, settings: Settings) -> StorageNodeRow:
    """Idempotently register the configured local node. The caller commits.

    An existing row is left untouched: changing a node's failure domain would invalidate
    placements, so that must be a deliberate operation, not a side effect of a restart.
    """
    await session.execute(
        pg_insert(StorageNodeRow)
        .values(
            name=settings.local_node_name,
            adapter_type="local",
            location_ref=str(settings.blob_root),
            failure_domain_id=settings.local_node_name,
        )
        .on_conflict_do_nothing(index_elements=["name"])
    )
    node = await session.scalar(
        select(StorageNodeRow).where(StorageNodeRow.name == settings.local_node_name)
    )
    if node is None:
        raise RuntimeError("storage node registration failed")
    return node


async def record_probe(
    session: AsyncSession,
    *,
    name: str,
    success: bool,
    thresholds: HealthThresholds,
    now: datetime | None = None,
) -> HealthRecord | None:
    """Apply one health observation to the node row. The caller commits."""
    node = await session.scalar(
        select(StorageNodeRow).where(StorageNodeRow.name == name).with_for_update()
    )
    if node is None:
        return None
    updated = apply_probe(
        HealthRecord(
            state=NodeState(node.state),
            consecutive_failures=node.consecutive_failures,
            consecutive_successes=node.consecutive_successes,
        ),
        success,
        thresholds,
    )
    node.state = updated.state.value
    node.consecutive_failures = updated.consecutive_failures
    node.consecutive_successes = updated.consecutive_successes
    if success:
        node.last_seen_at = now or datetime.now(UTC)
    return updated


class NodeHealthTracker:
    """Best-effort passive health recording: never raises into a request."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        node_name: str,
        thresholds: HealthThresholds,
    ) -> None:
        self._session_factory = session_factory
        self._node_name = node_name
        self._thresholds = thresholds

    async def observe(self, success: bool) -> None:
        try:
            async with self._session_factory() as session:
                await record_probe(
                    session, name=self._node_name, success=success, thresholds=self._thresholds
                )
                await session.commit()
        except Exception:
            logger.warning("node_health_record_failed", exc_info=True)
