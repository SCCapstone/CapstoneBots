"""
Tests for object serialization and deserialization (Steps 1 & 2).

These tests verify that Blender objects can be correctly serialized to
JSON metadata + binary mesh data, and reconstructed back.
"""
import json
import hashlib

import pytest

from blender_vcs.tests.conftest import (
    make_mock_object, MockMesh, MockVertex, MockEdge, MockLoop, MockPolygon,
    MockUVLoopLayer, MockUVLoopData, MockModifier, MockMaterialSlot,
    MockVertexGroup, MockVertexGroupElement, MockShapeKey, MockShapeKeyPoint,
    MockCollection, MockVector, MockBone, MockArmature,
)

# Import the module under test — relies on bpy mock from conftest
from blender_vcs.object_serialization import (
    serialize_object_metadata,
    serialize_mesh_data,
    compute_object_hash,
    deserialize_mesh_data,
    reconstruct_object_from_json,
)


# ── Serialization Tests ─────────────────────────────────────────────────────

class TestSerializeMetadata:

    def test_serialize_mesh_object_metadata(self, mock_mesh_object):
        result = serialize_object_metadata(mock_mesh_object)

        assert result["object_name"] == "Cube"
        assert result["object_type"] == "MESH"
        assert result["transform"]["location"] == [1.0, 2.0, 3.0]
        assert result["transform"]["rotation_euler"] == [0.0, 0.0, 1.5708]
        assert result["transform"]["scale"] == [1.0, 1.0, 1.0]
        assert result["parent"] is None
        assert isinstance(result["modifiers"], list)
        assert len(result["modifiers"]) == 1
        assert result["modifiers"][0]["name"] == "Subsurf"
        assert result["modifiers"][0]["type"] == "SUBSURF"
        assert isinstance(result["materials"], list)
        assert len(result["materials"]) == 1
        assert result["materials"][0]["name"] == "Material.001"
        assert result["visibility"]["hide_viewport"] is False

    def test_serialize_camera_metadata(self, mock_camera_object):
        result = serialize_object_metadata(mock_camera_object)

        assert result["object_type"] == "CAMERA"
        assert result["type_data"]["lens"] == 50.0
        assert result["type_data"]["clip_start"] == 0.1
        assert result["type_data"]["clip_end"] == 1000.0
        assert result["type_data"]["sensor_width"] == 36.0
        assert result["type_data"]["camera_type"] == "PERSP"

    def test_serialize_light_metadata(self, mock_light_object):
        result = serialize_object_metadata(mock_light_object)

        assert result["object_type"] == "LIGHT"
        assert result["type_data"]["light_type"] == "POINT"
        assert result["type_data"]["energy"] == 1000.0
        assert result["type_data"]["color"] == [1.0, 0.8, 0.6]
        assert result["type_data"]["shadow_soft_size"] == 0.25

    def test_serialize_armature_metadata(self, mock_armature_object):
        result = serialize_object_metadata(mock_armature_object)

        assert result["object_type"] == "ARMATURE"
        bones = result["type_data"]["bones"]
        assert len(bones) == 3
        assert bones[0]["name"] == "Root"
        assert bones[0]["parent"] is None
        assert bones[1]["name"] == "Spine"
        assert bones[1]["parent"] == "Root"
        assert bones[1]["use_connect"] is True

    def test_serialize_empty_metadata(self, mock_empty_object):
        result = serialize_object_metadata(mock_empty_object)

        assert result["object_type"] == "EMPTY"
        # Custom properties should be captured
        assert "custom_properties" in result

    def test_serialize_with_parent(self, mock_mesh_object, mock_empty_object):
        mock_mesh_object.parent = mock_empty_object
        result = serialize_object_metadata(mock_mesh_object)
        assert result["parent"] == "Empty"

    def test_serialize_with_collections(self, mock_mesh_object):
        mock_mesh_object.users_collection = [MockCollection("MyCollection"), MockCollection("Scene")]
        result = serialize_object_metadata(mock_mesh_object)
        assert "MyCollection" in result["collections"]
        assert "Scene" in result["collections"]


