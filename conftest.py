"""
Root conftest.py — installs bpy mock before any test collection.

This must be at the repository root so it runs before pytest attempts
to import blender_vcs/__init__.py (which imports bpy at module level).
"""
import sys
from unittest.mock import MagicMock


def _build_mock_bpy():
    bpy = MagicMock()

    for prop in (
        "StringProperty", "BoolProperty", "IntProperty", "FloatProperty",
        "EnumProperty", "FloatVectorProperty", "IntVectorProperty",
        "PointerProperty", "CollectionProperty",
    ):
        setattr(bpy.props, prop, MagicMock(return_value=None))

    bpy.types.Operator = type("Operator", (), {"bl_idname": "", "bl_label": ""})
    bpy.types.Panel = type("Panel", (), {})
    bpy.types.AddonPreferences = type("AddonPreferences", (), {})
    bpy.types.WindowManager = MagicMock()
    bpy.types.Mesh = MagicMock()
    bpy.types.Object = MagicMock()

    bpy.utils.register_class = MagicMock()
    bpy.utils.unregister_class = MagicMock()

    bpy.data.meshes = MagicMock()
    bpy.data.objects = MagicMock()
    bpy.data.cameras = MagicMock()
    bpy.data.lights = MagicMock()
    bpy.data.armatures = MagicMock()
    bpy.data.materials = MagicMock()
    bpy.data.collections = MagicMock()
    bpy.data.libraries = []
    bpy.data.images = []

    bpy.context.window_manager = MagicMock()
    bpy.context.blend_data = MagicMock()
    bpy.context.blend_data.filepath = "/tmp/test.blend"
    bpy.context.scene = MagicMock()
    bpy.context.scene.objects = []
    bpy.context.evaluated_depsgraph_get = MagicMock()
    bpy.context.preferences = MagicMock()
    bpy.context.selected_objects = []

    bpy.ops.wm = MagicMock()
    bpy.ops.object = MagicMock()

    bpy.path.abspath = lambda x: x
    bpy.app.binary_path = "/usr/bin/blender"

    return bpy


if "bpy" not in sys.modules:
    sys.modules["bpy"] = _build_mock_bpy()
