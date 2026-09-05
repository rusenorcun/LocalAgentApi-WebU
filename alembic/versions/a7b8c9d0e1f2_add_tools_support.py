"""add tools support: messages.hidden/tool_calls_json/kind + models.supports_tools

Revision ID: a7b8c9d0e1f2
Revises: d4e5f6a7b8c9
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = "a7b8c9d0e1f2"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def _cols(insp, table):
    try:
        return {c["name"] for c in insp.get_columns(table)}
    except Exception:
        return set()


def upgrade():
    insp = sa.inspect(op.get_bind())
    mcols = _cols(insp, "messages")
    if "hidden" not in mcols:
        op.add_column("messages", sa.Column("hidden", sa.Boolean(), nullable=False, server_default="0"))
    if "tool_calls_json" not in mcols:
        op.add_column("messages", sa.Column("tool_calls_json", sa.Text(), nullable=True))
    if "kind" not in mcols:
        op.add_column("messages", sa.Column("kind", sa.String(length=32), nullable=True))
    if "supports_tools" not in _cols(insp, "models"):
        op.add_column("models", sa.Column("supports_tools", sa.Boolean(), nullable=False, server_default="0"))


def downgrade():
    pass
