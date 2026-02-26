"""
S3 Cleanup Utilities

Shared helper for deleting S3 objects associated with a project's blender_objects.
Used by both the delete_project and delete_account endpoints to avoid code duplication.
"""

import os
import logging
from collections import defaultdict
from typing import Any

import boto3
from sqlalchemy import text as sa_text

logger = logging.getLogger(__name__)


def delete_s3_objects(s3_paths: list[str], project_id: Any) -> None:
    """Delete a list of S3 URIs, grouped by bucket, using batch deletes.

    Args:
        s3_paths: List of ``s3://bucket/key`` URIs to delete.
        project_id: Project identifier used only for log messages.
    """
    if not s3_paths:
        return

    # Credentials are read from the environment.  Both the standard AWS names
    # (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY) and the project-specific
    # aliases (S3_ACCESS_KEY / S3_SECRET_KEY) are supported so that either
    # naming convention works without code changes.
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

    logger.info("Deleted %d S3 objects for project %s", len(s3_paths), project_id)


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
    """Collect and delete all S3 objects for a project, logging warnings on failure.

    Args:
        db: An async SQLAlchemy session.
        project_id: The project UUID (string or UUID object).
    """
    try:
        pid = str(project_id)
        s3_paths = await collect_project_s3_paths(db, pid)
        delete_s3_objects(s3_paths, project_id)
    except Exception as exc:
        logger.warning("S3 cleanup failed for project %s: %s", project_id, exc)
