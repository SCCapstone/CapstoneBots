"""
Tests for object diff/status detection (Step 6).
"""
import pytest

from blender_vcs.diff import compute_scene_diff, ObjectStatus


class TestSceneDiff:

    def test_diff_detects_modified_object(self):
        """Object exists in both scene and parent commit but hash changed."""
        scene_objects = {"Cube": "hash_new_abc"}
        parent_objects = {"Cube": "hash_old_xyz"}

        diff = compute_scene_diff(scene_objects, parent_objects)

        assert diff["Cube"] == ObjectStatus.MODIFIED

    def test_diff_detects_new_object(self):
        """Object in scene but not in parent commit."""
        scene_objects = {"Cube": "hash_abc", "NewLight": "hash_def"}
        parent_objects = {"Cube": "hash_abc"}

        diff = compute_scene_diff(scene_objects, parent_objects)

        assert diff["NewLight"] == ObjectStatus.ADDED

    def test_diff_detects_deleted_object(self):
        """Object in parent commit but not in scene."""
        scene_objects = {"Cube": "hash_abc"}
        parent_objects = {"Cube": "hash_abc", "OldCamera": "hash_xyz"}

        diff = compute_scene_diff(scene_objects, parent_objects)

        assert diff["OldCamera"] == ObjectStatus.DELETED

    def test_diff_unchanged_objects(self):
        """Same hash = unchanged, should not appear in diff."""
        scene_objects = {"Cube": "hash_abc", "Camera": "hash_def"}
        parent_objects = {"Cube": "hash_abc", "Camera": "hash_def"}

        diff = compute_scene_diff(scene_objects, parent_objects)

        # Unchanged objects should not be in the diff
        assert "Cube" not in diff
        assert "Camera" not in diff

    def test_diff_empty_parent(self):
        """First commit — all objects are new."""
        scene_objects = {"Cube": "a", "Camera": "b", "Light": "c"}
        parent_objects = {}

        diff = compute_scene_diff(scene_objects, parent_objects)

        assert diff["Cube"] == ObjectStatus.ADDED
        assert diff["Camera"] == ObjectStatus.ADDED
        assert diff["Light"] == ObjectStatus.ADDED

    def test_diff_empty_scene(self):
        """All objects deleted."""
        scene_objects = {}
        parent_objects = {"Cube": "a", "Camera": "b"}

        diff = compute_scene_diff(scene_objects, parent_objects)

        assert diff["Cube"] == ObjectStatus.DELETED
        assert diff["Camera"] == ObjectStatus.DELETED

    def test_diff_mixed_changes(self):
        """Combination of modified, added, deleted, and unchanged."""
        scene_objects = {
            "Cube": "hash_modified",
            "Camera": "hash_same",
            "NewEmpty": "hash_new",
        }
        parent_objects = {
            "Cube": "hash_original",
            "Camera": "hash_same",
            "OldLight": "hash_old",
        }

        diff = compute_scene_diff(scene_objects, parent_objects)

        assert diff["Cube"] == ObjectStatus.MODIFIED
        assert "Camera" not in diff
        assert diff["NewEmpty"] == ObjectStatus.ADDED
        assert diff["OldLight"] == ObjectStatus.DELETED
