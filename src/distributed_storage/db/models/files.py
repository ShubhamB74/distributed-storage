"""Files and their versions (Phase 1 data model, ADR-0009)."""

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


class File(Base):
    __tablename__ = "files"
    __table_args__ = (Index("ix_files_owner_created", "owner_id", "created_at", "id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    # Set when a version commits. Deferrable so a file and its first version can be inserted in
    # either order inside one transaction.
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "file_versions.id",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
            name="fk_files_current_version_id_file_versions",
        )
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FileVersion(Base):
    __tablename__ = "file_versions"
    __table_args__ = (
        UniqueConstraint("file_id", "version_number", name="uq_file_versions_file_version"),
        CheckConstraint("version_number >= 1", name="version_number_positive"),
        CheckConstraint("state IN ('planned', 'committed', 'deleting')", name="state_valid"),
        CheckConstraint("size_bytes > 0", name="size_bytes_positive"),
        CheckConstraint("octet_length(metadata_envelope) <= 65536", name="metadata_envelope_cap"),
        CheckConstraint(
            "state <> 'committed' OR committed_at IS NOT NULL", name="committed_has_timestamp"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("files.id", ondelete="RESTRICT"))
    version_number: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(Text, server_default=text("'planned'"))
    # Ciphertext size in bytes (plaintext size in the Phase 1 development-only path).
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    # Opaque to the server. Phase 1 stores "dev-plain-v0" JSON; Phase 2 an encrypted envelope.
    metadata_format: Mapped[str] = mapped_column(Text)
    metadata_envelope: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
