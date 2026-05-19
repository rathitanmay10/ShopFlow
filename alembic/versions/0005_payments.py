"""payments and payment_events

Revision ID: 0005_payments
Revises: 0004_orders
Create Date: 2026-05-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_payments"
down_revision: str | Sequence[str] | None = "0004_orders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE payment_status AS ENUM ('initiated', 'processing', 'success', 'failed')"
    )
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column(
            "status",
            postgresql.ENUM(
                "initiated",
                "processing",
                "success",
                "failed",
                name="payment_status",
                create_type=False,
            ),
            nullable=False,
            server_default="initiated",
        ),
        sa.Column("external_txn_id", sa.String(length=64), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        sa.UniqueConstraint("order_id", name=op.f("uq_payments_order_id")),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            ondelete="CASCADE",
            name=op.f("fk_payments_order_id_orders"),
        ),
    )
    op.create_index("ix_payments_order_id", "payments", ["order_id"])

    op.create_table(
        "payment_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "from_status",
            postgresql.ENUM(
                "initiated",
                "processing",
                "success",
                "failed",
                name="payment_status",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "to_status",
            postgresql.ENUM(
                "initiated",
                "processing",
                "success",
                "failed",
                name="payment_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_events")),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payments.id"],
            ondelete="CASCADE",
            name=op.f("fk_payment_events_payment_id_payments"),
        ),
    )
    op.create_index("ix_payment_events_payment_id", "payment_events", ["payment_id"])


def downgrade() -> None:
    op.drop_index("ix_payment_events_payment_id", table_name="payment_events")
    op.drop_table("payment_events")
    op.drop_index("ix_payments_order_id", table_name="payments")
    op.drop_table("payments")
    op.execute("DROP TYPE payment_status")
