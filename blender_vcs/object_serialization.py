"""
Object-level serialization and deserialization for BVCS.

Provides functions to:
- Serialize Blender objects to JSON metadata + binary mesh data
- Compute content hashes for deduplication
- Deserialize/reconstruct objects from stored data
"""
import json
import hashlib
import logging

logger = logging.getLogger("BVCS")


# ── Serialization ────────────────────────────────────────────────────────────

def serialize_object_metadata(obj) -> dict:
    """
    Extract JSON-serializable metadata from a Blender object.

    Args:
        obj: A bpy.types.Object (or mock equivalent)

    Returns:
        dict with object_name, object_type, transform, parent, collections,
        modifiers, constraints, custom_properties, materials, visibility,
        and type-specific data.
    """
    metadata = {
        "object_name": obj.name,
        "object_type": obj.type,
        "transform": {
            "location": list(obj.location),
            "rotation_euler": list(obj.rotation_euler),
            "scale": list(obj.scale),
        },
        "parent": obj.parent.name if obj.parent else None,
        "collections": [c.name for c in (obj.users_collection or [])],
        "modifiers": _serialize_modifiers(obj),
        "constraints": _serialize_constraints(obj),
        "custom_properties": _serialize_custom_properties(obj),
        "materials": _serialize_materials(obj),
        "visibility": {
            "hide_viewport": bool(obj.hide_viewport),
            "hide_render": bool(obj.hide_render),
            "hide_select": bool(obj.hide_select),
        },
    }

    # Type-specific data
    type_data = _serialize_type_data(obj)
    if type_data:
        metadata["type_data"] = type_data

    return metadata


def _serialize_modifiers(obj) -> list:
    result = []
    for mod in (obj.modifiers or []):
        mod_dict = {"name": mod.name, "type": mod.type}
        # Extract common modifier properties based on type
        if mod.type == "SUBSURF":
            mod_dict["levels"] = getattr(mod, "levels", 1)
            mod_dict["render_levels"] = getattr(mod, "render_levels", 2)
        elif mod.type == "MIRROR":
            mod_dict["use_axis"] = [
                getattr(mod, "use_axis", [True, False, False])
            ] if not isinstance(getattr(mod, "use_axis", None), list) else getattr(mod, "use_axis")
        elif mod.type == "ARRAY":
            mod_dict["count"] = getattr(mod, "count", 2)
        elif mod.type == "SOLIDIFY":
            mod_dict["thickness"] = getattr(mod, "thickness", 0.01)
        elif mod.type == "BEVEL":
            mod_dict["width"] = getattr(mod, "width", 0.1)
            mod_dict["segments"] = getattr(mod, "segments", 1)
        result.append(mod_dict)
    return result


def _serialize_constraints(obj) -> list:
    result = []
    for con in (obj.constraints or []):
        con_dict = {"name": con.name, "type": con.type}
        # Common constraint properties
        if hasattr(con, "target") and con.target:
            try:
                con_dict["target"] = con.target.name
            except Exception:
                pass
        if hasattr(con, "influence"):
            try:
                con_dict["influence"] = float(con.influence)
            except Exception:
                pass
        result.append(con_dict)
    return result


def _serialize_custom_properties(obj) -> dict:
    """Serialize custom properties, skipping RNA/internal keys."""
    props = {}
    try:
        for key in obj.keys():
            if key.startswith("_") or key.startswith("bvcs_"):
                continue
            val = obj[key]
            # Only store JSON-serializable types
            if isinstance(val, (int, float, str, bool)):
                props[key] = val
            elif isinstance(val, (list, tuple)):
                props[key] = list(val)
            elif isinstance(val, dict):
                props[key] = val
            else:
                try:
                    props[key] = list(val)
                except (TypeError, ValueError):
                    props[key] = str(val)
    except Exception:
        pass
    return props


def _serialize_materials(obj) -> list:
    result = []
    for slot in (obj.material_slots or []):
        if slot.material:
            result.append({
                "name": slot.material.name,
                "link": getattr(slot, "link", "OBJECT"),
            })
        else:
            result.append({"name": None, "link": getattr(slot, "link", "OBJECT")})
    return result


def _serialize_type_data(obj) -> dict:
    """Serialize type-specific data (camera, light, armature, empty)."""
    obj_type = obj.type

    if obj_type == "CAMERA" and obj.data:
        return {
            "lens": obj.data.lens,
            "clip_start": obj.data.clip_start,
            "clip_end": obj.data.clip_end,
            "sensor_width": obj.data.sensor_width,
            "camera_type": obj.data.type,
        }

    elif obj_type == "LIGHT" and obj.data:
        return {
            "light_type": obj.data.type,
            "energy": obj.data.energy,
            "color": list(obj.data.color),
            "shadow_soft_size": obj.data.shadow_soft_size,
        }

    elif obj_type == "ARMATURE" and obj.data:
        bones = []
        for bone in obj.data.bones:
            bones.append({
                "name": bone.name,
                "head": list(bone.head),
                "tail": list(bone.tail),
                "parent": bone.parent.name if bone.parent else None,
                "use_connect": bool(bone.use_connect),
            })
        return {"bones": bones}

    elif obj_type == "EMPTY":
        return {
            "empty_display_type": getattr(obj, "empty_display_type", "PLAIN_AXES"),
            "empty_display_size": getattr(obj, "empty_display_size", 1.0),
        }

    return {}


