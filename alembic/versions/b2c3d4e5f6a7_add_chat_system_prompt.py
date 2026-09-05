"""add chat system_prompt column

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-14 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = [c['name'] for c in sa.inspect(bind).get_columns('chats')]
    if 'system_prompt' not in cols:
        with op.batch_alter_table('chats') as batch_op:
            batch_op.add_column(sa.Column('system_prompt', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('chats') as batch_op:
        batch_op.drop_column('system_prompt')
