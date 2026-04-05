"""
Tests for the object-level staging system (Step 5).
"""
import pytest
from unittest.mock import MagicMock, patch

from blender_vcs.tests.conftest import make_mock_object, MockMesh, MockCollection


# Import after bpy mock is in place
from blender_vcs.object_serialization import serialize_object_metadata, compute_object_hash
from blender_vcs.staging import StagingArea


class TestStagingArea:

    def setup_method(self):
        self.staging = StagingArea()

    def test_stage_individual_object(self):
        self.staging.stage("Cube")
        assert "Cube" in self.staging.staged_objects

    def test_stage_all_objects(self):
        scene_objects = ["Cube", "Camera", "Light"]
        self.staging.stage_all(scene_objects)
        assert set(self.staging.staged_objects) == {"Cube", "Camera", "Light"}

    def test_unstage_object(self):
        self.staging.stage("Cube")
        self.staging.stage("Camera")
        self.staging.unstage("Cube")
        assert "Cube" not in self.staging.staged_objects
        assert "Camera" in self.staging.staged_objects

    def test_commit_blocked_without_staging(self):
        assert self.staging.staged_objects == []
        with pytest.raises(ValueError, match="No objects staged"):
            self.staging.validate_for_commit()

    def test_staged_objects_persisted_across_operations(self):
        self.staging.stage("Cube")
        self.staging.stage("Camera")

        # Simulate other operations (staging area should retain state)
        _ = self.staging.get_staged_names()

        assert "Cube" in self.staging.staged_objects
        assert "Camera" in self.staging.staged_objects

    def test_stage_duplicate_ignored(self):
        self.staging.stage("Cube")
        self.staging.stage("Cube")
        assert self.staging.staged_objects.count("Cube") == 1

    def test_unstage_nonexistent_is_noop(self):
        self.staging.unstage("DoesNotExist")
        assert self.staging.staged_objects == []

    def test_clear(self):
        self.staging.stage("Cube")
        self.staging.stage("Camera")
        self.staging.clear()
        assert self.staging.staged_objects == []

    def test_get_staged_names(self):
        self.staging.stage("Cube")
        self.staging.stage("Light")
        names = self.staging.get_staged_names()
        assert set(names) == {"Cube", "Light"}

    def test_validate_for_commit_success(self):
        self.staging.stage("Cube")
        # Should not raise
        self.staging.validate_for_commit()

    # ── Deletion staging tests ──

    def test_stage_deletion(self):
        self.staging.stage_deletion("OldLight")
        assert "OldLight" in self.staging.staged_deletions
        assert "OldLight" not in self.staging.staged_objects

    def test_stage_deletion_removes_from_staged_objects(self):
        """Staging a deletion for an object that was staged for add/modify removes it from staged_objects."""
        self.staging.stage("Cube")
        self.staging.stage_deletion("Cube")
        assert "Cube" in self.staging.staged_deletions
        assert "Cube" not in self.staging.staged_objects

    def test_stage_after_deletion_removes_from_deletions(self):
        """Re-staging an object for add/modify removes it from staged deletions."""
        self.staging.stage_deletion("Cube")
        self.staging.stage("Cube")
        assert "Cube" in self.staging.staged_objects
        assert "Cube" not in self.staging.staged_deletions

    def test_unstage_clears_both(self):
        """Unstaging removes from both staged_objects and staged_deletions."""
        self.staging.stage("Cube")
        self.staging.stage_deletion("Light")
        self.staging.unstage("Cube")
        self.staging.unstage("Light")
        assert self.staging.staged_objects == []
        assert self.staging.staged_deletions == []

    def test_clear_clears_deletions(self):
        self.staging.stage("Cube")
        self.staging.stage_deletion("Light")
        self.staging.clear()
        assert self.staging.staged_objects == []
        assert self.staging.staged_deletions == []

    def test_has_staged_changes_with_only_deletions(self):
        """has_staged_changes returns True when only deletions are staged."""
        assert not self.staging.has_staged_changes()
        self.staging.stage_deletion("Light")
        assert self.staging.has_staged_changes()

    def test_validate_for_commit_with_only_deletions(self):
        """Commit is valid with only deletions staged."""
        self.staging.stage_deletion("OldCamera")
        self.staging.validate_for_commit()  # Should not raise

    def test_validate_for_commit_fails_with_nothing(self):
        """Commit is blocked with nothing staged."""
        with pytest.raises(ValueError, match="No objects staged"):
            self.staging.validate_for_commit()
