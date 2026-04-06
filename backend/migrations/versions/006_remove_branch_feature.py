"""Remove branch feature schema objects.

Revision ID: 006
Create Date: 2026-04-02

This migration removes branch-specific database structures:
- drops branches table
- removes branch columns from commits, object_locks, and projects
- replaces merge_conflicts.target_branch_id with target_commit_id
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# Revision identifiers
revision = "006"
down_revision = "005"
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

    def has_constraint(table: str, name: str) -> bool:
        if not has_table(table):
            return False
        fks = {fk["name"] for fk in inspector.get_foreign_keys(table) if fk.get("name")}
        uqs = {uq["name"] for uq in inspector.get_unique_constraints(table) if uq.get("name")}
        return name in fks or name in uqs

    def drop_fk_constraints_for_column(table: str, column: str) -> None:
        if not has_table(table):
            return
        for fk in inspector.get_foreign_keys(table):
            name = fk.get("name")
            constrained_columns = fk.get("constrained_columns") or []
            if name and column in constrained_columns:
                op.drop_constraint(name, table, type_="foreignkey")

    # 1) Add target_commit_id and backfill from the target branch head.
    if has_table("merge_conflicts") and has_column("merge_conflicts", "target_branch_id"):
        if not has_column("merge_conflicts", "target_commit_id"):
            op.add_column(
                "merge_conflicts",
                sa.Column("target_commit_id", postgresql.UUID(as_uuid=True), nullable=True),
            )
        if has_table("branches") and has_column("branches", "head_commit_id"):
            op.execute(
                """
                UPDATE merge_conflicts AS mc
                SET target_commit_id = b.head_commit_id
                FROM branches AS b
                WHERE mc.target_branch_id = b.branch_id
                """
            )
        # Fallback so the column can be made NOT NULL even if a branch had no head commit.
        op.execute(
            """
            UPDATE merge_conflicts
            SET target_commit_id = source_commit_id
            WHERE target_commit_id IS NULL
            """
        )
        if not has_constraint("merge_conflicts", "merge_conflicts_target_commit_id_fkey"):
            op.create_foreign_key(
                "merge_conflicts_target_commit_id_fkey",
                "merge_conflicts",
                "commits",
                ["target_commit_id"],
                ["commit_id"],
            )
        op.alter_column("merge_conflicts", "target_commit_id", nullable=False)

    # 2) Remove lock uniqueness that depends on branch_id before dropping the column.
    if has_table("object_locks") and has_column("object_locks", "branch_id"):
        if has_constraint("object_locks", "unique_object_lock"):
            op.drop_constraint("unique_object_lock", "object_locks", type_="unique")
        op.create_unique_constraint("unique_object_lock", "object_locks", ["project_id", "object_name"])

    # 3) Drop branch FK columns from dependent tables.
    if has_table("merge_conflicts") and has_column("merge_conflicts", "target_branch_id"):
        drop_fk_constraints_for_column("merge_conflicts", "target_branch_id")
        op.drop_column("merge_conflicts", "target_branch_id")

    if has_table("object_locks") and has_column("object_locks", "branch_id"):
        drop_fk_constraints_for_column("object_locks", "branch_id")
        op.drop_column("object_locks", "branch_id")

    if has_table("commits") and has_column("commits", "branch_id"):
        drop_fk_constraints_for_column("commits", "branch_id")
        op.drop_column("commits", "branch_id")

    # 4) Remove project default branch metadata.
    if has_table("projects") and has_column("projects", "default_branch"):
        op.drop_column("projects", "default_branch")

    # 5) Drop branches table last (after dependents are removed).
    if has_table("branches"):
        if has_constraint("branches", "fk_branches_head_commit_id"):
            op.drop_constraint("fk_branches_head_commit_id", "branches", type_="foreignkey")
        op.drop_table("branches")


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for branch feature removal.")
