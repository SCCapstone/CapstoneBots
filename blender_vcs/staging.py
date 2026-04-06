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

    Objects can be staged for addition/modification (present in the scene)
    or for deletion (removed from the scene but present in the parent commit).

    Usage:
        staging = StagingArea()
        staging.stage("Cube")
        staging.stage_deletion("OldLight")
        staging.validate_for_commit()  # raises if nothing staged
        names = staging.get_staged_names()
        deletions = staging.get_staged_deletions()
    """

    def __init__(self):
        self.staged_objects: list[str] = []
        self.staged_deletions: list[str] = []

    def stage(self, object_name: str):
        """Add an object to the staging area (idempotent)."""
        if object_name not in self.staged_objects:
            self.staged_objects.append(object_name)
            logger.info(f"Staged object: {object_name}")
        # If it was staged for deletion, remove that
        if object_name in self.staged_deletions:
            self.staged_deletions.remove(object_name)

    def stage_deletion(self, object_name: str):
        """Stage an object for deletion (idempotent)."""
        if object_name not in self.staged_deletions:
            self.staged_deletions.append(object_name)
            logger.info(f"Staged deletion: {object_name}")
        # If it was staged for add/modify, remove that
        if object_name in self.staged_objects:
            self.staged_objects.remove(object_name)

    def stage_all(self, scene_object_names: list[str]):
        """Stage all objects from the scene."""
        for name in scene_object_names:
            self.stage(name)

    def unstage(self, object_name: str):
        """Remove an object from the staging area (both add and delete)."""
        if object_name in self.staged_objects:
            self.staged_objects.remove(object_name)
            logger.info(f"Unstaged object: {object_name}")
        if object_name in self.staged_deletions:
            self.staged_deletions.remove(object_name)
            logger.info(f"Unstaged deletion: {object_name}")

    def clear(self):
        """Clear the staging area."""
        self.staged_objects.clear()
        self.staged_deletions.clear()

    def get_staged_names(self) -> list[str]:
        """Return a copy of the staged object names (additions/modifications)."""
        return list(self.staged_objects)

    def get_staged_deletions(self) -> list[str]:
        """Return a copy of the staged deletion names."""
        return list(self.staged_deletions)

    def has_staged_changes(self) -> bool:
        """Return True if any objects or deletions are staged."""
        return bool(self.staged_objects) or bool(self.staged_deletions)

    def validate_for_commit(self):
        """Raise if nothing is staged."""
        if not self.staged_objects and not self.staged_deletions:
            raise ValueError("No objects staged for commit")

    def is_staged(self, object_name: str) -> bool:
        """Check if an object is staged (add/modify)."""
        return object_name in self.staged_objects

    def is_staged_for_deletion(self, object_name: str) -> bool:
        """Check if an object is staged for deletion."""
        return object_name in self.staged_deletions
