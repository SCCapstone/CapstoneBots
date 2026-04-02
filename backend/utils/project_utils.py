"""
Project Utility Functions

Shared helpers for project-level operations used across multiple routers.
"""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text as sa_text

from utils.s3_cleanup import cleanup_project_s3

log = logging.getLogger(__name__)


async def delete_project_data(db: AsyncSession, project_id: UUID) -> None:
    """
    Delete a project and all its associated data using raw SQL.

    Handles S3 asset cleanup, circular FK resolution, and cascading table
    deletes.  The caller is responsible for committing (or rolling back) the
    transaction afterwards.

    Args:
        db: Active async database session.
        project_id: UUID of the project to delete.
    """
    pid = str(project_id)

    # 1. Delete S3 objects linked to this project's blender_objects
    await cleanup_project_s3(db, project_id)

    # 2. Break self-referential FKs before deleting rows
    await db.execute(sa_text(
        "UPDATE commits SET parent_commit_id = NULL WHERE project_id = :pid"
    ), {"pid": pid})

    # blender_objects links via commit_id (not project_id) and has self-ref parent_object_id
    await db.execute(sa_text(
        "UPDATE blender_objects SET parent_object_id = NULL "
        "WHERE commit_id IN (SELECT commit_id FROM commits WHERE project_id = :pid)"
    ), {"pid": pid})
    await db.execute(sa_text(
        "DELETE FROM blender_objects "
        "WHERE commit_id IN (SELECT commit_id FROM commits WHERE project_id = :pid)"
    ), {"pid": pid})

    # 3. Delete remaining child tables that have project_id
    for tbl in [
        "object_locks", "merge_conflicts",
        "commits", "project_metadata",
        "project_invitations", "project_members",
    ]:
        await db.execute(sa_text(f"DELETE FROM {tbl} WHERE project_id = :pid"), {"pid": pid})

    # 4. Delete the project itself
    await db.execute(sa_text("DELETE FROM projects WHERE project_id = :pid"), {"pid": pid})
