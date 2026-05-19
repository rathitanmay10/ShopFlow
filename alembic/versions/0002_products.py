"""products and categories

Revision ID: 0002_products
Revises: 0001_users
Create Date: 2026-05-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_products"
down_revision: str | Sequence[str] | None = "0001_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
        sa.UniqueConstraint("name", name=op.f("uq_categories_name")),
        sa.UniqueConstraint("slug", name=op.f("uq_categories_slug")),
    )

    op.execute("CREATE TYPE product_status AS ENUM ('active', 'out_of_stock', 'discontinued')")
    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("seller_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stock_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "status",
            postgresql.ENUM(
                "active",
                "out_of_stock",
                "discontinued",
                name="product_status",
                create_type=False,
            ),
            nullable=False,
            server_default="active",
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint("sku", name=op.f("uq_products_sku")),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            ondelete="SET NULL",
            name=op.f("fk_products_category_id_categories"),
        ),
        sa.ForeignKeyConstraint(
            ["seller_id"],
            ["users.id"],
            ondelete="CASCADE",
            name=op.f("fk_products_seller_id_users"),
        ),
    )
    op.create_index("ix_products_seller_id", "products", ["seller_id"])
    op.create_index("ix_products_category_id", "products", ["category_id"])
    op.create_index("ix_products_deleted_at", "products", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_products_deleted_at", table_name="products")
    op.drop_index("ix_products_category_id", table_name="products")
    op.drop_index("ix_products_seller_id", table_name="products")
    op.drop_table("products")
    op.execute("DROP TYPE product_status")
    op.drop_table("categories")
