"""
Three-way merge conflict detection for BVCS.

Implements object-level merge logic similar to Git's three-way merge,
comparing a base (common ancestor), local, and remote state.
"""
from enum import Enum
from dataclasses import dataclass, field


class ConflictType(str, Enum):
    BOTH_MODIFIED = "BOTH_MODIFIED"
    ADDED_BOTH = "ADDED_BOTH"
    DELETED_LOCALLY = "DELETED_LOCALLY"
    DELETED_REMOTELY = "DELETED_REMOTELY"


@dataclass
class MergePlan:
    """Result of a three-way merge analysis."""
    auto_merge_local: list[str] = field(default_factory=list)
    auto_merge_remote: list[str] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)


def compute_object_diff(
    base_objects: dict[str, str],
    local_objects: dict[str, str],
    remote_objects: dict[str, str],
) -> MergePlan:
    """
    Perform a three-way diff on object blob_hashes.

    Args:
        base_objects: {object_name: blob_hash} from common ancestor commit
        local_objects: {object_name: blob_hash} from local state
        remote_objects: {object_name: blob_hash} from remote HEAD

    Returns:
        MergePlan with auto_merge_local, auto_merge_remote, conflicts, unchanged
    """
    plan = MergePlan()

    all_names = set(base_objects) | set(local_objects) | set(remote_objects)

    for name in sorted(all_names):
        in_base = name in base_objects
        in_local = name in local_objects
        in_remote = name in remote_objects

        base_hash = base_objects.get(name)
        local_hash = local_objects.get(name)
        remote_hash = remote_objects.get(name)

        if in_base:
            # Object existed in base
            if in_local and in_remote:
                local_changed = local_hash != base_hash
                remote_changed = remote_hash != base_hash

                if not local_changed and not remote_changed:
                    plan.unchanged.append(name)
                elif local_changed and not remote_changed:
                    plan.auto_merge_local.append(name)
                elif not local_changed and remote_changed:
                    plan.auto_merge_remote.append(name)
                else:
                    # Both changed
                    if local_hash == remote_hash:
                        # Convergent edit — same result, no conflict
                        plan.auto_merge_local.append(name)
                    else:
                        plan.conflicts.append({
                            "object_name": name,
                            "conflict_type": ConflictType.BOTH_MODIFIED,
                            "base_hash": base_hash,
                            "local_hash": local_hash,
                            "remote_hash": remote_hash,
                        })

            elif in_local and not in_remote:
                # Deleted on remote
                local_changed = local_hash != base_hash
                if local_changed:
                    plan.conflicts.append({
                        "object_name": name,
                        "conflict_type": ConflictType.DELETED_REMOTELY,
                        "base_hash": base_hash,
                        "local_hash": local_hash,
                        "remote_hash": None,
                    })
                else:
                    # Unchanged locally, deleted remotely → accept deletion
                    plan.auto_merge_remote.append(name)

            elif not in_local and in_remote:
                # Deleted locally
                remote_changed = remote_hash != base_hash
                if remote_changed:
                    plan.conflicts.append({
                        "object_name": name,
                        "conflict_type": ConflictType.DELETED_LOCALLY,
                        "base_hash": base_hash,
                        "local_hash": None,
                        "remote_hash": remote_hash,
                    })
                else:
                    # Unchanged remotely, deleted locally → accept deletion
                    plan.auto_merge_local.append(name)

            else:
                # Deleted on both sides — no action needed
                pass

        else:
            # Object NOT in base — new on one or both sides
            if in_local and in_remote:
                if local_hash == remote_hash:
                    # Same content added on both sides — no conflict
                    plan.auto_merge_local.append(name)
                else:
                    plan.conflicts.append({
                        "object_name": name,
                        "conflict_type": ConflictType.ADDED_BOTH,
                        "base_hash": None,
                        "local_hash": local_hash,
                        "remote_hash": remote_hash,
                    })
            elif in_local:
                plan.auto_merge_local.append(name)
            elif in_remote:
                plan.auto_merge_remote.append(name)

    return plan
