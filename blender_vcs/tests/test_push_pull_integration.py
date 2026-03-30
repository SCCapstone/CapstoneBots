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
