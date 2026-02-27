"""Add email verification columns to users table

Revision ID: 005
Create Date: 2026-02-27

Adds is_verified (Boolean, default False) and email_verified_at (DateTime)
columns to support email verification on signup.

Existing users are marked as verified so they are not locked out.
"""

from alembic import op
import sqlalchemy as sa

# Revision identifiers
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('is_verified', sa.Boolean, server_default=sa.text('false'), nullable=False))
    op.add_column('users', sa.Column('email_verified_at', sa.DateTime, nullable=True))
    # Auto-verify all existing users so they are not locked out
    op.execute("UPDATE users SET is_verified = true, email_verified_at = now()")


def downgrade():
    op.drop_column('users', 'email_verified_at')
    op.drop_column('users', 'is_verified')

