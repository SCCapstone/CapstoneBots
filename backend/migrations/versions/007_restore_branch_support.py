"""Restore branch support.

Revision ID: 007
Revises: 006
Create Date: 2026-04-05

Re-adds branching infrastructure:
- Re-creates branches table
- Re-adds default_branch to projects
- Re-adds branch_id to commits and object_locks
- Data migration: creates "main" branch per project, links existing commits
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Revision identifiers
revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    def has_table(name: str) -> bool:
        return name in tables

    def has_column(table: str, column: str) -> bool:
        if not has_table(table):
            return False
        return any(c["name"] == column for c in inspector.get_columns(table))

    # 1) Create branches table
    if not has_table("branches"):
        op.create_table(
            "branches",
            sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("branch_name", sa.String(), nullable=False),
            sa.Column("head_commit_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("parent_branch_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"]),
            sa.ForeignKeyConstraint(["head_commit_id"], ["commits.commit_id"]),
            sa.ForeignKeyConstraint(["parent_branch_id"], ["branches.branch_id"]),
            sa.ForeignKeyConstraint(
                ["created_by"], ["users.user_id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("branch_id"),
            sa.UniqueConstraint(
                "project_id", "branch_name", name="unique_project_branch"
            ),
        )

    # 2) Add default_branch to projects
    if not has_column("projects", "default_branch"):
        op.add_column(
            "projects",
            sa.Column(
                "default_branch",
                sa.String(),
                nullable=False,
                server_default="main",
            ),
        )

    # 3) Add branch_id to commits (nullable first for data migration)
    if not has_column("commits", "branch_id"):
        op.add_column(
            "commits",
            sa.Column(
                "branch_id", postgresql.UUID(as_uuid=True), nullable=True
            ),
        )
        op.create_foreign_key(
            "fk_commits_branch_id",
            "commits",
            "branches",
            ["branch_id"],
            ["branch_id"],
        )

    # 4) Add branch_id to object_locks (nullable first for data migration)
    if not has_column("object_locks", "branch_id"):
        op.add_column(
            "object_locks",
            sa.Column(
                "branch_id", postgresql.UUID(as_uuid=True), nullable=True
            ),
        )
        op.create_foreign_key(
            "fk_object_locks_branch_id",
            "object_locks",
            "branches",
            ["branch_id"],
            ["branch_id"],
        )

    # 5) Data migration: create "main" branch per project, link commits
    op.execute(
        """
        INSERT INTO branches (branch_id, project_id, branch_name, head_commit_id, created_at)
        SELECT
            gen_random_uuid(),
            p.project_id,
            'main',
            (
                SELECT c.commit_id
                FROM commits c
                WHERE c.project_id = p.project_id
                ORDER BY c.committed_at DESC
                LIMIT 1
            ),
            NOW()
        FROM projects p
        WHERE NOT EXISTS (
            SELECT 1 FROM branches b
            WHERE b.project_id = p.project_id AND b.branch_name = 'main'
        )
        """
    )

    # Link all existing commits to their project's main branch
    op.execute(
        """
        UPDATE commits c
        SET branch_id = b.branch_id
        FROM branches b
        WHERE b.project_id = c.project_id
          AND b.branch_name = 'main'
          AND c.branch_id IS NULL
        """
    )

    # Link all existing locks to their project's main branch
    op.execute(
        """
        UPDATE object_locks ol
        SET branch_id = b.branch_id
        FROM branches b
        WHERE b.project_id = ol.project_id
          AND b.branch_name = 'main'
          AND ol.branch_id IS NULL
        """
    )

    # 6) Make branch_id NOT NULL now that data is migrated
    op.alter_column("commits", "branch_id", nullable=False)
    op.alter_column("object_locks", "branch_id", nullable=False)

    # 7) Update unique constraint on object_locks to include branch_id
    # First check if old constraint exists and drop it
    constraints = {
        uq["name"]
        for uq in inspector.get_unique_constraints("object_locks")
        if uq.get("name")
    }
    if "unique_object_lock" in constraints:
        op.drop_constraint("unique_object_lock", "object_locks", type_="unique")
    op.create_unique_constraint(
        "unique_object_lock",
        "object_locks",
        ["project_id", "object_name", "branch_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Remove branch_id from object_locks
    constraints = {
        uq["name"]
        for uq in inspector.get_unique_constraints("object_locks")
        if uq.get("name")
    }
    if "unique_object_lock" in constraints:
        op.drop_constraint("unique_object_lock", "object_locks", type_="unique")
    op.create_unique_constraint(
        "unique_object_lock", "object_locks", ["project_id", "object_name"]
    )

    for fk in inspector.get_foreign_keys("object_locks"):
        if fk.get("name") == "fk_object_locks_branch_id":
            op.drop_constraint("fk_object_locks_branch_id", "object_locks", type_="foreignkey")
    op.drop_column("object_locks", "branch_id")

    # Remove branch_id from commits
    for fk in inspector.get_foreign_keys("commits"):
        if fk.get("name") == "fk_commits_branch_id":
            op.drop_constraint("fk_commits_branch_id", "commits", type_="foreignkey")
    op.drop_column("commits", "branch_id")

    # Remove default_branch from projects
    op.drop_column("projects", "default_branch")

    # Drop branches table
    op.drop_table("branches")
