"""phase 1 schema: identity, storage, files, audit

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-18

"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_pk() -> sa.Column[Any]:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _created_at() -> sa.Column[Any]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "users",
        _uuid_pk(),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("auth_scheme", sa.Text(), nullable=False),
        sa.Column("auth_verifier", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'active'"), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "email = lower(btrim(email)) AND email <> ''", name=op.f("ck_users_email_normalized")
        ),
        sa.CheckConstraint("status IN ('active', 'disabled')", name=op.f("ck_users_status_valid")),
        sa.CheckConstraint(
            "failed_login_count >= 0", name=op.f("ck_users_failed_login_count_nonneg")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )

    op.create_table(
        "devices",
        _uuid_pk(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("ed25519_public_key", sa.LargeBinary(), nullable=True),
        sa.Column("x25519_public_key", sa.LargeBinary(), nullable=True),
        _created_at(),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "ed25519_public_key IS NULL OR octet_length(ed25519_public_key) = 32",
            name=op.f("ck_devices_ed25519_public_key_length"),
        ),
        sa.CheckConstraint(
            "x25519_public_key IS NULL OR octet_length(x25519_public_key) = 32",
            name=op.f("ck_devices_x25519_public_key_length"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_devices_user_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_devices")),
        sa.UniqueConstraint("user_id", "name", name=op.f("uq_devices_user_id_name")),
    )

    op.create_table(
        "sessions",
        _uuid_pk(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        _created_at(),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32", name=op.f("ck_sessions_token_hash_length")
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_sessions_expiry_after_creation")
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            name=op.f("fk_sessions_device_id_devices"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sessions_token_hash")),
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)
    op.create_index(op.f("ix_sessions_device_id"), "sessions", ["device_id"], unique=False)

    op.create_table(
        "storage_nodes",
        _uuid_pk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("adapter_type", sa.Text(), nullable=False),
        sa.Column("location_ref", sa.Text(), nullable=False),
        sa.Column("failure_domain_id", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), server_default=sa.text("'healthy'"), nullable=False),
        sa.Column(
            "consecutive_failures", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "consecutive_successes", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.CheckConstraint(
            "adapter_type IN ('local')", name=op.f("ck_storage_nodes_adapter_type_valid")
        ),
        sa.CheckConstraint(
            "state IN ('healthy', 'suspect', 'down', 'retired')",
            name=op.f("ck_storage_nodes_state_valid"),
        ),
        sa.CheckConstraint(
            "consecutive_failures >= 0", name=op.f("ck_storage_nodes_consecutive_failures_nonneg")
        ),
        sa.CheckConstraint(
            "consecutive_successes >= 0",
            name=op.f("ck_storage_nodes_consecutive_successes_nonneg"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_storage_nodes")),
        sa.UniqueConstraint("name", name=op.f("uq_storage_nodes_name")),
    )
    op.create_index(op.f("ix_storage_nodes_state"), "storage_nodes", ["state"], unique=False)

    # files.current_version_id references file_versions, which references files:
    # create files without that foreign key first and add it after file_versions exists.
    op.create_table(
        "files",
        _uuid_pk(),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_files_owner_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_files")),
    )
    op.create_index(
        op.f("ix_files_owner_created"), "files", ["owner_id", "created_at", "id"], unique=False
    )

    op.create_table(
        "file_versions",
        _uuid_pk(),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("state", sa.Text(), server_default=sa.text("'planned'"), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("metadata_format", sa.Text(), nullable=False),
        sa.Column("metadata_envelope", sa.LargeBinary(), nullable=False),
        _created_at(),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "version_number >= 1", name=op.f("ck_file_versions_version_number_positive")
        ),
        sa.CheckConstraint(
            "state IN ('planned', 'committed', 'deleting')",
            name=op.f("ck_file_versions_state_valid"),
        ),
        sa.CheckConstraint("size_bytes > 0", name=op.f("ck_file_versions_size_bytes_positive")),
        sa.CheckConstraint(
            "octet_length(metadata_envelope) <= 65536",
            name=op.f("ck_file_versions_metadata_envelope_cap"),
        ),
        sa.CheckConstraint(
            "state <> 'committed' OR committed_at IS NOT NULL",
            name=op.f("ck_file_versions_committed_has_timestamp"),
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["files.id"],
            name=op.f("fk_file_versions_file_id_files"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_file_versions")),
        sa.UniqueConstraint(
            "file_id", "version_number", name=op.f("uq_file_versions_file_version")
        ),
    )

    op.create_foreign_key(
        op.f("fk_files_current_version_id_file_versions"),
        "files",
        "file_versions",
        ["current_version_id"],
        ["id"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )

    op.create_table(
        "stripes",
        _uuid_pk(),
        sa.Column("file_version_id", sa.Uuid(), nullable=False),
        sa.Column("stripe_index", sa.Integer(), nullable=False),
        sa.Column("codec_id", sa.Text(), nullable=False),
        sa.Column("data_shards", sa.Integer(), nullable=False),
        sa.Column("parity_shards", sa.Integer(), nullable=False),
        sa.Column("data_length", sa.BigInteger(), nullable=False),
        sa.Column("padding", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("state", sa.Text(), server_default=sa.text("'planned'"), nullable=False),
        _created_at(),
        sa.CheckConstraint("stripe_index >= 0", name=op.f("ck_stripes_stripe_index_nonneg")),
        sa.CheckConstraint("data_shards >= 1", name=op.f("ck_stripes_data_shards_positive")),
        sa.CheckConstraint("parity_shards >= 0", name=op.f("ck_stripes_parity_shards_nonneg")),
        sa.CheckConstraint("data_length > 0", name=op.f("ck_stripes_data_length_positive")),
        sa.CheckConstraint("padding >= 0", name=op.f("ck_stripes_padding_nonneg")),
        sa.CheckConstraint(
            "state IN ('planned', 'stored', 'deleting')", name=op.f("ck_stripes_state_valid")
        ),
        sa.ForeignKeyConstraint(
            ["file_version_id"],
            ["file_versions.id"],
            name=op.f("fk_stripes_file_version_id_file_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stripes")),
        sa.UniqueConstraint(
            "file_version_id", "stripe_index", name=op.f("uq_stripes_version_index")
        ),
    )

    op.create_table(
        "shard_placements",
        _uuid_pk(),
        sa.Column("stripe_id", sa.Uuid(), nullable=False),
        sa.Column("shard_index", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.Uuid(), nullable=False),
        sa.Column("content_hash", sa.LargeBinary(), nullable=True),
        sa.Column("length", sa.BigInteger(), nullable=True),
        sa.Column("state", sa.Text(), server_default=sa.text("'planned'"), nullable=False),
        sa.Column("generation", sa.Integer(), server_default=sa.text("0"), nullable=False),
        _created_at(),
        sa.CheckConstraint("shard_index >= 0", name=op.f("ck_shard_placements_shard_index_nonneg")),
        sa.CheckConstraint(
            "content_hash IS NULL OR octet_length(content_hash) = 32",
            name=op.f("ck_shard_placements_content_hash_length"),
        ),
        sa.CheckConstraint(
            "length IS NULL OR length > 0", name=op.f("ck_shard_placements_length_positive")
        ),
        sa.CheckConstraint("generation >= 0", name=op.f("ck_shard_placements_generation_nonneg")),
        sa.CheckConstraint(
            "state IN ('planned', 'stored', 'deleting')",
            name=op.f("ck_shard_placements_state_valid"),
        ),
        sa.CheckConstraint(
            "state <> 'stored' OR (content_hash IS NOT NULL AND length IS NOT NULL)",
            name=op.f("ck_shard_placements_stored_has_hash_and_length"),
        ),
        sa.ForeignKeyConstraint(
            ["node_id"],
            ["storage_nodes.id"],
            name=op.f("fk_shard_placements_node_id_storage_nodes"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["stripe_id"],
            ["stripes.id"],
            name=op.f("fk_shard_placements_stripe_id_stripes"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shard_placements")),
        sa.UniqueConstraint(
            "stripe_id", "shard_index", name=op.f("uq_shard_placements_stripe_index")
        ),
    )
    op.create_index(
        op.f("ix_shard_placements_node_id"), "shard_placements", ["node_id"], unique=False
    )
    op.create_index(op.f("ix_shard_placements_state"), "shard_placements", ["state"], unique=False)

    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("resource_type", sa.Text(), nullable=False),
        sa.Column("resource_id", sa.Text(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "outcome IN ('success', 'denied', 'failure')",
            name=op.f("ck_audit_events_outcome_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_audit_events_actor_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            name=op.f("fk_audit_events_device_id_devices"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(
        op.f("ix_audit_events_occurred_at"), "audit_events", ["occurred_at"], unique=False
    )
    op.create_index(
        op.f("ix_audit_events_actor_occurred"),
        "audit_events",
        ["actor_user_id", "occurred_at"],
        unique=False,
    )

    # Append-only enforcement. Not tamper evidence: a database owner can drop these triggers.
    op.execute(
        """
        CREATE FUNCTION audit_events_forbid_change() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_append_only
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION audit_events_forbid_change()
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_no_truncate
        BEFORE TRUNCATE ON audit_events
        FOR EACH STATEMENT EXECUTE FUNCTION audit_events_forbid_change()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER audit_events_no_truncate ON audit_events")
    op.execute("DROP TRIGGER audit_events_append_only ON audit_events")
    op.execute("DROP FUNCTION audit_events_forbid_change()")
    op.drop_table("audit_events")
    op.drop_table("shard_placements")
    op.drop_table("stripes")
    op.drop_constraint(
        op.f("fk_files_current_version_id_file_versions"), "files", type_="foreignkey"
    )
    op.drop_table("file_versions")
    op.drop_table("files")
    op.drop_table("storage_nodes")
    op.drop_table("sessions")
    op.drop_table("devices")
    op.drop_table("users")
