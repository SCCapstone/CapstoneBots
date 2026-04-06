"""Make author_id and added_by nullable for account deletion

Revision ID: 002
Create Date: 2026-02-25

This migration updates commits.author_id and
project_members.added_by to be nullable with ON DELETE SET NULL, so that
deleting a user account can anonymize their contributions without breaking
FK constraints.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Revision identifiers
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade():
    # Make commits.author_id nullable and add ON DELETE SET NULL
    op.alter_column('commits', 'author_id', existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.drop_constraint('commits_author_id_fkey', 'commits', type_='foreignkey')
    op.create_foreign_key(
        'commits_author_id_fkey', 'commits', 'users',
        ['author_id'], ['user_id'], ondelete='SET NULL'
    )

    # Add ON DELETE SET NULL to project_members.added_by
    # (already nullable, just needs the ondelete behavior)
    op.drop_constraint('project_members_added_by_fkey', 'project_members', type_='foreignkey')
    op.create_foreign_key(
        'project_members_added_by_fkey', 'project_members', 'users',
        ['added_by'], ['user_id'], ondelete='SET NULL'
    )


def downgrade():
    # Revert commits.author_id to NOT NULL without ON DELETE SET NULL
    op.drop_constraint('commits_author_id_fkey', 'commits', type_='foreignkey')
    op.create_foreign_key(
        'commits_author_id_fkey', 'commits', 'users',
        ['author_id'], ['user_id']
    )
    op.alter_column('commits', 'author_id', existing_type=postgresql.UUID(as_uuid=True), nullable=False)

    # Revert project_members.added_by FK to no ON DELETE behavior
    op.drop_constraint('project_members_added_by_fkey', 'project_members', type_='foreignkey')
    op.create_foreign_key(
        'project_members_added_by_fkey', 'project_members', 'users',
        ['added_by'], ['user_id']
    )
