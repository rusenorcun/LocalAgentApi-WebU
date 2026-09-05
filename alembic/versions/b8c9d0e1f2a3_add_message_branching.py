"""add message branching: parent_id + active (+ lineer backfill)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("messages")}
    added_parent = False
    if "parent_id" not in cols:
        op.add_column("messages", sa.Column("parent_id", sa.Integer(), nullable=True))
        added_parent = True
    if "active" not in cols:
        op.add_column("messages", sa.Column("active", sa.Boolean(), nullable=False, server_default="1"))
    # Backfill: yalniz parent_id yeni eklendiyse mevcut lineer gecmisi zincire cevir.
    if added_parent:
        conn = op.get_bind()
        rows = conn.execute(sa.text(
            "SELECT id, chat_id FROM messages ORDER BY chat_id, created_at, id"
        )).fetchall()
        prev_chat = None
        prev_id = None
        for r in rows:
            mid, cid = r[0], r[1]
            if cid != prev_chat:
                prev_chat, prev_id = cid, None
            if prev_id is not None:
                conn.execute(sa.text("UPDATE messages SET parent_id=:p WHERE id=:i"),
                             {"p": prev_id, "i": mid})
            prev_id = mid


def downgrade():
    pass