class TestSerializeMeshData:

    def test_serialize_mesh_data_binary(self, mock_mesh_object):
        binary = serialize_mesh_data(mock_mesh_object)

        assert isinstance(binary, bytes)
        assert len(binary) > 0

        # Deserialize to verify content
        data = json.loads(binary.decode("utf-8"))
        assert data["vertex_count"] == 4
        assert len(data["vertices"]) == 4
        assert data["polygon_count"] == 1
        assert len(data["polygons"]) == 1

    def test_serialize_mesh_with_uvs(self, mock_mesh_object):
        binary = serialize_mesh_data(mock_mesh_object)
        data = json.loads(binary.decode("utf-8"))

        assert "uv_layers" in data
        assert len(data["uv_layers"]) == 1
        assert data["uv_layers"][0]["name"] == "UVMap"
        assert len(data["uv_layers"][0]["data"]) == 4

    def test_serialize_mesh_with_vertex_groups(self):
        vg1 = MockVertexGroup("Arm", 0)
        vg2 = MockVertexGroup("Leg", 1)

        verts = [
            MockVertex([0, 0, 0], 0, groups=[MockVertexGroupElement(0, 1.0)]),
            MockVertex([1, 0, 0], 1, groups=[MockVertexGroupElement(1, 0.5)]),
        ]
        mesh = MockMesh(vertices=verts, edges=[], polygons=[], loops=[])
        obj = make_mock_object(name="Weighted", type_="MESH", data=mesh)
        obj.vertex_groups = [vg1, vg2]

        binary = serialize_mesh_data(obj)
        data = json.loads(binary.decode("utf-8"))

        assert "vertex_groups" in data
        assert len(data["vertex_groups"]) == 2
        assert data["vertex_groups"][0]["name"] == "Arm"

    def test_serialize_mesh_with_shape_keys(self):
        basis_data = [MockShapeKeyPoint([0, 0, 0]), MockShapeKeyPoint([1, 0, 0])]
        key1_data = [MockShapeKeyPoint([0, 0, 1]), MockShapeKeyPoint([1, 0, 1])]

        shape_keys = type("ShapeKeys", (), {
            "key_blocks": [
                MockShapeKey("Basis", basis_data, "Basis"),
                MockShapeKey("Key1", key1_data, "Basis"),
            ]
        })()

        verts = [MockVertex([0, 0, 0], 0), MockVertex([1, 0, 0], 1)]
        mesh = MockMesh(vertices=verts, shape_keys=shape_keys)
        obj = make_mock_object(name="Morphed", type_="MESH", data=mesh)

        binary = serialize_mesh_data(obj)
        data = json.loads(binary.decode("utf-8"))

        assert "shape_keys" in data
        assert len(data["shape_keys"]) == 2
        assert data["shape_keys"][0]["name"] == "Basis"


class TestComputeObjectHash:

    def test_deterministic(self, mock_mesh_object):
        meta = serialize_object_metadata(mock_mesh_object)
        h1 = compute_object_hash(meta)
        h2 = compute_object_hash(meta)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_changes_on_modification(self, mock_mesh_object):
        meta1 = serialize_object_metadata(mock_mesh_object)
        h1 = compute_object_hash(meta1)

        # Modify location
        mock_mesh_object.location = MockVector([99, 99, 99])
        meta2 = serialize_object_metadata(mock_mesh_object)
        h2 = compute_object_hash(meta2)

        assert h1 != h2


# ── Deserialization Tests ────────────────────────────────────────────────────

class TestDeserializeMeshData:

    def test_deserialize_mesh_from_binary(self, mock_mesh_object):
        binary = serialize_mesh_data(mock_mesh_object)
        mesh_data = deserialize_mesh_data(binary)

        assert mesh_data["vertex_count"] == 4
        assert len(mesh_data["vertices"]) == 4
        assert mesh_data["polygon_count"] == 1

    def test_round_trip_vertices(self, mock_mesh_object):
        binary = serialize_mesh_data(mock_mesh_object)
        mesh_data = deserialize_mesh_data(binary)

        # First vertex should match original
        assert mesh_data["vertices"][0] == [0, 0, 0]
        assert mesh_data["vertices"][1] == [1, 0, 0]


class TestReconstructObject:

    def test_reconstruct_camera_from_json(self, mock_camera_object):
        metadata = serialize_object_metadata(mock_camera_object)
        result = reconstruct_object_from_json(metadata)

        assert result["object_name"] == "Camera"
        assert result["object_type"] == "CAMERA"
        assert result["type_data"]["lens"] == 50.0

    def test_reconstruct_light_from_json(self, mock_light_object):
        metadata = serialize_object_metadata(mock_light_object)
        result = reconstruct_object_from_json(metadata)

        assert result["object_name"] == "Light"
        assert result["object_type"] == "LIGHT"
        assert result["type_data"]["energy"] == 1000.0

    def test_round_trip_serialize_deserialize(self, mock_mesh_object):
        """Serialize then reconstruct: all key fields should match."""
        metadata = serialize_object_metadata(mock_mesh_object)
        result = reconstruct_object_from_json(metadata)

        assert result["object_name"] == metadata["object_name"]
        assert result["object_type"] == metadata["object_type"]
        assert result["transform"] == metadata["transform"]
        assert result["materials"] == metadata["materials"]

    def test_reconstruct_parent_child_hierarchy(self):
        parent = make_mock_object(name="Parent", type_="EMPTY")
        child = make_mock_object(name="Child", type_="MESH",
                                  data=MockMesh())
        child.parent = parent

        parent_meta = serialize_object_metadata(parent)
        child_meta = serialize_object_metadata(child)

        parent_result = reconstruct_object_from_json(parent_meta)
        child_result = reconstruct_object_from_json(child_meta)

        assert parent_result["parent"] is None
        assert child_result["parent"] == "Parent"

    def test_reconstruct_collections(self, mock_mesh_object):
        mock_mesh_object.users_collection = [
            MockCollection("Level1"),
            MockCollection("Props"),
        ]
        metadata = serialize_object_metadata(mock_mesh_object)
        result = reconstruct_object_from_json(metadata)

        assert "Level1" in result["collections"]
        assert "Props" in result["collections"]