# ── Mesh Data Serialization (Binary) ────────────────────────────────────────

def serialize_mesh_data(obj) -> bytes:
    """
    Serialize mesh geometry data to a JSON-encoded binary format.

    Extracts vertices, edges, faces, UVs, vertex groups, and shape keys
    from the evaluated mesh.

    Args:
        obj: A bpy.types.Object with type MESH (or mock equivalent)

    Returns:
        bytes: JSON-encoded mesh data
    """
    mesh = obj.data
    if mesh is None:
        return json.dumps({"vertex_count": 0, "vertices": [], "edges": [],
                           "polygons": [], "polygon_count": 0}).encode("utf-8")

    # Vertices
    vertices = [list(v.co) for v in mesh.vertices]
    normals = [list(v.normal) for v in mesh.vertices]

    # Edges
    edges = [list(e.vertices) for e in mesh.edges]

    # Polygons
    polygons = []
    for poly in mesh.polygons:
        polygons.append({
            "vertices": list(poly.vertices),
            "loop_start": poly.loop_start,
            "loop_total": poly.loop_total,
        })

    # UV layers
    uv_layers = []
    for uv_layer in (mesh.uv_layers or []):
        uv_data = [list(d.uv) for d in uv_layer.data]
        uv_layers.append({
            "name": uv_layer.name,
            "data": uv_data,
        })

    # Vertex groups
    vertex_groups = []
    if hasattr(obj, "vertex_groups") and obj.vertex_groups:
        vg_names = {vg.index: vg.name for vg in obj.vertex_groups}
        vertex_groups = [
            {"name": vg.name, "index": vg.index}
            for vg in obj.vertex_groups
        ]

        # Per-vertex weights
        vertex_weights = []
        for v in mesh.vertices:
            weights = []
            for g in v.groups:
                group_name = vg_names.get(g.group, str(g.group))
                weights.append({"group": group_name, "weight": g.weight})
            vertex_weights.append(weights)
    else:
        vertex_weights = []

    # Shape keys
    shape_keys = []
    if mesh.shape_keys and hasattr(mesh.shape_keys, "key_blocks"):
        for sk in mesh.shape_keys.key_blocks:
            sk_data = [list(point.co) for point in sk.data]
            shape_keys.append({
                "name": sk.name,
                "relative_key": sk.relative_key.name if sk.relative_key else None,
                "data": sk_data,
            })

    result = {
        "vertex_count": len(vertices),
        "vertices": vertices,
        "normals": normals,
        "edges": edges,
        "polygon_count": len(polygons),
        "polygons": polygons,
        "uv_layers": uv_layers,
        "vertex_groups": vertex_groups,
        "vertex_weights": vertex_weights,
        "shape_keys": shape_keys,
    }

    return json.dumps(result, separators=(",", ":")).encode("utf-8")


# ── Hash Computation ─────────────────────────────────────────────────────────

