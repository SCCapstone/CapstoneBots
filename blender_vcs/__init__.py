bl_info = {
    "name": "BVCS",
    "author": "Capstone Bots",
    "version": (0, 0, 12),
    "blender": (4, 5, 0),
    "location": "View3D > N Panel > BVCS",
    "description": "Blender Version Control System Add-on: login, create/open project, add objects, commit, push, pull, detect conflicts",
    "category": "System",
}

import bpy
import requests
import json
import hashlib
import base64
from uuid import uuid4

BL_ID = "blender_vcs" 

# ---------------- Preferences ----------------
class BVCSAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = BL_ID

    api_url: bpy.props.StringProperty(
        name="API URL",
        default= "https://capstonebots-production.up.railway.app" or "http://localhost:8000",
    )
    auth_token: bpy.props.StringProperty(
        name="JWT Token",
        default="",
    )
    project_id: bpy.props.StringProperty(
        name="Default Project ID",
        default="",
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "api_url")
        layout.prop(self, "auth_token")
        layout.prop(self, "project_id")

# ---------------- Helpers ----------------
def get_prefs(context):
    prefs_container = context.preferences.addons.get(BL_ID)
    if not prefs_container:
        raise RuntimeError("BVCS preferences not found")
    return prefs_container.preferences

def get_bvcs_login_state():
    wm = bpy.context.window_manager
    if "bvcs_logged_in" not in wm:
        prefs = get_prefs(bpy.context)
        wm["bvcs_logged_in"] = bool(prefs.auth_token)
    return wm

def normalize_user_dict(user: dict) -> dict:
    if not isinstance(user, dict):
        return user
    if "user_id" not in user:
        if "id" in user:
            user["user_id"] = user["id"]
        elif "userId" in user:
            user["user_id"] = user["userId"]
    return user

def get_logged_in_user(prefs):
    if not prefs or not getattr(prefs, "auth_token", None):
        return None
    headers = {"Authorization": f"Bearer {prefs.auth_token}"}
    try:
        resp = requests.get(f"{prefs.api_url}/api/auth/me", headers=headers, timeout=5)
        resp.raise_for_status()
        user = resp.json()
        return normalize_user_dict(user)
    except Exception:
        return None

# ---------------- Operators ----------------
class BVCS_OT_Login(bpy.types.Operator):
    bl_idname = "bvcs.login"
    bl_label = "Login to BVCS"

    email: bpy.props.StringProperty(name="Email")
    password: bpy.props.StringProperty(name="Password", subtype='PASSWORD')

    def execute(self, context):
        prefs = get_prefs(context)
        url = f"{prefs.api_url}/api/auth/login"
        try:
            resp = requests.post(url, json={"email": self.email, "password": self.password}, timeout=5)
            if resp.status_code == 200:
                token = resp.json().get("access_token") or resp.json().get("token")
                if not token:
                    self.report({'ERROR'}, "Login response missing token")
                    return {'CANCELLED'}
                prefs.auth_token = token
                wm = get_bvcs_login_state()
                wm["bvcs_logged_in"] = True
                self.report({'INFO'}, "Login successful!")
            else:
                self.report({'ERROR'}, f"Login failed: {resp.status_code}")
        except Exception as e:
            self.report({'ERROR'}, f"Error connecting to server: {e}")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

class BVCS_OT_Logout(bpy.types.Operator):
    bl_idname = "bvcs.logout"
    bl_label = "Logout"

    def execute(self, context):
        prefs = get_prefs(context)
        prefs.auth_token = ""
        prefs.project_id = ""
        wm = get_bvcs_login_state()
        wm["bvcs_logged_in"] = False
        self.report({'INFO'}, "Logged out")
        return {'FINISHED'}

