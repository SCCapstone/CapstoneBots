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


def _serialize_rna_properties(rna_obj, skip_props=None) -> dict:
    """Extract generic RNA properties from a Blender RNA struct."""
    if skip_props is None:
        skip_props = {'rna_type', 'name', 'type'}
    result = {}
    try:
        if not hasattr(rna_obj, "bl_rna"):
            return result
        # Iterate over all properties defined on this blender object wrapper
        for prop_name in rna_obj.bl_rna.properties.keys():
            if prop_name in skip_props:
                continue
            
            bl_prop = rna_obj.bl_rna.properties[prop_name]
            # Skip read-only properties
            if getattr(bl_prop, "is_readonly", False):
                continue
            
            try:
                val = getattr(rna_obj, prop_name)
                # primitive types supported directly by JSON
                if isinstance(val, (int, float, str, bool)):
                    result[prop_name] = val
                elif val is None:
                    result[prop_name] = None
                elif hasattr(val, "name"):
                    # Object references, material references, etc.
                    result[prop_name] = {"__ref__": val.name, "type": getattr(type(val), "__name__", "Unknown")}
                elif hasattr(val, "__iter__") and not isinstance(val, dict):
                    # Vectors, Colors, etc.
                    items = []
                    for item in val:
                        if isinstance(item, (int, float, str, bool)):
                            items.append(item)
                        elif item is None:
                            items.append(None)
                        elif hasattr(item, "name"):
                            items.append({"__ref__": item.name, "type": getattr(type(item), "__name__", "Unknown")})
                        else:
                            items.append(str(item))
                    result[prop_name] = items
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Error serializing RNA properties for {getattr(rna_obj, 'name', 'unnamed')}: {e}")
    return result


def _serialize_modifiers(obj) -> list:
    result = []
    for mod in (obj.modifiers or []):
        mod_dict = {
            "name": mod.name, 
            "type": mod.type,
            "rna_props": _serialize_rna_properties(mod)
        }
        result.append(mod_dict)
    return result


def _serialize_constraints(obj) -> list:
    result = []
    for con in (obj.constraints or []):
        con_dict = {
            "name": con.name, 
            "type": con.type,
            "rna_props": _serialize_rna_properties(con)
        }
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
        if not slot.material:
            result.append({"name": None, "link": getattr(slot, "link", "OBJECT")})
            continue

        mat = slot.material
        mat_info = {
            "name": mat.name,
            "link": getattr(slot, "link", "OBJECT"),
            "use_nodes": bool(getattr(mat, "use_nodes", False)),
            "diffuse_color": list(mat.diffuse_color) if hasattr(mat, "diffuse_color") else None,
            "metallic": float(getattr(mat, "metallic", 0.0)),
            "roughness": float(getattr(mat, "roughness", 0.5)),
            "blend_method": str(getattr(mat, "blend_method", "OPAQUE")),
            "rna_props": _serialize_rna_properties(mat, skip_props={'rna_type', 'name', 'node_tree'})
        }

        # Node tree extraction
        try:
            if mat_info["use_nodes"] and mat.node_tree:
                nodes = []
                for n in mat.node_tree.nodes:
                    node_data = {
                        "name": n.name,
                        "type": n.type,
                        # bl_idname is the identifier needed by nodes.new()
                        # (n.type is a short enum like "BSDF_PRINCIPLED",
                        #  but nodes.new() needs "ShaderNodeBsdfPrincipled")
                        "bl_idname": getattr(n, "bl_idname", n.type),
                        "label": n.label,
                        "location": list(n.location) if hasattr(n, "location") else [0,0],
                        "width": getattr(n, "width", 140.0),
                        "inputs": {},
                        "rna_props": _serialize_rna_properties(n, skip_props={'rna_type', 'name', 'type', 'inputs', 'outputs'})
                    }
                    for inp in n.inputs:
                        if not getattr(inp, "is_linked", False) and hasattr(inp, "default_value"):
                            val = inp.default_value
                            if isinstance(val, (int, float, str, bool)):
                                node_data["inputs"][inp.name] = val
                            elif hasattr(val, "__iter__"):
                                node_data["inputs"][inp.name] = list(val)
                    nodes.append(node_data)
                mat_info["nodes"] = nodes

                links = []
                for link in mat.node_tree.links:
                    links.append({
                        "from_node": link.from_node.name,
                        "from_socket": getattr(link.from_socket, "name", ""),
                        "to_node": link.to_node.name,
                        "to_socket": getattr(link.to_socket, "name", "")
                    })
                mat_info["links"] = links
        except Exception as e:
            logger.warning(f"Error serializing material nodes for {mat.name}: {e}")

        result.append(mat_info)

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