def compute_object_hash(json_data: dict) -> str:
    """
    Compute SHA-256 hash of object metadata for deduplication.

    Args:
        json_data: Object metadata dict

    Returns:
        64-character hex string
    """
    canonical = json.dumps(json_data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── Deserialization ──────────────────────────────────────────────────────────

def deserialize_mesh_data(binary: bytes) -> dict:
    """
    Parse binary mesh data back into a dictionary.

    Args:
        binary: JSON-encoded mesh data bytes

    Returns:
        dict with vertices, edges, polygons, uv_layers, etc.
    """
    return json.loads(binary.decode("utf-8"))


def reconstruct_object_from_json(metadata: dict) -> dict:
    """
    Validate and return object metadata ready for Blender reconstruction.

    In a real Blender environment, this would create actual bpy objects.
    For testing, we return the metadata dict with validation that all
    required fields are present.

    Args:
        metadata: Object metadata dict from serialize_object_metadata

    Returns:
        dict: Validated metadata ready for object creation
    """
    required_keys = ["object_name", "object_type", "transform"]
    for key in required_keys:
        if key not in metadata:
            raise ValueError(f"Missing required key: {key}")

    return metadata


# ── Scene Reconstruction (Blender-dependent) ─────────────────────────────────

def reconstruct_scene(objects_data: list, mesh_binaries: dict):
    """
    Reconstruct a Blender scene from serialized object data.

    This function is meant to run inside Blender. It creates objects,
    applies transforms, materials, modifiers, and parent relationships.

    Args:
        objects_data: List of object metadata dicts
        mesh_binaries: Dict mapping object_name -> binary mesh data
    """
    import bpy

    created_objects = {}

    # First pass: create all objects
    for obj_data in objects_data:
        name = obj_data["object_name"]
        obj_type = obj_data["object_type"]
        transform = obj_data.get("transform", {})

        if obj_type == "MESH":
            mesh = bpy.data.meshes.new(name)
            if name in mesh_binaries:
                _apply_mesh_binary(mesh, mesh_binaries[name])
            bl_obj = bpy.data.objects.new(name, mesh)

        elif obj_type == "CAMERA":
            cam = bpy.data.cameras.new(name)
            td = obj_data.get("type_data", {})
            cam.lens = td.get("lens", 50)
            cam.clip_start = td.get("clip_start", 0.1)
            cam.clip_end = td.get("clip_end", 1000)
            cam.sensor_width = td.get("sensor_width", 36)
            cam.type = td.get("camera_type", "PERSP")
            bl_obj = bpy.data.objects.new(name, cam)

        elif obj_type == "LIGHT":
            td = obj_data.get("type_data", {})
            light = bpy.data.lights.new(name, type=td.get("light_type", "POINT"))
            light.energy = td.get("energy", 1000)
            light.color = td.get("color", [1, 1, 1])
            light.shadow_soft_size = td.get("shadow_soft_size", 0.25)
            bl_obj = bpy.data.objects.new(name, light)

        elif obj_type == "ARMATURE":
            arm = bpy.data.armatures.new(name)
            bl_obj = bpy.data.objects.new(name, arm)
            # Bone creation requires edit mode — deferred

        elif obj_type == "EMPTY":
            bl_obj = bpy.data.objects.new(name, None)
            td = obj_data.get("type_data", {})
            bl_obj.empty_display_type = td.get("empty_display_type", "PLAIN_AXES")
            bl_obj.empty_display_size = td.get("empty_display_size", 1.0)

        else:
            # Generic fallback
            bl_obj = bpy.data.objects.new(name, None)

        # Apply transform
        bl_obj.location = transform.get("location", [0, 0, 0])
        bl_obj.rotation_euler = transform.get("rotation_euler", [0, 0, 0])
        bl_obj.scale = transform.get("scale", [1, 1, 1])

        # Visibility
        vis = obj_data.get("visibility", {})
        bl_obj.hide_viewport = vis.get("hide_viewport", False)
        bl_obj.hide_render = vis.get("hide_render", False)
        bl_obj.hide_select = vis.get("hide_select", False)

        # Materials
        for mat_info in obj_data.get("materials", []):
            mat_name = mat_info.get("name")
            if mat_name:
                mat = bpy.data.materials.get(mat_name)
                if not mat:
                    mat = bpy.data.materials.new(mat_name)
                bl_obj.data.materials.append(mat)

        # Modifiers
        for mod_info in obj_data.get("modifiers", []):
            mod = bl_obj.modifiers.new(mod_info["name"], mod_info["type"])
            for key, val in mod_info.items():
                if key not in ("name", "type"):
                    try:
                        setattr(mod, key, val)
                    except Exception:
                        pass

        # Custom properties
        for key, val in obj_data.get("custom_properties", {}).items():
            bl_obj[key] = val

        # Link to scene
        bpy.context.scene.collection.objects.link(bl_obj)
        created_objects[name] = bl_obj

    # Second pass: parent relationships
    for obj_data in objects_data:
        name = obj_data["object_name"]
        parent_name = obj_data.get("parent")
        if parent_name and parent_name in created_objects:
            created_objects[name].parent = created_objects[parent_name]

    # Third pass: collection assignments
    for obj_data in objects_data:
        name = obj_data["object_name"]
        for col_name in obj_data.get("collections", []):
            col = bpy.data.collections.get(col_name)
            if not col:
                col = bpy.data.collections.new(col_name)
                bpy.context.scene.collection.children.link(col)
            if name in created_objects:
                col.objects.link(created_objects[name])

    return created_objects


def _apply_mesh_binary(mesh, binary_data: bytes):
    """
    Populate a bpy.types.Mesh from binary mesh data.

    Args:
        mesh: A bpy.types.Mesh
        binary_data: JSON-encoded mesh data bytes
    """
    data = deserialize_mesh_data(binary_data)

    vertices = [tuple(v) for v in data.get("vertices", [])]
    edges = [tuple(e) for e in data.get("edges", [])]
    faces = [tuple(p["vertices"]) for p in data.get("polygons", [])]

    mesh.from_pydata(vertices, edges, faces)
    mesh.update()

    # UV layers
    for uv_info in data.get("uv_layers", []):
        uv_layer = mesh.uv_layers.new(name=uv_info["name"])
        for i, uv_co in enumerate(uv_info["data"]):
            if i < len(uv_layer.data):
                uv_layer.data[i].uv = uv_co

    # Shape keys
    for sk_info in data.get("shape_keys", []):
        if not mesh.shape_keys:
            mesh.shape_keys_add(name=sk_info["name"])
        else:
            sk = mesh.shape_keys_add(name=sk_info["name"])
            for i, co in enumerate(sk_info.get("data", [])):
                if i < len(sk.data):
                    sk.data[i].co = co
