"""
Shared test fixtures and bpy mocking infrastructure for BVCS addon tests.

Since bpy is only available inside Blender, we mock it for unit testing.

IMPORTANT: The bpy mock must be installed before any blender_vcs imports.
This is handled by the root-level conftest.py which installs the mock
before pytest collects tests.
"""
import sys
import json
import hashlib
from unittest.mock import MagicMock, PropertyMock
from types import ModuleType

import pytest


# ── Mock Blender object factories ────────────────────────────────────────────

class MockVector:
    """Mimics mathutils.Vector / Euler / etc."""
    def __init__(self, values):
        self._values = list(values)

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def __getitem__(self, idx):
        return self._values[idx]

    def __repr__(self):
        return f"MockVector({self._values})"


class MockModifier:
    def __init__(self, name, type_, **props):
        self.name = name
        self.type = type_
        self._props = props
        for k, v in props.items():
            setattr(self, k, v)


class MockConstraint:
    def __init__(self, name, type_, **props):
        self.name = name
        self.type = type_
        self._props = props
        for k, v in props.items():
            setattr(self, k, v)


class MockMaterialSlot:
    def __init__(self, material_name, link="OBJECT"):
        self.material = MagicMock()
        self.material.name = material_name
        self.link = link


class MockCollection:
    def __init__(self, name):
        self.name = name


class MockVertex:
    def __init__(self, co, index=0, normal=None, groups=None):
        self.co = MockVector(co)
        self.index = index
        self.normal = MockVector(normal or [0, 0, 1])
        self.groups = groups or []


class MockVertexGroupElement:
    def __init__(self, group, weight):
        self.group = group
        self.weight = weight


class MockEdge:
    def __init__(self, vertices):
        self.vertices = list(vertices)


class MockLoop:
    def __init__(self, vertex_index, index=0):
        self.vertex_index = vertex_index
        self.index = index


class MockPolygon:
    def __init__(self, vertices, loop_start, loop_total):
        self.vertices = list(vertices)
        self.loop_start = loop_start
        self.loop_total = loop_total


class MockUVLoopLayer:
    def __init__(self, name, uv_data):
        self.name = name
        self.data = uv_data


class MockUVLoopData:
    def __init__(self, uv):
        self.uv = MockVector(uv)


class MockVertexGroup:
    def __init__(self, name, index):
        self.name = name
        self.index = index


class MockShapeKey:
    def __init__(self, name, data, relative_key_name="Basis"):
        self.name = name
        self.data = data
        self.relative_key = MagicMock()
        self.relative_key.name = relative_key_name


class MockShapeKeyPoint:
    def __init__(self, co):
        self.co = MockVector(co)


class MockMesh:
    """Mock of bpy.types.Mesh with geometry data."""
    def __init__(self, vertices=None, edges=None, polygons=None, loops=None,
                 uv_layers=None, vertex_colors=None, shape_keys=None):
        self.vertices = vertices or []
        self.edges = edges or []
        self.polygons = polygons or []
        self.loops = loops or []
        self.uv_layers = uv_layers or []
        self.vertex_colors = vertex_colors or []
        self.shape_keys = shape_keys


class MockBone:
    def __init__(self, name, head, tail, parent_name=None, use_connect=False):
        self.name = name
        self.head = MockVector(head)
        self.tail = MockVector(tail)
        self.parent = None
        self.use_connect = use_connect
        self._parent_name = parent_name


class MockArmature:
    def __init__(self, bones):
        self.bones = bones
        # Wire up parent references
        bone_map = {b.name: b for b in bones}
        for b in bones:
            if b._parent_name and b._parent_name in bone_map:
                b.parent = bone_map[b._parent_name]


