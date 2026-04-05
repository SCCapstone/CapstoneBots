"""
Integration tests for push/pull flows (Steps 3 & 4).

These test the full push/pull flow against mock backend/S3 responses.
"""
import json
import hashlib
from unittest.mock import MagicMock, patch, PropertyMock
from uuid import uuid4

import pytest

from blender_vcs.tests.conftest import (
    make_mock_object, MockMesh, MockVertex, MockEdge, MockLoop,
    MockPolygon, MockCollection,
)
from blender_vcs.object_serialization import (
    serialize_object_metadata,
    serialize_mesh_data,
    compute_object_hash,
)
from blender_vcs.push_pull import (
    prepare_push_objects,
    build_commit_objects_list,
    prepare_pull_data,
)


def _make_scene_objects():
    """Create a small scene: Cube, Camera, Light."""
    verts = [MockVertex([0, 0, 0], 0), MockVertex([1, 0, 0], 1),
             MockVertex([1, 1, 0], 2), MockVertex([0, 1, 0], 3)]
    mesh = MockMesh(vertices=verts, edges=[], polygons=[
        MockPolygon([0, 1, 2, 3], 0, 4)
    ], loops=[MockLoop(i, i) for i in range(4)])

    cube = make_mock_object(name="Cube", type_="MESH", data=mesh,
                             location=(1, 2, 3))
    camera = make_mock_object(name="Camera", type_="CAMERA",
                               location=(7, -6, 5))
    camera.data = MagicMock()
    camera.data.lens = 50
    camera.data.clip_start = 0.1
    camera.data.clip_end = 1000
    camera.data.sensor_width = 36
    camera.data.type = "PERSP"

    light = make_mock_object(name="Light", type_="LIGHT",
                              location=(4, 1, 6))
    light.data = MagicMock()
    light.data.type = "POINT"
    light.data.energy = 1000
    light.data.color = [1, 1, 1]
    light.data.shadow_soft_size = 0.25

    return [cube, camera, light]


