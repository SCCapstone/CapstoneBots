"""
Project Utility Functions

Shared helpers for project-level operations used across multiple routers.
"""

import logging
import os
from collections import defaultdict
from uuid import UUID

import boto3
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text as sa_text

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
    try:
        s3_rows = await db.execute(sa_text(
            "SELECT bo.json_data_path, bo.mesh_data_path FROM blender_objects bo "
            "JOIN commits c ON bo.commit_id = c.commit_id "
            "WHERE c.project_id = :pid"
        ), {"pid": pid})
        s3_paths = []
        for row in s3_rows:
            for path in (row[0], row[1]):
                if path and isinstance(path, str) and path.startswith("s3://"):
                    s3_paths.append(path)

        if s3_paths:
            s3_client = boto3.client(
                "s3",
                region_name=os.environ.get("S3_REGION", "us-east-1"),
                aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("S3_ACCESS_KEY"),
                aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY") or os.environ.get("S3_SECRET_KEY"),
            )
            bucket_keys: dict[str, list[str]] = defaultdict(list)
            for s3_uri in s3_paths:
                parts = s3_uri[5:]  # strip "s3://"
                slash = parts.find("/")
                if slash > 0:
                    bucket_keys[parts[:slash]].append(parts[slash + 1:])
            for bucket, keys in bucket_keys.items():
                for i in range(0, len(keys), 1000):
                    batch = keys[i:i + 1000]
                    s3_client.delete_objects(
                        Bucket=bucket,
                        Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True},
                    )
            log.info(f"Deleted {len(s3_paths)} S3 objects for project {project_id}")
    except Exception as e:
        log.warning(f"S3 cleanup failed for project {project_id}: {e}")

    # 2. Break circular FKs before deleting rows
    await db.execute(sa_text(
        "UPDATE branches SET head_commit_id = NULL WHERE project_id = :pid"
    ), {"pid": pid})
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
        "commits", "branches", "project_metadata",
        "project_invitations", "project_members",
    ]:
        await db.execute(sa_text(f"DELETE FROM {tbl} WHERE project_id = :pid"), {"pid": pid})

    # 4. Delete the project itself
    await db.execute(sa_text("DELETE FROM projects WHERE project_id = :pid"), {"pid": pid})
