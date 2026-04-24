"""
S3 Cleanup Utilities

Shared helpers for deleting S3 objects associated with a project's blender_objects.
Used by both the delete_project and delete_account endpoints to avoid code duplication.
"""

import asyncio
import logging
from typing import Any

from sqlalchemy import text as sa_text

logger = logging.getLogger(__name__)


async def collect_project_s3_paths(db: Any, pid: str) -> list[str]:
    """Query the database and return all S3 paths for a project's blender_objects.

    Args:
        db: An async SQLAlchemy session.
        pid: The project UUID as a string.

    Returns:
        List of ``s3://`` URI strings found in ``blender_objects`` for the project.
    """
    s3_rows = await db.execute(
        sa_text(
            "SELECT bo.json_data_path, bo.mesh_data_path FROM blender_objects bo "
            "JOIN commits c ON bo.commit_id = c.commit_id "
            "WHERE c.project_id = :pid"
        ),
        {"pid": pid},
    )
    s3_paths = []
    for row in s3_rows:
        for path in (row[0], row[1]):
            if path and isinstance(path, str) and path.startswith("s3://"):
                s3_paths.append(path)
    return s3_paths


async def cleanup_project_s3(db: Any, project_id: Any) -> None:
    """Delete all stored objects under a project's prefix in MinIO/S3.

    Args:
        db: An async SQLAlchemy session (unused; kept for API compatibility).
        project_id: The project UUID (string or UUID object).
    """
    try:
        from storage.storage_service import get_storage_service
        # delete_project_data is a sync minio call that can issue many sequential
        # remove_object requests. Run it in a thread so we don't block the event
        # loop for the duration of the S3 batch delete on large projects.
        await asyncio.to_thread(get_storage_service().delete_project_data, project_id)
    except Exception as exc:
        logger.error("S3 cleanup failed for project %s — orphaned objects may remain: %s", project_id, exc, exc_info=True)
