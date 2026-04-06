"""
Tests for object-level three-way merge conflict detection (Step 7).
"""
import pytest

from blender_vcs.merge import compute_object_diff, ConflictType, MergePlan


class TestComputeObjectDiff:

    def test_no_conflict_local_only_change(self):
        """Modified locally, unchanged on remote → auto-merge local."""
        base = {"Cube": "hash_base"}
        local = {"Cube": "hash_local"}
        remote = {"Cube": "hash_base"}

        plan = compute_object_diff(base, local, remote)

        assert "Cube" in plan.auto_merge_local
        assert "Cube" not in plan.auto_merge_remote
        assert len(plan.conflicts) == 0

    def test_no_conflict_remote_only_change(self):
        """Unchanged locally, modified on remote → auto-merge remote."""
        base = {"Cube": "hash_base"}
        local = {"Cube": "hash_base"}
        remote = {"Cube": "hash_remote"}

        plan = compute_object_diff(base, local, remote)

        assert "Cube" in plan.auto_merge_remote
        assert "Cube" not in plan.auto_merge_local
        assert len(plan.conflicts) == 0

    def test_conflict_both_modified(self):
        """Different changes on both sides → BOTH_MODIFIED conflict."""
        base = {"Cube": "hash_base"}
        local = {"Cube": "hash_local"}
        remote = {"Cube": "hash_remote"}

        plan = compute_object_diff(base, local, remote)

        assert len(plan.conflicts) == 1
        assert plan.conflicts[0]["object_name"] == "Cube"
        assert plan.conflicts[0]["conflict_type"] == ConflictType.BOTH_MODIFIED

    def test_conflict_both_modified_same_result(self):
        """Both modified to same hash → no conflict (convergent edit)."""
        base = {"Cube": "hash_base"}
        local = {"Cube": "hash_same"}
        remote = {"Cube": "hash_same"}

        plan = compute_object_diff(base, local, remote)

        # Same result on both sides — no conflict
        assert len(plan.conflicts) == 0

    def test_conflict_deleted_locally_modified_remotely(self):
        """Deleted locally, modified on remote → conflict."""
        base = {"Cube": "hash_base"}
        local = {}  # deleted
        remote = {"Cube": "hash_remote"}

        plan = compute_object_diff(base, local, remote)

        assert len(plan.conflicts) == 1
        assert plan.conflicts[0]["conflict_type"] == ConflictType.DELETED_LOCALLY

    def test_conflict_deleted_remotely_modified_locally(self):
        """Modified locally, deleted on remote → conflict."""
        base = {"Cube": "hash_base"}
        local = {"Cube": "hash_local"}
        remote = {}  # deleted

        plan = compute_object_diff(base, local, remote)

        assert len(plan.conflicts) == 1
        assert plan.conflicts[0]["conflict_type"] == ConflictType.DELETED_REMOTELY

    def test_conflict_added_both_same_name(self):
        """New object with same name on both sides with different hashes → conflict."""
        base = {}
        local = {"NewObj": "hash_local"}
        remote = {"NewObj": "hash_remote"}

        plan = compute_object_diff(base, local, remote)

        assert len(plan.conflicts) == 1
        assert plan.conflicts[0]["conflict_type"] == ConflictType.ADDED_BOTH

    def test_added_both_same_hash(self):
        """New object with same name and same hash on both sides → no conflict."""
        base = {}
        local = {"NewObj": "hash_same"}
        remote = {"NewObj": "hash_same"}

        plan = compute_object_diff(base, local, remote)

        assert len(plan.conflicts) == 0

    def test_added_only_locally(self):
        """New object only locally → auto-merge local."""
        base = {}
        local = {"NewObj": "hash_new"}
        remote = {}

        plan = compute_object_diff(base, local, remote)

        assert "NewObj" in plan.auto_merge_local
        assert len(plan.conflicts) == 0

    def test_added_only_remotely(self):
        """New object only on remote → auto-merge remote."""
        base = {}
        local = {}
        remote = {"NewObj": "hash_new"}

        plan = compute_object_diff(base, local, remote)

        assert "NewObj" in plan.auto_merge_remote
        assert len(plan.conflicts) == 0

    def test_deleted_both_sides(self):
        """Deleted on both sides → clean (no action needed)."""
        base = {"Cube": "hash_base"}
        local = {}
        remote = {}

        plan = compute_object_diff(base, local, remote)

        assert len(plan.conflicts) == 0
        assert "Cube" not in plan.auto_merge_local
        assert "Cube" not in plan.auto_merge_remote

    def test_unchanged_on_all_sides(self):
        """No changes anywhere → clean."""
        base = {"Cube": "hash_base", "Camera": "hash_cam"}
        local = {"Cube": "hash_base", "Camera": "hash_cam"}
        remote = {"Cube": "hash_base", "Camera": "hash_cam"}

        plan = compute_object_diff(base, local, remote)

        assert len(plan.conflicts) == 0
        assert len(plan.auto_merge_local) == 0
        assert len(plan.auto_merge_remote) == 0
        assert set(plan.unchanged) == {"Cube", "Camera"}

    def test_compute_object_diff_returns_correct_merge_plan(self):
        """Full three-way diff with multiple objects → correct classification."""
        base = {
            "Cube": "hash_base_cube",
            "Camera": "hash_base_cam",
            "Light": "hash_base_light",
            "OldObj": "hash_old",
        }
        local = {
            "Cube": "hash_local_cube",       # modified locally
            "Camera": "hash_base_cam",        # unchanged
            "Light": "hash_local_light",      # modified locally
            # OldObj deleted locally
            "NewLocal": "hash_new_local",     # added locally
        }
        remote = {
            "Cube": "hash_base_cube",         # unchanged remotely
            "Camera": "hash_remote_cam",      # modified remotely
            "Light": "hash_remote_light",     # modified remotely (conflict!)
            "OldObj": "hash_old",             # unchanged remotely
            "NewRemote": "hash_new_remote",   # added remotely
        }

        plan = compute_object_diff(base, local, remote)

        # Cube: local only change → auto_merge_local
        assert "Cube" in plan.auto_merge_local
        # Camera: remote only change → auto_merge_remote
        assert "Camera" in plan.auto_merge_remote
        # Light: both modified → conflict
        assert any(c["object_name"] == "Light" for c in plan.conflicts)
        # OldObj: deleted locally, unchanged remotely → auto_merge_local (deletion)
        assert "OldObj" in plan.auto_merge_local
        # NewLocal: added locally → auto_merge_local
        assert "NewLocal" in plan.auto_merge_local
        # NewRemote: added remotely → auto_merge_remote
        assert "NewRemote" in plan.auto_merge_remote

    def test_merge_plan_has_all_fields(self):
        plan = compute_object_diff({}, {}, {})
        assert hasattr(plan, "auto_merge_local")
        assert hasattr(plan, "auto_merge_remote")
        assert hasattr(plan, "conflicts")
        assert hasattr(plan, "unchanged")
