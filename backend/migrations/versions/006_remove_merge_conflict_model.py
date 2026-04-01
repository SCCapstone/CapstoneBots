"""Remove merge_conflict model and table.

Revision ID: 006
Revises: 005
Create Date: 2026-03-31 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the merge_conflicts table
    op.drop_table('merge_conflicts')


def downgrade() -> None:
    # Recreate merge_conflicts table if reverting
    op.create_table(
        'merge_conflicts',
        sa.Column('conflict_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_commit_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('target_branch_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('object_name', sa.String(), nullable=False),
        sa.Column('conflict_type', sa.String(), nullable=False),
        sa.Column('resolved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.project_id'], ),
        sa.ForeignKeyConstraint(['source_commit_id'], ['commits.commit_id'], ),
        sa.ForeignKeyConstraint(['target_branch_id'], ['branches.branch_id'], ),
        sa.PrimaryKeyConstraint('conflict_id')
    )