class TestPrepareObjects:

    def test_push_creates_multiple_blender_objects(self):
        """Push scene with 3 objects → 3 object records (not 1 BLEND_FILE)."""
        scene = _make_scene_objects()
        parent_objects = {}  # First commit

        result = prepare_push_objects(scene, parent_objects)

        assert len(result) == 3
        names = {obj["object_name"] for obj in result}
        assert names == {"Cube", "Camera", "Light"}
        # No BLEND_FILE type
        for obj in result:
            assert obj["object_type"] != "BLEND_FILE"

    def test_push_dedup_skips_unchanged_objects(self):
        """Push twice without changes → second push reuses blob_hashes."""
        scene = _make_scene_objects()

        # First push: all new
        first_result = prepare_push_objects(scene, parent_objects={})

        # Build parent_objects from first push
        parent_objects = {
            obj["object_name"]: {
                "blob_hash": obj["blob_hash"],
                "json_data_path": f"projects/test/objects/{obj['object_name']}/abc.json",
                "mesh_data_path": obj.get("mesh_data_path"),
            }
            for obj in first_result
        }

        # Second push: same scene, no changes
        second_result = prepare_push_objects(scene, parent_objects)

        for obj in second_result:
            assert obj["changed"] is False, f"{obj['object_name']} should be unchanged"

    def test_push_uploads_only_changed_objects(self):
        """Modify 1 of 3 objects → only 1 marked as changed."""
        scene = _make_scene_objects()

        # First push
        first_result = prepare_push_objects(scene, parent_objects={})
        parent_objects = {
            obj["object_name"]: {
                "blob_hash": obj["blob_hash"],
                "json_data_path": f"projects/test/objects/{obj['object_name']}/abc.json",
                "mesh_data_path": obj.get("mesh_data_path"),
            }
            for obj in first_result
        }

        # Modify the cube's location
        from blender_vcs.tests.conftest import MockVector
        scene[0].location = MockVector([99, 99, 99])

        second_result = prepare_push_objects(scene, parent_objects)

        changed = [obj for obj in second_result if obj["changed"]]
        unchanged = [obj for obj in second_result if not obj["changed"]]

        assert len(changed) == 1
        assert changed[0]["object_name"] == "Cube"
        assert len(unchanged) == 2

    def test_push_with_staged_subset(self):
        """Stage 1 of 3 → commit has 1 changed + 2 unchanged refs."""
        scene = _make_scene_objects()

        # First push
        first_result = prepare_push_objects(scene, parent_objects={})
        parent_objects = {
            obj["object_name"]: {
                "blob_hash": obj["blob_hash"],
                "json_data_path": f"projects/test/objects/{obj['object_name']}/abc.json",
                "mesh_data_path": obj.get("mesh_data_path"),
            }
            for obj in first_result
        }

        # Modify all objects but only stage Cube
        from blender_vcs.tests.conftest import MockVector
        for obj in scene:
            obj.location = MockVector([99, 99, 99])

        staged_names = {"Cube"}
        result = prepare_push_objects(scene, parent_objects, staged_names=staged_names)

        # Only Cube should be changed; Camera and Light should reuse parent
        changed = [obj for obj in result if obj["changed"]]
        unchanged = [obj for obj in result if not obj["changed"]]

        assert len(changed) == 1
        assert changed[0]["object_name"] == "Cube"
        assert len(unchanged) == 2

    def test_unstaged_new_objects_still_uploaded(self):
        """New objects not in parent must be uploaded even when not staged."""
        scene = _make_scene_objects()  # Cube, Camera, Light

        # Parent only had Cube — Camera and Light are new
        first_cube = prepare_push_objects([scene[0]], parent_objects={})
        parent_objects = {
            "Cube": {
                "blob_hash": first_cube[0]["blob_hash"],
                "json_data_path": "projects/test/objects/Cube/abc.json",
                "mesh_data_path": None,
            }
        }

        # Only stage Cube, but Camera & Light are new (no parent)
        result = prepare_push_objects(scene, parent_objects, staged_names={"Cube"})

        names_changed = {o["object_name"] for o in result if o["changed"]}
        # Camera and Light are new → must be changed (uploaded) even if not staged
        assert "Camera" in names_changed
        assert "Light" in names_changed
        # All 3 objects are in the result
        assert len(result) == 3

    def test_parent_objects_carried_forward_when_deleted_from_scene(self):
        """Objects in parent but missing from scene are preserved unless staged for deletion."""
        scene = _make_scene_objects()  # Cube, Camera, Light

        # First push — all three objects
        first_result = prepare_push_objects(scene, parent_objects={})
        parent_objects = {
            obj["object_name"]: {
                "blob_hash": obj["blob_hash"],
                "json_data_path": f"projects/test/objects/{obj['object_name']}/abc.json",
                "mesh_data_path": None,
                "object_type": obj["object_type"],
            }
            for obj in first_result
        }

        # Scene now only has Cube (Camera and Light deleted from scene)
        scene_without_two = [scene[0]]

        # Push without staging any deletions
        result = prepare_push_objects(
            scene_without_two, parent_objects, staged_names={"Cube"}, staged_deletions=set()
        )

        result_names = {o["object_name"] for o in result}
        # Camera and Light should be carried forward from parent
        assert result_names == {"Cube", "Camera", "Light"}
        assert len(result) == 3

    def test_staged_deletion_removes_object_from_commit(self):
        """Staging a deletion excludes the object from the commit snapshot."""
        scene = _make_scene_objects()

        first_result = prepare_push_objects(scene, parent_objects={})
        parent_objects = {
            obj["object_name"]: {
                "blob_hash": obj["blob_hash"],
                "json_data_path": f"projects/test/objects/{obj['object_name']}/abc.json",
                "mesh_data_path": None,
                "object_type": obj["object_type"],
            }
            for obj in first_result
        }

        # Scene now only has Cube; Light is explicitly staged for deletion
        scene_without_two = [scene[0]]

        result = prepare_push_objects(
            scene_without_two, parent_objects,
            staged_names={"Cube"},
            staged_deletions={"Light"},
        )

        result_names = {o["object_name"] for o in result}
        # Light is deleted, Camera is carried forward
        assert "Light" not in result_names
        assert "Camera" in result_names
        assert "Cube" in result_names
        assert len(result) == 2


class TestBuildCommitObjectsList:

    def test_build_list_includes_all_objects(self):
        """Commit snapshot includes all scene objects."""
        scene = _make_scene_objects()
        push_result = prepare_push_objects(scene, parent_objects={})

        # Simulate upload results
        upload_results = {}
        for obj in push_result:
            upload_results[obj["object_name"]] = {
                "json_data_path": f"projects/test/objects/{obj['object_name']}/hash.json",
                "mesh_data_path": f"projects/test/objects/{obj['object_name']}/mesh-data/hash.bin"
                                  if obj["object_type"] == "MESH" else None,
                "blob_hash": obj["blob_hash"],
            }

        commit_objects = build_commit_objects_list(push_result, upload_results)

        assert len(commit_objects) == 3
        for obj in commit_objects:
            assert "object_name" in obj
            assert "object_type" in obj
            assert "json_data_path" in obj
            assert "blob_hash" in obj


