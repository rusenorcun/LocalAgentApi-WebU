"""add model is_vision column

Revision ID: f1a2b3c4d5e6
Revises: e2f3a4b5c6d7
Create Date: 2026-06-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'f1a2b3c4d5e6'
down_revision = 'e2f3a4b5c6d7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = [c['name'] for c in sa.inspect(bind).get_columns('models')]
    if 'is_vision' in cols:
        return
    with op.batch_alter_table('models') as batch_op:
        batch_op.add_column(
            sa.Column('is_vision', sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table('models') as batch_op:
        batch_op.drop_column('is_vision')