class BVCS_OT_CreateProject(bpy.types.Operator):
    bl_idname = "bvcs.create_project"
    bl_label = "Create New Project"

    project_name: bpy.props.StringProperty(name="Project Name")
    project_description: bpy.props.StringProperty(name="Description", default="")

    def execute(self, context):
        prefs = get_prefs(context)
        user = get_logged_in_user(prefs)
        if not user:
            self.report({'ERROR'}, "Cannot get logged-in user")
            return {'CANCELLED'}

        payload = {
            "name": self.project_name,
            "description": self.project_description,
            "owner_id": user["user_id"],
            "active": True
        }
        headers = {"Authorization": f"Bearer {prefs.auth_token}"}
        try:
            resp = requests.post(f"{prefs.api_url}/api/projects", json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            project = resp.json()
            proj_id = project.get("project_id") or project.get("id")
            if proj_id:
                prefs.project_id = proj_id
                self.report({'INFO'}, f"Project created: {self.project_name}")
            else:
                self.report({'WARNING'}, "Project created but ID not found")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to create project: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

class BVCS_OT_SelectProject(bpy.types.Operator):
    bl_idname = "bvcs.select_project"
    bl_label = "Open Existing Project"

    project_enum: bpy.props.EnumProperty(
        name="Project",
        description="Choose a project",
        items=lambda self, context: get_user_projects(self, context)
    )

    def execute(self, context):
        prefs = get_prefs(context)
        prefs.project_id = self.project_enum
        self.report({'INFO'}, f"Selected project {self.project_enum}")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

def get_user_projects(self, context):
    prefs = get_prefs(context)
    headers = {"Authorization": f"Bearer {prefs.auth_token}"}
    try:
        resp = requests.get(f"{prefs.api_url}/api/projects", headers=headers, timeout=5)
        resp.raise_for_status()
        projects = resp.json()
        return [(str(p["project_id"]), p["name"], p.get("description", "")) for p in projects]
    except Exception:
        return []

# ---------------- Stage Objects ----------------
class BVCS_OT_StageObjects(bpy.types.Operator):
    bl_idname = "bvcs.stage_objects"
    bl_label = "Stage Selected Objects"

    staged_objects: list = []

    def execute(self, context):
        selected_objects = context.selected_objects
        if not selected_objects:
            self.report({'ERROR'}, "No objects selected")
            return {'CANCELLED'}

        BVCS_OT_StageObjects.staged_objects = [obj.name for obj in selected_objects]

        self.report({'INFO'}, f"Staged {len(selected_objects)} objects")
        print("[BVCS] STAGED OBJECTS:", BVCS_OT_StageObjects.staged_objects)

        return {'FINISHED'}

# ---------------- Commit ----------------
class BVCS_OT_Commit(bpy.types.Operator):
    bl_idname = "bvcs.commit"
    bl_label = "Commit Staged Objects"

    commit_message: bpy.props.StringProperty(name="Commit Message", default="Updated objects")

    def execute(self, context):
        prefs = get_prefs(context)
        if not prefs.project_id:
            self.report({'ERROR'}, "No project selected")
            return {'CANCELLED'}

        staged = BVCS_OT_StageObjects.staged_objects
        if not staged:
            self.report({'ERROR'}, "No staged objects to commit")
            return {'CANCELLED'}

        objects_data = []
        for obj_name in staged:
            obj = bpy.data.objects.get(obj_name)
            if not obj:
                continue

            # JSON metadata
            json_data = {
                "name": obj.name,
                "type": obj.type
            }

            # Mesh data encoded as Base64
            mesh_base64 = None
            if obj.type == 'MESH':
                try:
                    mesh_list = [[v.co.x, v.co.y, v.co.z] for v in obj.data.vertices]
                    mesh_bytes = json.dumps(mesh_list).encode()
                    mesh_base64 = base64.b64encode(mesh_bytes).decode('utf-8')
                except Exception as e:
                    print(f"[BVCS] Failed to encode mesh for {obj.name}: {e}")

            # Blob hash
            blob_hash = hashlib.sha256(json.dumps(json_data, sort_keys=True).encode()).hexdigest()

            objects_data.append({
                "object_name": obj.name,
                "object_type": obj.type,
                "json_data": json_data,
                "mesh_data": mesh_base64,
                "blob_hash": blob_hash
            })

        commit_data = {
            "branch_id": "default",  # adjust for your branch system
            "author_id": str(uuid4()),  # placeholder
            "commit_message": self.commit_message,
            "objects": objects_data
        }

        print("[BVCS] COMMIT DATA:", json.dumps(commit_data, indent=2))
        self.report({'INFO'}, "Commit prepared (Base64 mesh)")

        bpy.context.window_manager["bvcs_last_commit"] = commit_data
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

# ---------------- Push ----------------
class BVCS_OT_Push(bpy.types.Operator):
    bl_idname = "bvcs.push"
    bl_label = "Push Last Commit (Stub)"

    def execute(self, context):
        self.report({'INFO'}, "[STUB] Push created (stub).")
        print("[BVCS] BVCS_OT_Push called — STUB (no functionality).")
        return {'FINISHED'}

# ---------------- Pull ----------------
class BVCS_OT_PullProject(bpy.types.Operator):
    bl_idname = "bvcs.pull_project"
    bl_label = "Pull Project (Stub)"

    def execute(self, context):
        self.report({'INFO'}, "[STUB] Pull project not implemented yet.")
        print("[BVCS] STUB: Pull triggered")
        return {'FINISHED'}

# ---------------- Conflicts ----------------
class BVCS_OT_CheckConflicts(bpy.types.Operator):
    bl_idname = "bvcs.check_conflicts"
    bl_label = "Check Merge Conflicts (Stub)"

    def execute(self, context):
        self.report({'INFO'}, "[STUB] Conflict detection not implemented yet.")
        print("[BVCS] STUB: Conflict check triggered")
        return {'FINISHED'}

# ---------------- Panel ----------------
class BVCS_PT_Panel(bpy.types.Panel):
    bl_label = "BVCS"
    bl_idname = "BVCS_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'BVCS'

    def draw(self, context):
        layout = self.layout
        prefs = context.preferences.addons[BL_ID].preferences
        wm = get_bvcs_login_state()
        logged_in = wm.get("bvcs_logged_in", False)

        layout.label(text=f"API: {prefs.api_url}")
        status = "Logged In" if logged_in and prefs.auth_token else "Not Authenticated"
        layout.label(text=f"Status: {status}")

        if logged_in and prefs.auth_token:
            layout.operator("bvcs.create_project")
            layout.operator("bvcs.select_project")
            layout.operator("bvcs.logout")
        else:
            layout.operator("bvcs.login")

        if prefs.project_id:
            layout.label(text=f"Project: {prefs.project_id}")
            layout.operator("bvcs.stage_objects")
            layout.operator("bvcs.commit")
            layout.operator("bvcs.push")
            layout.operator("bvcs.pull_project")
            layout.operator("bvcs.check_conflicts")

# ---------------- Registration ----------------
classes = [
    BVCSAddonPreferences,
    BVCS_OT_Login,
    BVCS_OT_Logout,
    BVCS_OT_CreateProject,
    BVCS_OT_SelectProject,
    BVCS_OT_StageObjects,
    BVCS_OT_Commit,
    BVCS_OT_Push,
    BVCS_OT_PullProject,
    BVCS_OT_CheckConflicts,
    BVCS_PT_Panel
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()