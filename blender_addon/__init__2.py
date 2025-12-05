bl_info = {
    "name": "BVCS",
    "author": "Capstone Bots",
    "version": (0, 0, 14),
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
import logging
import os
from datetime import datetime, timezone

# Optional dependency
try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
    HAS_BOTO3 = True
except Exception:
    HAS_BOTO3 = False

BL_ID = "blender_vcs" 

# ---------------- Logger ----------------
logger = logging.getLogger("BVCS")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# ---------------- Preferences ----------------
class BVCSAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = BL_ID

    api_url: bpy.props.StringProperty(
        name="API URL",
        default="https://capstonebots-production.up.railway.app",
    )
    auth_token: bpy.props.StringProperty(
        name="JWT Token",
        default="",
    )
    project_id: bpy.props.StringProperty(
        name="Default Project ID",
        default="",
    )

    # S3 fields
    s3_access_key: bpy.props.StringProperty(
        name="S3 Access Key",
        default="",
    )
    s3_secret_key: bpy.props.StringProperty(
        name="S3 Secret Key",
        default="",
        subtype='PASSWORD'
    )
    s3_bucket: bpy.props.StringProperty(
        name="S3 Bucket",
        default="",
    )
    s3_endpoint: bpy.props.StringProperty(
        name="S3 Endpoint",
        default="",  # optional - e.g. https://s3.us-east-1.amazonaws.com
    )
    s3_region: bpy.props.StringProperty(
        name="S3 Region",
        default="us-east-1",
    )
    s3_secure: bpy.props.BoolProperty(
        name="S3 Secure (use https)",
        default=True,
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Server")
        layout.prop(self, "api_url")
        layout.prop(self, "auth_token")
        layout.prop(self, "project_id")

        layout.separator()
        layout.label(text="S3 Configuration (optional)")
        layout.prop(self, "s3_access_key")
        layout.prop(self, "s3_secret_key")
        layout.prop(self, "s3_bucket")
        layout.prop(self, "s3_endpoint")
        layout.prop(self, "s3_region")
        layout.prop(self, "s3_secure")
        row = layout.row()
        row.operator("bvcs.test_s3", text="Test S3 Connection")

# ---------------- Helpers ----------------
def get_prefs(context):
    prefs_container = context.preferences.addons.get(BL_ID)
    if not prefs_container:
        raise RuntimeError("BVCS preferences not found")
    return prefs_container.preferences

def get_bvcs_login_state():
    wm = bpy.context.window_manager
    if "bvcs_logged_in" not in wm:
        prefs = None
        try:
            prefs = get_prefs(bpy.context)
        except Exception:
            pass
        wm["bvcs_logged_in"] = bool(prefs and getattr(prefs, "auth_token", None))
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
    except Exception as e:
        logger.error(f"Failed to fetch logged-in user: {e}")
        return None

def make_s3_client(prefs):
    """
    Creates a boto3 S3 client using preferences or environment.
    Returns (client, error_msg). If client is None, error_msg explains why.
    """
    # prefer prefs values; fallback to env vars
    access_key = prefs.s3_access_key or os.environ.get("S3_ACCESS_KEY") or os.environ.get("AWS_ACCESS_KEY_ID")
    secret_key = prefs.s3_secret_key or os.environ.get("S3_SECRET_KEY") or os.environ.get("AWS_SECRET_ACCESS_KEY")
    bucket = prefs.s3_bucket or os.environ.get("S3_BUCKET")
    endpoint = prefs.s3_endpoint or os.environ.get("S3_ENDPOINT")
    region = prefs.s3_region or os.environ.get("S3_REGION", "us-east-1")
    secure = prefs.s3_secure

    if not HAS_BOTO3:
        return None, "boto3 is not installed in this Blender Python environment."

    if not access_key or not secret_key or not bucket:
        return None, "S3 credentials or bucket not configured in preferences or environment."

    session = boto3.session.Session()
    s3_client = session.client(
        service_name='s3',
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        endpoint_url=endpoint if endpoint else None,
        config=boto3.session.Config(signature_version='s3v4')) if hasattr(boto3, 'session') else None

    return {
        "client": s3_client,
        "bucket": bucket,
        "endpoint": endpoint,
        "region": region,
        "secure": secure
    }, None

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
                logger.info("Login successful")
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
        logger.info("User logged out")
        return {'FINISHED'}

# ---------------- Project Operators ----------------
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
                prefs.project_id = str(proj_id)
                self.report({'INFO'}, f"Project created: {self.project_name}")
                logger.info(f"Project created: {self.project_name} ({proj_id})")
            else:
                self.report({'WARNING'}, "Project created but ID not found")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to create project: {e}")
            logger.error(f"Project creation failed: {e}")
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
        items=lambda self, context: get_user_projects(context)
    )

    def execute(self, context):
        prefs = get_prefs(context)
        prefs.project_id = self.project_enum
        self.report({'INFO'}, f"Selected project {self.project_enum}")
        logger.info(f"Project selected: {self.project_enum}")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

def get_user_projects(context):
    prefs = get_prefs(context)
    headers = {"Authorization": f"Bearer {prefs.auth_token}"}
    try:
        resp = requests.get(f"{prefs.api_url}/api/projects", headers=headers, timeout=5)
        resp.raise_for_status()
        projects = resp.json()
        return [(str(p["project_id"]), p["name"], p.get("description", "")) for p in projects]
    except Exception as e:
        logger.error(f"Failed to fetch projects: {e}")
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
        logger.info(f"Staged objects: {BVCS_OT_StageObjects.staged_objects}")
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
            json_data = {"name": obj.name, "type": obj.type}
            mesh_base64 = None
            if obj.type == 'MESH':
                try:
                    mesh_list = [[v.co.x, v.co.y, v.co.z] for v in obj.data.vertices]
                    mesh_bytes = json.dumps(mesh_list).encode()
                    mesh_base64 = base64.b64encode(mesh_bytes).decode('utf-8')
                except Exception as e:
                    logger.error(f"Failed to encode mesh for {obj.name}: {e}")

            blob_hash = hashlib.sha256(json.dumps(json_data, sort_keys=True).encode()).hexdigest()
            objects_data.append({
                "object_name": obj.name,
                "object_type": obj.type,
                "json_data": json_data,
                "mesh_data": mesh_base64,
                "blob_hash": blob_hash
            })

        commit_data = {
            "branch_id": "default",
            "project_id": prefs.project_id,
            "author_id": str(uuid4()),
            "commit_message": self.commit_message,
            "objects": objects_data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # compute commit hash for filename
        commit_json = json.dumps(commit_data, sort_keys=True)
        commit_hash = hashlib.sha256(commit_json.encode()).hexdigest()

        context.window_manager["bvcs_last_commit"] = {
            "commit_hash": commit_hash,
            "commit_data": commit_data
        }
        self.report({'INFO'}, "Commit prepared")
        logger.info(f"Commit data prepared: {commit_hash}")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

# ---------------- S3 Test ----------------
class BVCS_OT_TestS3(bpy.types.Operator):
    bl_idname = "bvcs.test_s3"
    bl_label = "Test S3 Connection"

    def execute(self, context):
        prefs = get_prefs(context)
        s3_info, err = make_s3_client(prefs)
        if err:
            self.report({'ERROR'}, f"S3 error: {err}")
            logger.error(f"S3 test failed: {err}")
            return {'CANCELLED'}
        client = s3_info["client"]
        bucket = s3_info["bucket"]
        try:
            # attempt a head_bucket to check access
            client.head_bucket(Bucket=bucket)
            self.report({'INFO'}, "S3 connection OK")
            logger.info("S3 connection OK")
        except Exception as e:
            self.report({'ERROR'}, f"S3 connection failed: {e}")
            logger.error(f"S3 connection failed: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}

# ---------------- Push / Pull / Conflicts ----------------
class BVCS_OT_Push(bpy.types.Operator):
    bl_idname = "bvcs.push"
    bl_label = "Push Last Commit to S3"

    def execute(self, context):
        prefs = get_prefs(context)
        wm = context.window_manager
        last = wm.get("bvcs_last_commit")
        if not last:
            self.report({'ERROR'}, "No commit prepared to push")
            return {'CANCELLED'}
        s3_info, err = make_s3_client(prefs)
        if err:
            self.report({'ERROR'}, f"S3 error: {err}")
            logger.error(f"S3 push failed: {err}")
            return {'CANCELLED'}

        client = s3_info["client"]
        bucket = s3_info["bucket"]
        commit_hash = last["commit_hash"]
        commit_data = last["commit_data"]
        key = f"{prefs.project_id}/{commit_hash}.json"

        try:
            payload = json.dumps(commit_data, indent=2)
            client.put_object(Bucket=bucket, Key=key, Body=payload.encode('utf-8'))
            # optionally set metadata
            logger.info(f"Pushed commit {commit_hash} to s3://{bucket}/{key}")
            # store remote pointer
            wm["bvcs_last_pushed"] = {"key": key, "bucket": bucket, "pushed_at": datetime.now(timezone.utc).isoformat()}
            self.report({'INFO'}, f"Pushed commit to {bucket}/{key}")
        except Exception as e:
            logger.error(f"Failed to push commit to S3: {e}")
            self.report({'ERROR'}, f"Push failed: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}

class BVCS_OT_PullProject(bpy.types.Operator):
    bl_idname = "bvcs.pull_project"
    bl_label = "Pull Project from S3 (latest)"

    def execute(self, context):
        prefs = get_prefs(context)
        if not prefs.project_id:
            self.report({'ERROR'}, "No project selected")
            return {'CANCELLED'}
        s3_info, err = make_s3_client(prefs)
        if err:
            self.report({'ERROR'}, f"S3 error: {err}")
            logger.error(f"S3 pull failed: {err}")
            return {'CANCELLED'}
        client = s3_info["client"]
        bucket = s3_info["bucket"]
        prefix = f"{prefs.project_id}/"

        try:
            # list objects with the project prefix and pick the most recently LastModified
            resp = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
            items = resp.get("Contents") or []
            if not items:
                self.report({'WARNING'}, "No commits found in S3 for this project")
                return {'FINISHED'}
            # pick most recent by LastModified
            items_sorted = sorted(items, key=lambda i: i.get("LastModified") or i.get("LastModified", ""), reverse=True)
            latest = items_sorted[0]
            key = latest["Key"]
            obj = client.get_object(Bucket=bucket, Key=key)
            payload = obj["Body"].read().decode('utf-8')
            commit_data = json.loads(payload)
            context.window_manager["bvcs_last_pulled"] = {"key": key, "commit_data": commit_data}
            self.report({'INFO'}, f"Pulled {key}")
            logger.info(f"Pulled object {key} from s3://{bucket}")
        except Exception as e:
            logger.error(f"Failed to pull project from S3: {e}")
            self.report({'ERROR'}, f"Pull failed: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}

class BVCS_OT_CheckConflicts(bpy.types.Operator):
    bl_idname = "bvcs.check_conflicts"
    bl_label = "Check Merge Conflicts (Stub)"

    def execute(self, context):
        self.report({'INFO'}, "[STUB] Conflict check called")
        logger.info("Check conflicts operator called (stub)")
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
        try:
            prefs = get_prefs(context)
        except Exception:
            layout.label(text="BVCS preferences not found. Enable the add-on.")
            return

        wm = get_bvcs_login_state()
        logged_in = wm.get("bvcs_logged_in", False)

        layout.label(text=f"API: {prefs.api_url}")
        layout.label(text=f"Status: {'Logged In' if logged_in and prefs.auth_token else 'Not Authenticated'}")

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
            layout.separator()
            layout.label(text="S3:")
            layout.prop(prefs, "s3_bucket", text="Bucket")

# ---------------- Registration ----------------
classes = [
    BVCSAddonPreferences,
    BVCS_OT_Login,
    BVCS_OT_Logout,
    BVCS_OT_CreateProject,
    BVCS_OT_SelectProject,
    BVCS_OT_StageObjects,
    BVCS_OT_Commit,
    BVCS_OT_TestS3,
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
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

if __name__ == "__main__":
    register()