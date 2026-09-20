"""accounts + devices

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users: new nullable columns for accounts + OAuth
    op.add_column("users", sa.Column("name", sa.String(120), nullable=True))
    op.add_column("users", sa.Column("provider", sa.String(32), nullable=True))
    op.add_column("users", sa.Column("provider_id", sa.String(255), nullable=True))
    op.create_index("ix_users_provider_provider_id",
                    "users", ["provider", "provider_id"])

    # devices
    op.create_table(
        "devices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("os", sa.String(32), nullable=True),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column("token_prefix", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_devices_user_id", "devices", ["user_id"])
    op.create_index("ix_devices_token_prefix", "devices", ["token_prefix"])

    # device_codes
    op.create_table(
        "device_codes",
        sa.Column("code", sa.String(16), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("device_name", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_device_codes_user_id", "device_codes", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_device_codes_user_id", table_name="device_codes")
    op.drop_table("device_codes")
    op.drop_index("ix_devices_token_prefix", table_name="devices")
    op.drop_index("ix_devices_user_id", table_name="devices")
    op.drop_table("devices")
    op.drop_index("ix_users_provider_provider_id", table_name="users")
    op.drop_column("users", "provider_id")
    op.drop_column("users", "provider")
    op.drop_column("users", "name")