def compute_object_hash(json_data: dict, binary_data: bytes = None) -> str:
    """
    Compute SHA-256 hash of object metadata (and optional mesh binary) for deduplication.

    Args:
        json_data: Object metadata dict
        binary_data: Optional mesh data bytes. If provided, included in hash.

    Returns:
        64-character hex string
    """
    canonical = json.dumps(json_data, sort_keys=True, separators=(",", ":"))
    hasher = hashlib.sha256(canonical.encode("utf-8"))
    if binary_data:
        hasher.update(binary_data)
    return hasher.hexdigest()


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

def clear_scene():
    """
    Remove all objects from the current Blender scene and purge orphan data-blocks.

    This prepares a blank slate so that ``reconstruct_scene`` can recreate
    the scene from remote data without leaving duplicates behind.
    """
    import bpy

    # Deselect everything first
    bpy.ops.object.select_all(action='DESELECT')

    # Remove ALL objects in the file, not just those in the root scene
    # collection.  bpy.data.objects covers sub-collections too, preventing
    # duplicates caused by leftover objects in nested collections.
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    # Purge orphan data-blocks (meshes, materials, cameras, lights, etc.
    # that now have zero users after the objects were removed).
    try:
        bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=True)
    except Exception:
        # orphans_purge can fail if the outliner context isn't available;
        # the objects are already removed so this is non-fatal.
        pass

    logger.info("Scene cleared and orphan data-blocks purged")


def _apply_rna_properties(rna_obj, rna_props: dict):
    """Apply serialized generic RNA properties to a Blender object/struct."""
    import bpy
    for prop_name, val in rna_props.items():
        try:
            # Skip if explicitly read-only
            bl_prop = getattr(rna_obj.bl_rna.properties, prop_name, None)
            if bl_prop and getattr(bl_prop, "is_readonly", False):
                continue

            # Handle references
            if isinstance(val, dict) and "__ref__" in val:
                ref_name = val["__ref__"]
                ref_type = val.get("type", "")
                
                ref_obj = None
                if ref_type == "Object":
                    ref_obj = bpy.data.objects.get(ref_name)
                elif ref_type == "Material":
                    ref_obj = bpy.data.materials.get(ref_name)
                elif ref_type == "Collection":
                    ref_obj = bpy.data.collections.get(ref_name)
                elif ref_type == "Mesh":
                    ref_obj = bpy.data.meshes.get(ref_name)
                elif ref_type == "Camera":
                    ref_obj = bpy.data.cameras.get(ref_name)
                    
                if ref_obj:
                    setattr(rna_obj, prop_name, ref_obj)
                continue

            # Handle vectors/lists
            if isinstance(val, list):
                current_val = getattr(rna_obj, prop_name, None)
                if current_val is not None and hasattr(current_val, "__len__"):
                    try:
                        if len(current_val) == len(val):
                            for i, v in enumerate(val):
                                if isinstance(v, dict) and "__ref__" in v:
                                    continue
                                current_val[i] = v
                            continue
                    except Exception:
                        pass
                        
            # Scalar values
            setattr(rna_obj, prop_name, val)
        except Exception:
            pass


