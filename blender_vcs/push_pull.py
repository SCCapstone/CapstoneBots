"""
Push and pull logic for object-level VCS.

Provides functions to:
- Prepare objects for push (serialize, hash, detect changes)
- Build the commit objects list (changed + unchanged references)
- Prepare pull data for scene reconstruction
"""
import logging

from .object_serialization import (
    serialize_object_metadata,
    serialize_mesh_data,
    compute_object_hash,
)

logger = logging.getLogger("BVCS")

# Object types that have binary mesh data
MESH_TYPES = {"MESH", "CURVE", "SURFACE", "FONT"}


def prepare_push_objects(
    scene_objects: list,
    parent_objects: dict,
    staged_names: set = None,
) -> list[dict]:
    """
    Prepare scene objects for push by serializing and detecting changes.

    Args:
        scene_objects: List of bpy.types.Object (or mocks)
        parent_objects: {object_name: {blob_hash, json_data_path, mesh_data_path}}
                       from parent commit. Empty dict for first commit.
        staged_names: Set of object names explicitly staged. If None, all
                     objects are considered staged.

    Returns:
        List of dicts, one per object:
            {
                "object_name": str,
                "object_type": str,
                "blob_hash": str,
                "metadata": dict,       # JSON metadata
                "mesh_binary": bytes,    # binary mesh data (or None)
                "changed": bool,         # True if needs upload
                "parent_data": dict,     # parent's paths if unchanged
            }
    """
    result = []

    for obj in scene_objects:
        name = obj.name
        obj_type = obj.type

        # Serialize metadata
        metadata = serialize_object_metadata(obj)

        # Serialize mesh data if applicable
        mesh_binary = None
        if obj_type in MESH_TYPES and obj.data is not None:
            mesh_binary = serialize_mesh_data(obj)

        blob_hash = compute_object_hash(metadata, mesh_binary)

        # Check if changed vs parent
        parent_data = parent_objects.get(name, {})
        parent_hash = parent_data.get("blob_hash")

        # Determine if this object is "changed" for this commit:
        # - If staged_names is provided and this object is NOT staged,
        #   treat it as unchanged (reuse parent even if locally modified)
        # - If no parent hash exists, it's always new/changed
        # - If hashes differ, it's changed
        if staged_names is not None and name not in staged_names:
            changed = False
        elif parent_hash is None:
            changed = True
        else:
            changed = blob_hash != parent_hash

        result.append({
            "object_name": name,
            "object_type": obj_type,
            "blob_hash": blob_hash,
            "metadata": metadata,
            "mesh_binary": mesh_binary,
            "changed": changed,
            "parent_data": parent_data if not changed else {},
        })

    return result


def build_commit_objects_list(
    push_result: list[dict],
    upload_results: dict,
) -> list[dict]:
    """
    Build the final objects list for the commit API call.

    Combines newly uploaded objects with unchanged references from parent.

    Args:
        push_result: Output from prepare_push_objects
        upload_results: {object_name: {json_data_path, mesh_data_path, blob_hash}}
                       for objects that were uploaded

    Returns:
        List of BlenderObjectCreate-compatible dicts
    """
    objects = []

    for obj in push_result:
        name = obj["object_name"]

        if obj["changed"] and name in upload_results:
            # Use newly uploaded paths
            uploaded = upload_results[name]
            objects.append({
                "object_name": name,
                "object_type": obj["object_type"],
                "json_data_path": uploaded["json_data_path"],
                "mesh_data_path": uploaded.get("mesh_data_path"),
                "parent_object_id": None,
                "blob_hash": obj["blob_hash"],
            })
        else:
            # Reuse parent paths
            parent = obj.get("parent_data", {})
            objects.append({
                "object_name": name,
                "object_type": obj["object_type"],
                "json_data_path": parent.get("json_data_path", ""),
                "mesh_data_path": parent.get("mesh_data_path"),
                "parent_object_id": None,
                "blob_hash": obj["blob_hash"] if obj["changed"] else parent.get("blob_hash", obj["blob_hash"]),
            })

    return objects


def build_commit_objects_hash_map(commit_objects: list[dict]) -> dict[str, str]:
    """
    Build a mapping of object_name → blob_hash from commit objects.

    This is useful for three-way merge comparisons during pull, where
    we need hash maps from multiple commits.

    Args:
        commit_objects: List of object dicts from GET /commits/{id}/objects

    Returns:
        Dict mapping object_name → blob_hash
    """
    result = {}
    for obj in commit_objects:
        if not isinstance(obj, dict):
            continue
        name = obj.get("object_name")
        blob_hash = obj.get("blob_hash", "")
        if name:
            result[name] = blob_hash
    return result


def prepare_pull_data(commit_objects: list[dict]) -> list[dict]:
    """
    Process commit objects for pull/download.

    Determines which objects need mesh downloads and flags legacy
    BLEND_FILE objects for backward compatibility.

    Args:
        commit_objects: List of object dicts from GET /commits/{id}/objects

    Returns:
        List of dicts with download instructions:
            {
                "object_name": str,
                "object_type": str,
                "json_data_path": str,
                "mesh_data_path": str or None,
                "has_mesh": bool,
                "is_legacy_blend": bool,
                "blob_hash": str,
            }
    """
    result = []

    for obj in commit_objects:
        obj_type = obj.get("object_type", "")
        is_legacy = obj_type == "BLEND_FILE"
        mesh_path = obj.get("mesh_data_path")

        result.append({
            "object_name": obj.get("object_name", ""),
            "object_type": obj_type,
            "json_data_path": obj.get("json_data_path", ""),
            "mesh_data_path": mesh_path,
            "has_mesh": bool(mesh_path),
            "is_legacy_blend": is_legacy,
            "blob_hash": obj.get("blob_hash", ""),
        })

    return result
