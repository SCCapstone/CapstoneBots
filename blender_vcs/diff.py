"""
Object-level diff/status computation for BVCS.

Compares current scene objects against the parent commit to determine
which objects are modified, added, or deleted.
"""
from enum import Enum


class ObjectStatus(str, Enum):
    MODIFIED = "M"
    ADDED = "+"
    DELETED = "-"


def compute_scene_diff(
    scene_objects: dict[str, str],
    parent_objects: dict[str, str],
) -> dict[str, ObjectStatus]:
    """
    Compare scene objects against parent commit objects.

    Args:
        scene_objects: {object_name: blob_hash} for current scene
        parent_objects: {object_name: blob_hash} for parent commit

    Returns:
        dict mapping object_name -> ObjectStatus for changed objects only.
        Unchanged objects are omitted.
    """
    diff = {}

    all_names = set(scene_objects.keys()) | set(parent_objects.keys())

    for name in all_names:
        in_scene = name in scene_objects
        in_parent = name in parent_objects

        if in_scene and in_parent:
            if scene_objects[name] != parent_objects[name]:
                diff[name] = ObjectStatus.MODIFIED
            # else: unchanged — omit
        elif in_scene and not in_parent:
            diff[name] = ObjectStatus.ADDED
        elif not in_scene and in_parent:
            diff[name] = ObjectStatus.DELETED

    return diff
