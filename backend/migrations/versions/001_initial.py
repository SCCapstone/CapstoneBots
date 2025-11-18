"""Initial schema for VCS

Revision ID: 001
Create Date: 2025-11-14

This migration creates the core tables for the Blender Collaborative Version Control System.
Tables include: users, projects, branches, commits, blender_objects, object_locks, merge_conflicts, and project_metadata.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Revision identifiers
revision = '001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Create users table
    op.create_table(
        'users',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('last_login', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('user_id'),
        sa.UniqueConstraint('username', name='uq_users_username'),
        sa.UniqueConstraint('email', name='uq_users_email'),
    )
    op.create_index('ix_users_username', 'users', ['username'])
    op.create_index('ix_users_email', 'users', ['email'])

    # Create projects table
    op.create_table(
        'projects',
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('default_branch', sa.String(), nullable=True, server_default='main'),
        sa.Column('active', sa.Boolean(), nullable=True, server_default='true'),
        sa.ForeignKeyConstraint(['owner_id'], ['users.user_id'], ),
        sa.PrimaryKeyConstraint('project_id'),
    )

    # Create branches table
    op.create_table(
        'branches',
        sa.Column('branch_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('branch_name', sa.String(), nullable=False),
        sa.Column('head_commit_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('parent_branch_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.user_id'], ),
        sa.ForeignKeyConstraint(['project_id'], ['projects.project_id'], ),
        sa.ForeignKeyConstraint(['parent_branch_id'], ['branches.branch_id'], ),
        sa.PrimaryKeyConstraint('branch_id'),
        sa.UniqueConstraint('project_id', 'branch_name', name='unique_project_branch'),
    )

    # Create commits table
    op.create_table(
        'commits',
        sa.Column('commit_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('branch_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('parent_commit_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('author_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('commit_message', sa.Text(), nullable=False),
        sa.Column('commit_hash', sa.String(), nullable=False),
        sa.Column('committed_at', sa.DateTime(), nullable=True),
        sa.Column('merge_commit', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('merge_parent_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['author_id'], ['users.user_id'], ),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.branch_id'], ),
        sa.ForeignKeyConstraint(['merge_parent_id'], ['commits.commit_id'], ),
        sa.ForeignKeyConstraint(['parent_commit_id'], ['commits.commit_id'], ),
        sa.ForeignKeyConstraint(['project_id'], ['projects.project_id'], ),
        sa.PrimaryKeyConstraint('commit_id'),
        sa.UniqueConstraint('commit_hash', name='uq_commits_commit_hash'),
    )
    op.create_index('ix_commits_commit_hash', 'commits', ['commit_hash'])

    # Create blender_objects table
    op.create_table(
        'blender_objects',
        sa.Column('object_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('commit_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('object_name', sa.String(), nullable=False),
        sa.Column('object_type', sa.String(), nullable=False),
        sa.Column('json_data_path', sa.String(), nullable=False),
        sa.Column('mesh_data_path', sa.String(), nullable=True),
        sa.Column('parent_object_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('blob_hash', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['commit_id'], ['commits.commit_id'], ),
        sa.ForeignKeyConstraint(['parent_object_id'], ['blender_objects.object_id'], ),
        sa.PrimaryKeyConstraint('object_id'),
    )
    op.create_index('ix_blender_objects_blob_hash', 'blender_objects', ['blob_hash'])

    # Create object_locks table
    op.create_table(
        'object_locks',
        sa.Column('lock_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('object_name', sa.String(), nullable=False),
        sa.Column('locked_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('branch_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('locked_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.branch_id'], ),
        sa.ForeignKeyConstraint(['locked_by'], ['users.user_id'], ),
        sa.ForeignKeyConstraint(['project_id'], ['projects.project_id'], ),
        sa.PrimaryKeyConstraint('lock_id'),
        sa.UniqueConstraint('project_id', 'object_name', 'branch_id', name='unique_object_lock'),
    )

    # Create merge_conflicts table
    op.create_table(
        'merge_conflicts',
        sa.Column('conflict_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_commit_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('target_branch_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('object_name', sa.String(), nullable=False),
        sa.Column('conflict_type', sa.String(), nullable=False),
        sa.Column('resolved', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.project_id'], ),
        sa.ForeignKeyConstraint(['source_commit_id'], ['commits.commit_id'], ),
        sa.ForeignKeyConstraint(['target_branch_id'], ['branches.branch_id'], ),
        sa.PrimaryKeyConstraint('conflict_id'),
    )

    # Create project_metadata table
    op.create_table(
        'project_metadata',
        sa.Column('metadata_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', sa.String(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.project_id'], ),
        sa.PrimaryKeyConstraint('metadata_id'),
        sa.UniqueConstraint('project_id', 'key', name='unique_project_metadata'),
    )

    # Add foreign key constraint for branches.head_commit_id after commits table is created
    op.create_foreign_key('fk_branches_head_commit_id', 'branches', 'commits', ['head_commit_id'], ['commit_id'])

def downgrade():
    op.drop_constraint('fk_branches_head_commit_id', 'branches')
    op.drop_table('project_metadata')
    op.drop_table('merge_conflicts')
    op.drop_table('object_locks')
    op.drop_table('blender_objects')
    op.drop_table('commits')
    op.drop_table('branches')
    op.drop_table('projects')
    op.drop_table('users')
