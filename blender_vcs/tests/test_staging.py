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
