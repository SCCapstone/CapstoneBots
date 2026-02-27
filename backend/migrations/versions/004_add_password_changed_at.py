"""Add password_changed_at column to users table

Revision ID: 004
Create Date: 2026-02-26

Adds a nullable DateTime column for tracking when a user last changed
their password — used to invalidate password-reset tokens after use.
"""

from alembic import op
import sqlalchemy as sa

# Revision identifiers
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('password_changed_at', sa.DateTime, nullable=True))


def downgrade():
    op.drop_column('users', 'password_changed_at')

