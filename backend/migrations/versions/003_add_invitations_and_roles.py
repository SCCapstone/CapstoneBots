"""Add project_invitations table and update member roles

Revision ID: 003
Create Date: 2026-02-25

Creates the project_invitations table for the invitation-based collaboration flow.
Migrates existing project_members.role from "member" to "editor".
Adds composite indexes for performance.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Revision identifiers
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create project_invitations table
    op.create_table(
        'project_invitations',
        sa.Column('invitation_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('projects.project_id', ondelete='CASCADE'), nullable=False),
        sa.Column('inviter_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False),
        sa.Column('invitee_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=True),
        sa.Column('invitee_email', sa.String, nullable=False),
        sa.Column('role', sa.String, nullable=False, server_default='editor'),
        sa.Column('status', sa.String, nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime, nullable=False),
        sa.Column('responded_at', sa.DateTime, nullable=True),
    )

    # 2. Add indexes on project_invitations
    op.create_index(
        'ix_invitation_project_email_status',
        'project_invitations',
        ['project_id', 'invitee_email', 'status']
    )
    op.create_index(
        'ix_invitation_invitee_status',
        'project_invitations',
        ['invitee_id', 'status']
    )

    # 3. Add composite index on project_members for faster lookups
    op.create_index(
        'ix_project_members_project_user',
        'project_members',
        ['project_id', 'user_id']
    )

    # 4. Migrate existing "member" role to "editor"
    op.execute("UPDATE project_members SET role = 'editor' WHERE role = 'member'")


def downgrade():
    # Revert role back to "member"
    op.execute("UPDATE project_members SET role = 'member' WHERE role = 'editor'")

    # Drop indexes
    op.drop_index('ix_project_members_project_user', table_name='project_members')
    op.drop_index('ix_invitation_invitee_status', table_name='project_invitations')
    op.drop_index('ix_invitation_project_email_status', table_name='project_invitations')

    # Drop table
    op.drop_table('project_invitations')