def make_mock_object(
    name="Cube",
    type_="MESH",
    location=(0, 0, 0),
    rotation=(0, 0, 0),
    scale=(1, 1, 1),
    parent=None,
    collections=None,
    modifiers=None,
    constraints=None,
    material_slots=None,
    hide_viewport=False,
    hide_render=False,
    hide_select=False,
    data=None,
    custom_properties=None,
):
    """Create a mock Blender object for testing."""
    obj = MagicMock()
    obj.name = name
    obj.type = type_
    obj.location = MockVector(location)
    obj.rotation_euler = MockVector(rotation)
    obj.scale = MockVector(scale)
    obj.parent = parent
    obj.users_collection = collections or []
    obj.modifiers = modifiers or []
    obj.constraints = constraints or []
    obj.material_slots = material_slots or []
    obj.hide_viewport = hide_viewport
    obj.hide_render = hide_render
    obj.hide_select = hide_select
    obj.data = data

    # Custom properties: bpy objects act like dicts for custom props
    _custom = custom_properties or {}
    obj.keys.return_value = list(_custom.keys())
    obj.__getitem__ = lambda self, key: _custom[key]
    obj.__contains__ = lambda self, key: key in _custom
    obj.items.return_value = list(_custom.items())

    return obj


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_mesh_object():
    """A basic MESH object with geometry."""
    verts = [
        MockVertex([0, 0, 0], 0),
        MockVertex([1, 0, 0], 1),
        MockVertex([1, 1, 0], 2),
        MockVertex([0, 1, 0], 3),
    ]
    edges = [MockEdge([0, 1]), MockEdge([1, 2]), MockEdge([2, 3]), MockEdge([3, 0])]
    loops = [MockLoop(0, 0), MockLoop(1, 1), MockLoop(2, 2), MockLoop(3, 3)]
    polys = [MockPolygon([0, 1, 2, 3], loop_start=0, loop_total=4)]
    uv_data = [MockUVLoopData([0, 0]), MockUVLoopData([1, 0]),
                MockUVLoopData([1, 1]), MockUVLoopData([0, 1])]
    uv_layer = MockUVLoopLayer("UVMap", uv_data)

    mesh = MockMesh(
        vertices=verts,
        edges=edges,
        polygons=polys,
        loops=loops,
        uv_layers=[uv_layer],
    )

    obj = make_mock_object(
        name="Cube",
        type_="MESH",
        location=(1.0, 2.0, 3.0),
        rotation=(0.0, 0.0, 1.5708),
        scale=(1.0, 1.0, 1.0),
        data=mesh,
        material_slots=[MockMaterialSlot("Material.001")],
        modifiers=[MockModifier("Subsurf", "SUBSURF", levels=2, render_levels=3)],
    )
    return obj


@pytest.fixture
def mock_camera_object():
    """A CAMERA object."""
    cam_data = MagicMock()
    cam_data.lens = 50.0
    cam_data.clip_start = 0.1
    cam_data.clip_end = 1000.0
    cam_data.sensor_width = 36.0
    cam_data.type = "PERSP"

    return make_mock_object(
        name="Camera",
        type_="CAMERA",
        location=(7.0, -6.0, 5.0),
        data=cam_data,
    )


@pytest.fixture
def mock_light_object():
    """A LIGHT object."""
    light_data = MagicMock()
    light_data.type = "POINT"
    light_data.energy = 1000.0
    light_data.color = MockVector([1.0, 0.8, 0.6])
    light_data.shadow_soft_size = 0.25

    return make_mock_object(
        name="Light",
        type_="LIGHT",
        location=(4.0, 1.0, 6.0),
        data=light_data,
    )


@pytest.fixture
def mock_armature_object():
    """An ARMATURE object with bone hierarchy."""
    bones = [
        MockBone("Root", [0, 0, 0], [0, 0, 1]),
        MockBone("Spine", [0, 0, 1], [0, 0, 2], parent_name="Root", use_connect=True),
        MockBone("Head", [0, 0, 2], [0, 0, 2.5], parent_name="Spine", use_connect=True),
    ]
    arm_data = MockArmature(bones)

    return make_mock_object(
        name="Armature",
        type_="ARMATURE",
        data=arm_data,
    )


@pytest.fixture
def mock_empty_object():
    """An EMPTY object."""
    obj = make_mock_object(
        name="Empty",
        type_="EMPTY",
        data=MagicMock(),
        custom_properties={"custom_float": 3.14, "custom_str": "hello"},
    )
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = 1.0
    return obj