class TestPreparePullData:

    def test_pull_returns_object_metadata(self):
        """Pull returns object data suitable for scene reconstruction."""
        commit_objects = [
            {
                "object_id": str(uuid4()),
                "object_name": "Cube",
                "object_type": "MESH",
                "json_data_path": "projects/test/objects/Cube/abc.json",
                "mesh_data_path": "projects/test/objects/Cube/mesh-data/abc.bin",
                "blob_hash": "abc123",
            },
            {
                "object_id": str(uuid4()),
                "object_name": "Camera",
                "object_type": "CAMERA",
                "json_data_path": "projects/test/objects/Camera/abc.json",
                "mesh_data_path": None,
                "blob_hash": "def456",
            },
        ]

        result = prepare_pull_data(commit_objects)

        assert len(result) == 2
        assert result[0]["object_name"] == "Cube"
        assert result[0]["has_mesh"] is True
        assert result[1]["object_name"] == "Camera"
        assert result[1]["has_mesh"] is False

    def test_pull_backward_compat_blend_file(self):
        """Old BLEND_FILE commit → flagged for legacy fallback."""
        commit_objects = [
            {
                "object_id": str(uuid4()),
                "object_name": "scene.blend",
                "object_type": "BLEND_FILE",
                "json_data_path": "s3://bucket/proj_123/scene.blend",
                "mesh_data_path": None,
                "blob_hash": "xyz789",
            },
        ]

        result = prepare_pull_data(commit_objects)

        assert len(result) == 1
        assert result[0]["is_legacy_blend"] is True


class TestBuildCommitObjectsHashMap:
    """Tests for build_commit_objects_hash_map helper."""

    def test_builds_hash_map_from_commit_objects(self):
        """Commit objects list → {name: blob_hash} mapping."""
        from blender_vcs.push_pull import build_commit_objects_hash_map

        commit_objects = [
            {"object_name": "Cube", "object_type": "MESH", "blob_hash": "aaa"},
            {"object_name": "Camera", "object_type": "CAMERA", "blob_hash": "bbb"},
            {"object_name": "Light", "object_type": "LIGHT", "blob_hash": "ccc"},
        ]

        result = build_commit_objects_hash_map(commit_objects)

        assert result == {"Cube": "aaa", "Camera": "bbb", "Light": "ccc"}

    def test_handles_empty_list(self):
        from blender_vcs.push_pull import build_commit_objects_hash_map

        assert build_commit_objects_hash_map([]) == {}

    def test_skips_invalid_entries(self):
        from blender_vcs.push_pull import build_commit_objects_hash_map

        commit_objects = [
            {"object_name": "Cube", "blob_hash": "aaa"},
            "not a dict",
            {"blob_hash": "bbb"},  # missing object_name
            None,
        ]

        result = build_commit_objects_hash_map(commit_objects)

        assert result == {"Cube": "aaa"}

    def test_default_empty_hash_for_missing_blob_hash(self):
        from blender_vcs.push_pull import build_commit_objects_hash_map

        commit_objects = [
            {"object_name": "Cube"},
        ]

        result = build_commit_objects_hash_map(commit_objects)

        assert result == {"Cube": ""}


class TestReconstructSceneClearExisting:
    """Tests for reconstruct_scene with clear_existing parameter."""

    def test_clear_existing_calls_clear_scene(self):
        """When clear_existing=True, clear_scene() should be called."""
        from unittest.mock import patch
        from blender_vcs.object_serialization import reconstruct_scene

        objects_data = [
            {
                "object_name": "Cube",
                "object_type": "MESH",
                "transform": {"location": [0, 0, 0], "rotation_euler": [0, 0, 0], "scale": [1, 1, 1]},
                "visibility": {},
                "materials": [],
                "modifiers": [],
                "custom_properties": {},
                "collections": [],
            },
        ]

        with patch("blender_vcs.object_serialization.clear_scene") as mock_clear:
            reconstruct_scene(objects_data, {}, clear_existing=True)
            mock_clear.assert_called_once()

    def test_no_clear_by_default(self):
        """When clear_existing is not set (default False), clear_scene() should NOT be called."""
        from unittest.mock import patch
        from blender_vcs.object_serialization import reconstruct_scene

        objects_data = [
            {
                "object_name": "Camera",
                "object_type": "CAMERA",
                "transform": {"location": [0, 0, 0], "rotation_euler": [0, 0, 0], "scale": [1, 1, 1]},
                "visibility": {},
                "materials": [],
                "modifiers": [],
                "custom_properties": {},
                "collections": [],
                "type_data": {"lens": 50, "clip_start": 0.1, "clip_end": 1000, "sensor_width": 36, "camera_type": "PERSP"},
            },
        ]

        with patch("blender_vcs.object_serialization.clear_scene") as mock_clear:
            reconstruct_scene(objects_data, {}, clear_existing=False)
            mock_clear.assert_not_called()


