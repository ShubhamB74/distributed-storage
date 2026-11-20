"""Storage nodes, stripes and shard placements (ADR-0005, ADR-0006, ADR-0014)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from distributed_storage.db.base import Base


class StorageNode(Base):
    __tablename__ = "storage_nodes"
    __table_args__ = (
        UniqueConstraint("name"),
        CheckConstraint("adapter_type IN ('local')", name="adapter_type_valid"),
        CheckConstraint("state IN ('healthy', 'suspect', 'down', 'retired')", name="state_valid"),
        CheckConstraint("consecutive_failures >= 0", name="consecutive_failures_nonneg"),
        CheckConstraint("consecutive_successes >= 0", name="consecutive_successes_nonneg"),
        Index("ix_storage_nodes_state", "state"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text)
    adapter_type: Mapped[str] = mapped_column(Text)
    # Non-secret reference to where the node lives (for example the blob root directory).
    location_ref: Mapped[str] = mapped_column(Text)
    failure_domain_id: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text, server_default=text("'healthy'"))
    consecutive_failures: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    consecutive_successes: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Stripe(Base):
    __tablename__ = "stripes"
    __table_args__ = (
        UniqueConstraint("file_version_id", "stripe_index", name="uq_stripes_version_index"),
        CheckConstraint("stripe_index >= 0", name="stripe_index_nonneg"),
        CheckConstraint("data_shards >= 1", name="data_shards_positive"),
        CheckConstraint("parity_shards >= 0", name="parity_shards_nonneg"),
        CheckConstraint("data_length > 0", name="data_length_positive"),
        CheckConstraint("padding >= 0", name="padding_nonneg"),
        CheckConstraint("state IN ('planned', 'stored', 'deleting')", name="state_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    file_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("file_versions.id", ondelete="RESTRICT")
    )
    stripe_index: Mapped[int] = mapped_column(Integer)
    codec_id: Mapped[str] = mapped_column(Text)
    data_shards: Mapped[int] = mapped_column(Integer)
    parity_shards: Mapped[int] = mapped_column(Integer)
    data_length: Mapped[int] = mapped_column(BigInteger)
    padding: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    state: Mapped[str] = mapped_column(Text, server_default=text("'planned'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ShardPlacement(Base):
    """One shard on one node. Its UUID is also the blob key on the node (ADR-0014)."""

    __tablename__ = "shard_placements"
    __table_args__ = (
        UniqueConstraint("stripe_id", "shard_index", name="uq_shard_placements_stripe_index"),
        CheckConstraint("shard_index >= 0", name="shard_index_nonneg"),
        CheckConstraint(
            "content_hash IS NULL OR octet_length(content_hash) = 32", name="content_hash_length"
        ),
        CheckConstraint("length IS NULL OR length > 0", name="length_positive"),
        CheckConstraint("generation >= 0", name="generation_nonneg"),
        CheckConstraint("state IN ('planned', 'stored', 'deleting')", name="state_valid"),
        CheckConstraint(
            "state <> 'stored' OR (content_hash IS NOT NULL AND length IS NOT NULL)",
            name="stored_has_hash_and_length",
        ),
        Index("ix_shard_placements_node_id", "node_id"),
        Index("ix_shard_placements_state", "state"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    stripe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stripes.id", ondelete="RESTRICT"))
    shard_index: Mapped[int] = mapped_column(Integer)
    node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("storage_nodes.id", ondelete="RESTRICT"))
    # NULL while the placement is only planned; required once it is stored.
    content_hash: Mapped[bytes | None] = mapped_column(LargeBinary)
    length: Mapped[int | None] = mapped_column(BigInteger)
    state: Mapped[str] = mapped_column(Text, server_default=text("'planned'"))
    # Fencing token for repair (Phase 4).
    generation: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
