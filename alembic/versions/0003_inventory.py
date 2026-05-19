"""inventory movements

Revision ID: 0003_inventory
Revises: 0002_products
Create Date: 2026-05-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_inventory"
down_revision: str | Sequence[str] | None = "0002_products"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE movement_reason AS ENUM "
        "('order', 'cancel', 'admin_adjust', 'restock', 'seller_adjust')"
    )
    op.create_table(
        "inventory_movements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column(
            "reason",
            postgresql.ENUM(
                "order",
                "cancel",
                "admin_adjust",
                "restock",
                "seller_adjust",
                name="movement_reason",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_movements")),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            ondelete="CASCADE",
            name=op.f("fk_inventory_movements_product_id_products"),
        ),
    )
    op.create_index(
        "ix_inventory_movements_product_id", "inventory_movements", ["product_id"]
    )
    op.create_index(
        "ix_inventory_movements_order_id", "inventory_movements", ["order_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_inventory_movements_order_id", table_name="inventory_movements")
    op.drop_index("ix_inventory_movements_product_id", table_name="inventory_movements")
    op.drop_table("inventory_movements")
    op.execute("DROP TYPE movement_reason")