# Mapping from Blender node .type enum → bl_idname for backward compat
# with serialized data that only stored the short type string.
_NODE_TYPE_TO_IDNAME = {
    "BSDF_PRINCIPLED": "ShaderNodeBsdfPrincipled",
    "OUTPUT_MATERIAL": "ShaderNodeOutputMaterial",
    "TEX_IMAGE": "ShaderNodeTexImage",
    "TEX_ENVIRONMENT": "ShaderNodeTexEnvironment",
    "TEX_NOISE": "ShaderNodeTexNoise",
    "TEX_VORONOI": "ShaderNodeTexVoronoi",
    "TEX_WAVE": "ShaderNodeTexWave",
    "TEX_GRADIENT": "ShaderNodeTexGradient",
    "TEX_MAGIC": "ShaderNodeTexMagic",
    "TEX_CHECKER": "ShaderNodeTexChecker",
    "TEX_BRICK": "ShaderNodeTexBrick",
    "TEX_COORD": "ShaderNodeTexCoord",
    "TEX_MUSGRAVE": "ShaderNodeTexMusgrave",
    "MAPPING": "ShaderNodeMapping",
    "MIX_RGB": "ShaderNodeMixRGB",
    "MIX": "ShaderNodeMix",
    "MIX_SHADER": "ShaderNodeMixShader",
    "ADD_SHADER": "ShaderNodeAddShader",
    "BSDF_DIFFUSE": "ShaderNodeBsdfDiffuse",
    "BSDF_GLOSSY": "ShaderNodeBsdfGlossy",
    "BSDF_TRANSPARENT": "ShaderNodeBsdfTransparent",
    "BSDF_GLASS": "ShaderNodeBsdfGlass",
    "EMISSION": "ShaderNodeEmission",
    "BACKGROUND": "ShaderNodeBackground",
    "SUBSURFACE_SCATTERING": "ShaderNodeSubsurfaceScattering",
    "BUMP": "ShaderNodeBump",
    "NORMAL_MAP": "ShaderNodeNormalMap",
    "DISPLACEMENT": "ShaderNodeDisplacement",
    "MATH": "ShaderNodeMath",
    "VECT_MATH": "ShaderNodeVectorMath",
    "SEPARATE_XYZ": "ShaderNodeSeparateXYZ",
    "COMBINE_XYZ": "ShaderNodeCombineXYZ",
    "SEPARATE_RGB": "ShaderNodeSeparateRGB",
    "COMBINE_RGB": "ShaderNodeCombineRGB",
    "SEPARATE_COLOR": "ShaderNodeSeparateColor",
    "COMBINE_COLOR": "ShaderNodeCombineColor",
    "RGB": "ShaderNodeRGB",
    "VALUE": "ShaderNodeValue",
    "INVERT": "ShaderNodeInvert",
    "HUE_SAT": "ShaderNodeHueSaturation",
    "GAMMA": "ShaderNodeGamma",
    "BRIGHTCONTRAST": "ShaderNodeBrightContrast",
    "CLAMP": "ShaderNodeClamp",
    "MAP_RANGE": "ShaderNodeMapRange",
    "FRESNEL": "ShaderNodeFresnel",
    "LAYER_WEIGHT": "ShaderNodeLayerWeight",
    "BLACKBODY": "ShaderNodeBlackbody",
    "WAVELENGTH": "ShaderNodeWavelength",
    "CURVE_RGB": "ShaderNodeRGBCurve",
    "CURVE_VEC": "ShaderNodeVectorCurve",
    "CURVE_FLOAT": "ShaderNodeFloatCurve",
    "OBJECT_INFO": "ShaderNodeObjectInfo",
    "VERTEX_COLOR": "ShaderNodeVertexColor",
    "ATTRIBUTE": "ShaderNodeAttribute",
    "UVMAP": "ShaderNodeUVMap",
    "TANGENT": "ShaderNodeTangent",
    "GEOMETRY": "ShaderNodeNewGeometry",
    "CAMERA": "ShaderNodeCameraData",
    "LIGHT_PATH": "ShaderNodeLightPath",
    "HOLDOUT": "ShaderNodeHoldout",
    "VOLUME_ABSORPTION": "ShaderNodeVolumeAbsorption",
    "VOLUME_SCATTER": "ShaderNodeVolumeScatter",
    "PRINCIPLED_VOLUME": "ShaderNodeVolumePrincipled",
    "REROUTE": "NodeReroute",
    "GROUP": "ShaderNodeGroup",
    "FRAME": "NodeFrame",
    "GROUP_INPUT": "NodeGroupInput",
    "GROUP_OUTPUT": "NodeGroupOutput",
    "VALTORGB": "ShaderNodeValToRGB",
    "RGBTOBW": "ShaderNodeRGBToBW",
    "COLOR_RAMP": "ShaderNodeValToRGB",
}


