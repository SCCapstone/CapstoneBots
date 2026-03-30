"""
Object-level staging area for BVCS.

Manages the list of objects staged for the next commit,
similar to Git's staging area (index).
"""
import logging

logger = logging.getLogger("BVCS")


class StagingArea:
    """
    Tracks which Blender objects are staged for the next commit.

    Usage:
        staging = StagingArea()
        staging.stage("Cube")
        staging.stage("Camera")
        staging.validate_for_commit()  # raises if empty
        names = staging.get_staged_names()
    """

    def __init__(self):
        self.staged_objects: list[str] = []

    def stage(self, object_name: str):
        """Add an object to the staging area (idempotent)."""
        if object_name not in self.staged_objects:
            self.staged_objects.append(object_name)
            logger.info(f"Staged object: {object_name}")

    def stage_all(self, scene_object_names: list[str]):
        """Stage all objects from the scene."""
        for name in scene_object_names:
            self.stage(name)

    def unstage(self, object_name: str):
        """Remove an object from the staging area."""
        if object_name in self.staged_objects:
            self.staged_objects.remove(object_name)
            logger.info(f"Unstaged object: {object_name}")

    def clear(self):
        """Clear the staging area."""
        self.staged_objects.clear()

    def get_staged_names(self) -> list[str]:
        """Return a copy of the staged object names."""
        return list(self.staged_objects)

    def validate_for_commit(self):
        """Raise if no objects are staged."""
        if not self.staged_objects:
            raise ValueError("No objects staged for commit")

    def is_staged(self, object_name: str) -> bool:
        """Check if an object is staged."""
        return object_name in self.staged_objects
