"""re_add_projects

Revision ID: e2f3a4b5c6d7
Revises: cb6d044ff007
Create Date: 2026-06-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, None] = 'cb6d044ff007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: var olan tablolar yeniden olusturulmaz (taze/karma kurulum guvenli).
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    if 'projects' not in existing:
        op.create_table(
            'projects',
            sa.Column('id', sa.String(36), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(120), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
    if 'project_chats' not in existing:
        op.create_table(
            'project_chats',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('project_id', sa.String(36), nullable=False),
            sa.Column('chat_id', sa.String(36), nullable=False),
            sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['chat_id'], ['chats.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_project_chats_pc', 'project_chats', ['project_id', 'chat_id'], unique=True)
    if 'project_documents' not in existing:
        op.create_table(
            'project_documents',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('project_id', sa.String(36), nullable=False),
            sa.Column('document_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_project_docs_pd', 'project_documents', ['project_id', 'document_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_project_docs_pd', table_name='project_documents')
    op.drop_table('project_documents')
    op.drop_index('ix_project_chats_pc', table_name='project_chats')
    op.drop_table('project_chats')
    op.drop_table('projects')