def reconstruct_scene(objects_data: list, mesh_binaries: dict,
                      clear_existing: bool = False):
    """
    Reconstruct a Blender scene from serialized object data.

    This function is meant to run inside Blender. It creates objects,
    applies transforms, materials, modifiers, and parent relationships.

    Args:
        objects_data: List of object metadata dicts
        mesh_binaries: Dict mapping object_name -> binary mesh data
        clear_existing: If True, remove all existing scene objects before
            reconstruction. Use this for a clean pull to avoid duplicates.
    """
    import bpy

    if clear_existing:
        clear_scene()
    else:
        # Even when not clearing the whole scene (dirty pull / merge),
        # remove any existing objects whose names match the incoming data
        # so we replace them instead of creating duplicates (Cube.001, etc.).
        incoming_names = {od["object_name"] for od in objects_data}
        for obj in list(bpy.data.objects):
            if obj.name in incoming_names:
                bpy.data.objects.remove(obj, do_unlink=True)

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
                
                if "use_nodes" in mat_info:
                    mat.use_nodes = mat_info["use_nodes"]
                if "diffuse_color" in mat_info and mat_info["diffuse_color"]:
                    mat.diffuse_color = mat_info["diffuse_color"]
                if "metallic" in mat_info: mat.metallic = mat_info["metallic"]
                if "roughness" in mat_info: mat.roughness = mat_info["roughness"]
                if "blend_method" in mat_info: mat.blend_method = mat_info["blend_method"]
                
                if "rna_props" in mat_info:
                    _apply_rna_properties(mat, mat_info["rna_props"])

                # Reconstruct material nodes
                if mat.use_nodes and "nodes" in mat_info and mat.node_tree:
                    tree = mat.node_tree
                    tree.nodes.clear() # clear defaults
                    node_map = {}

                    for n_data in mat_info["nodes"]:
                        try:
                            # Use bl_idname (correct identifier for nodes.new).
                            # Fall back to type → bl_idname mapping for old data
                            # that only stored the short enum type.
                            node_id = n_data.get("bl_idname") or \
                                      _NODE_TYPE_TO_IDNAME.get(n_data["type"]) or \
                                      n_data["type"]
                            n = tree.nodes.new(type=node_id)
                            n.name = n_data["name"]
                            if "label" in n_data: n.label = n_data["label"]
                            if "location" in n_data: n.location = n_data["location"]
                            if "width" in n_data: n.width = n_data["width"]
                            
                            if "rna_props" in n_data:
                                _apply_rna_properties(n, n_data["rna_props"])

                            for inp_name, inp_val in n_data.get("inputs", {}).items():
                                if inp_name in n.inputs:
                                    try:
                                        if isinstance(inp_val, list):
                                            dv = n.inputs[inp_name].default_value
                                            for i, v in enumerate(inp_val):
                                                if hasattr(dv, "__len__") and i < len(dv):
                                                    dv[i] = v
                                        else:
                                            n.inputs[inp_name].default_value = inp_val
                                    except Exception:
                                        pass
                            node_map[n_data["name"]] = n
                        except Exception:
                            pass

                    # Reconstruct links
                    for link_data in mat_info.get("links", []):
                        try:
                            f_node = node_map.get(link_data["from_node"])
                            t_node = node_map.get(link_data["to_node"])
                            if f_node and t_node:
                                f_socket = f_node.outputs.get(link_data["from_socket"])
                                t_socket = t_node.inputs.get(link_data["to_socket"])
                                if f_socket and t_socket:
                                    tree.links.new(t_socket, f_socket)
                        except Exception:
                            pass

                bl_obj.data.materials.append(mat)

        # Modifiers
        for mod_info in obj_data.get("modifiers", []):
            try:
                mod = bl_obj.modifiers.new(mod_info["name"], mod_info["type"])
                if "rna_props" in mod_info:
                    _apply_rna_properties(mod, mod_info["rna_props"])
                else:
                    # Fallback for old formatting
                    for key, val in mod_info.items():
                        if key not in ("name", "type"):
                            try:
                                setattr(mod, key, val)
                            except Exception:
                                pass
            except Exception:
                pass

        # Constraints
        for con_info in obj_data.get("constraints", []):
            try:
                con = bl_obj.constraints.new(con_info["type"])
                con.name = con_info["name"]
                if "rna_props" in con_info:
                    _apply_rna_properties(con, con_info["rna_props"])
                else:
                    # Fallback for old formatting
                    for key, val in con_info.items():
                        if key not in ("name", "type"):
                            try:
                                setattr(con, key, val)
                            except Exception:
                                pass
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