class TestPushDetectsPropertyChanges:
    """Verify that material, modifier, and transform changes produce different hashes."""

    def test_material_change_detected(self):
        """Changing a material's diffuse_color → different blob_hash."""
        scene = _make_scene_objects()
        cube = scene[0]

        # First push
        first_result = prepare_push_objects(scene, parent_objects={})
        parent_objects = {
            obj["object_name"]: {
                "blob_hash": obj["blob_hash"],
                "json_data_path": f"projects/test/objects/{obj['object_name']}/abc.json",
                "mesh_data_path": obj.get("mesh_data_path"),
            }
            for obj in first_result
        }

        # Add a material to the cube
        mat = MagicMock()
        mat.name = "Red"
        mat.diffuse_color = [1.0, 0.0, 0.0, 1.0]
        mat.metallic = 0.5
        mat.roughness = 0.3
        mat.blend_method = "OPAQUE"
        mat.use_nodes = False
        mat.node_tree = None
        slot = MagicMock()
        slot.material = mat
        slot.link = "OBJECT"
        cube.material_slots = [slot]

        second_result = prepare_push_objects(scene, parent_objects)
        cube_result = next(o for o in second_result if o["object_name"] == "Cube")
        assert cube_result["changed"] is True

    def test_modifier_change_detected(self):
        """Adding a modifier → different blob_hash."""
        from blender_vcs.tests.conftest import MockModifier
        scene = _make_scene_objects()
        cube = scene[0]

        first_result = prepare_push_objects(scene, parent_objects={})
        parent_objects = {
            obj["object_name"]: {
                "blob_hash": obj["blob_hash"],
                "json_data_path": f"projects/test/objects/{obj['object_name']}/abc.json",
                "mesh_data_path": obj.get("mesh_data_path"),
            }
            for obj in first_result
        }

        # Add a modifier
        cube.modifiers = [MockModifier("Subsurf", "SUBSURF")]

        second_result = prepare_push_objects(scene, parent_objects)
        cube_result = next(o for o in second_result if o["object_name"] == "Cube")
        assert cube_result["changed"] is True

    def test_transform_change_detected(self):
        """Changing location/rotation/scale → different blob_hash."""
        from blender_vcs.tests.conftest import MockVector
        scene = _make_scene_objects()
        cube = scene[0]

        first_result = prepare_push_objects(scene, parent_objects={})
        parent_objects = {
            obj["object_name"]: {
                "blob_hash": obj["blob_hash"],
                "json_data_path": f"projects/test/objects/{obj['object_name']}/abc.json",
                "mesh_data_path": obj.get("mesh_data_path"),
            }
            for obj in first_result
        }

        # Change scale
        cube.scale = MockVector([2.0, 2.0, 2.0])

        second_result = prepare_push_objects(scene, parent_objects)
        cube_result = next(o for o in second_result if o["object_name"] == "Cube")
        assert cube_result["changed"] is True


class TestReconstructSceneRemovesExisting:
    """Verify that reconstruct_scene replaces existing objects instead of duplicating."""

    def test_dirty_pull_removes_matching_objects_before_creating(self):
        """When clear_existing=False, objects with matching names are removed first."""
        from unittest.mock import patch, call
        from blender_vcs.object_serialization import reconstruct_scene

        objects_data = [
            {
                "object_name": "Cube",
                "object_type": "MESH",
                "transform": {"location": [0, 0, 0], "rotation_euler": [0, 0, 0], "scale": [1, 1, 1]},
                "visibility": {},
                "materials": [],
                "modifiers": [],
                "custom_properties": {},
                "collections": [],
            },
        ]

        # Simulate an existing object named "Cube" in bpy.data.objects
        existing_obj = MagicMock()
        existing_obj.name = "Cube"

        import bpy
        bpy.data.objects.__iter__ = MagicMock(return_value=iter([existing_obj]))

        with patch("blender_vcs.object_serialization.clear_scene") as mock_clear:
            reconstruct_scene(objects_data, {}, clear_existing=False)
            # clear_scene should NOT be called
            mock_clear.assert_not_called()
            # But the existing "Cube" should have been removed
            bpy.data.objects.remove.assert_called_with(existing_obj, do_unlink=True)


class TestPullDirtyStateDetection:
    """Tests that the pull operator properly detects dirty local state."""

    def test_staging_area_is_dirty_when_objects_staged(self):
        """Staging area with objects → dirty state."""
        from blender_vcs.staging import StagingArea

        staging = StagingArea()
        staging.stage("Cube")

        assert bool(staging.staged_objects) is True

    def test_staging_area_is_clean_when_empty(self):
        """Empty staging area → clean state."""
        from blender_vcs.staging import StagingArea

        staging = StagingArea()

        assert bool(staging.staged_objects) is False

    def test_staging_area_clean_after_clear(self):
        """Staging area after clear() → clean state."""
        from blender_vcs.staging import StagingArea

        staging = StagingArea()
        staging.stage("Cube")
        staging.stage("Camera")
        staging.clear()

        assert bool(staging.staged_objects) is False

