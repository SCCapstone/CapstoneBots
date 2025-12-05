bl_info = {
    "name": "BVCS",
    "author": "Capstone Bots",
    "version": (0, 0, 15),
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
import shutil
import tempfile
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
        row.operator("bvcs.refresh_s3", text="Refresh S3 Credentials")

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

def fetch_user_s3_credentials(prefs):
    """Fetch S3 credentials from backend for the current user and fill in preferences."""
    headers = {"Authorization": f"Bearer {prefs.auth_token}"}
    try:
        resp = requests.get(f"{prefs.api_url}/api/user/s3", headers=headers, timeout=5)
        resp.raise_for_status()
        s3_data = resp.json()
        prefs.s3_access_key = s3_data.get("access_key", "")
        prefs.s3_secret_key = s3_data.get("secret_key", "")
        prefs.s3_bucket = s3_data.get("bucket", "")
        prefs.s3_endpoint = s3_data.get("endpoint", "")
        prefs.s3_region = s3_data.get("region", "us-east-1")
        prefs.s3_secure = s3_data.get("secure", True)
        logger.info("S3 credentials fetched from backend")
    except Exception as e:
        logger.warning(f"Failed to fetch S3 credentials: {e}")

def make_s3_client(prefs):
    """
    Creates a boto3 S3 client using preferences or environment.
    Returns (client_info, error_msg). If client_info is None, error_msg explains why.
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
        config=boto3.session.Config(signature_version='s3v4'))

    return {
        "client": s3_client,
        "bucket": bucket,
        "endpoint": endpoint,
        "region": region,
        "secure": secure
    }, None

def gather_dependencies(blend_file_path):
    """Gather all dependencies of the blend file and copy them to a new folder."""
    base_dir = os.path.dirname(blend_file_path)
    package_dir_name = "package_" + os.path.basename(blend_file_path).split('.')[0]
    package_dir = os.path.join(tempfile.gettempdir(), package_dir_name)

    # Create a new directory to store the blend file and dependencies
    os.makedirs(package_dir, exist_ok=True)

    # Copy the blend file while preserving the relative path
    shutil.copy(blend_file_path, package_dir)

    # List to store paths of dependencies
    dependencies = set()

    # Add all linked libraries
    for library in bpy.data.libraries:
        dependencies.add(bpy.path.abspath(library.filepath))

    # Add all image filepaths (textures)
    for image in bpy.data.images:
        if image.filepath:
            dependencies.add(bpy.path.abspath(image.filepath))

    # Copy all dependencies to the new directory, preserving the relative paths
    for dep in dependencies:
        try:
            rel_path = os.path.relpath(dep, base_dir)
            dep_dest = os.path.join(package_dir, rel_path)
            os.makedirs(os.path.dirname(dep_dest), exist_ok=True)
            shutil.copy(dep, dep_dest)
        except Exception as e:
            logger.warning(f"Could not copy dependency {dep}: {e}")

    return package_dir

def upload_folder_to_s3(folder, bucket, s3_key, client):
    """Upload a folder to AWS S3 without zipping."""
    try:
        for root, dirs, files in os.walk(folder):
            for file in files:
                local_file_path = os.path.join(root, file)
                s3_file_path = os.path.relpath(local_file_path, folder)
                s3_file_path = os.path.join(s3_key, s3_file_path).replace("\\", "/")
                client.upload_file(local_file_path, bucket, s3_file_path)
                logger.info(f"Uploaded {local_file_path} to {s3_file_path} in {bucket}")
        logger.info(f"Uploaded {folder} to {s3_key} in {bucket}")
        return True
    except Exception as e:
        logger.error(f"Failed to upload folder to S3: {e}")
        return False

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
                # fetch S3 credentials for this user automatically
                fetch_user_s3_credentials(prefs)
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
    bl_label = "Commit Changes"

    commit_message: bpy.props.StringProperty(name="Commit Message", default="Updated objects")

    def execute(self, context):
        prefs = get_prefs(context)
        if not prefs.project_id:
            self.report({'ERROR'}, "No project selected")
            return {'CANCELLED'}

        # Save the current blend file
        local_file_path = bpy.context.blend_data.filepath
        if not local_file_path:
            self.report({'ERROR'}, "Please save your blend file first")
            return {'CANCELLED'}
        
        try:
            # Save the file to capture all current changes
            bpy.ops.wm.save_mainfile()
            
            # Store commit info locally (will be synced to DB when pushed)
            context.window_manager["bvcs_pending_commit"] = {
                "message": self.commit_message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "file_path": local_file_path
            }
            
            self.report({'INFO'}, f"Committed locally: {self.commit_message}")
            logger.info(f"Local commit created: {self.commit_message}")
            
        except Exception as e:
            self.report({'ERROR'}, f"Commit failed: {e}")
            logger.error(f"Commit failed: {e}")
            return {'CANCELLED'}
            
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

# ---------------- S3 Test / Refresh ----------------
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
            client.head_bucket(Bucket=bucket)
            self.report({'INFO'}, "S3 connection OK")
            logger.info("S3 connection OK")
        except Exception as e:
            self.report({'ERROR'}, f"S3 connection failed: {e}")
            logger.error(f"S3 connection failed: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}

class BVCS_OT_RefreshS3(bpy.types.Operator):
    bl_idname = "bvcs.refresh_s3"
    bl_label = "Refresh S3 Credentials"

    def execute(self, context):
        prefs = get_prefs(context)
        if not prefs.auth_token:
            self.report({'ERROR'}, "Not logged in")
            return {'CANCELLED'}
        fetch_user_s3_credentials(prefs)
        self.report({'INFO'}, "S3 credentials refreshed")
        return {'FINISHED'}

# ---------------- Push / Pull / Conflicts ----------------
class BVCS_OT_Push(bpy.types.Operator):
    bl_idname = "bvcs.push"
    bl_label = "Push to S3 and Database"

    def execute(self, context):
        prefs = get_prefs(context)
        wm = context.window_manager
        local_file_path = bpy.context.blend_data.filepath
        
        if not local_file_path:
            self.report({'ERROR'}, "Please save your blend file before pushing")
            return {'CANCELLED'}
        
        if not prefs.project_id:
            self.report({'ERROR'}, "No project selected")
            return {'CANCELLED'}
        
        # Get pending commit info
        pending_commit = wm.get("bvcs_pending_commit")
        if not pending_commit:
            self.report({'ERROR'}, "No commit to push. Please commit first.")
            return {'CANCELLED'}
            
        s3_info, err = make_s3_client(prefs)
        if err:
            self.report({'ERROR'}, f"S3 error: {err}")
            logger.error(f"S3 push failed: {err}")
            return {'CANCELLED'}

        client = s3_info["client"]
        bucket = s3_info["bucket"]
        
        # Create a unique folder name based on project_id and timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        s3_folder_name = f"{prefs.project_id}_{timestamp}"
        
        try:
            # Step 1: Upload .blend file and dependencies to S3
            self.report({'INFO'}, "Gathering dependencies...")
            package_dir = gather_dependencies(local_file_path)
            
            self.report({'INFO'}, "Uploading to S3...")
            success = upload_folder_to_s3(package_dir, bucket, s3_folder_name, client)
            
            # Clean up: remove the temporary package directory after upload
            shutil.rmtree(package_dir)
            
            if not success:
                self.report({'ERROR'}, "Failed to upload to S3")
                return {'CANCELLED'}
            
            # Step 2: Get current user for author_id
            user = get_logged_in_user(prefs)
            if not user:
                self.report({'ERROR'}, "Cannot get logged-in user")
                return {'CANCELLED'}
            
            # Step 3: Get main branch ID
            headers = {"Authorization": f"Bearer {prefs.auth_token}"}
            branches_resp = requests.get(f"{prefs.api_url}/api/projects/{prefs.project_id}/branches", 
                                         headers=headers, timeout=10)
            branches_resp.raise_for_status()
            branches = branches_resp.json()
            main_branch = next((b for b in branches if b.get("branch_name") == "main"), None)
            if not main_branch:
                self.report({'ERROR'}, "Main branch not found")
                return {'CANCELLED'}
            
            # Step 4: Build S3 paths for objects
            blend_filename = os.path.basename(local_file_path)
            s3_blend_path = f"s3://{bucket}/{s3_folder_name}/{blend_filename}"
            
            # Create object metadata - one entry for the main .blend file
            objects_data = [{
                "object_name": blend_filename,
                "object_type": "BLEND_FILE",
                "json_data_path": s3_blend_path,
                "mesh_data_path": None,
                "parent_object_id": None,
                "blob_hash": hashlib.sha256(s3_blend_path.encode()).hexdigest()
            }]
            
            # Step 5: Create commit in database
            commit_payload = {
                "branch_id": main_branch["branch_id"],
                "author_id": user["user_id"],
                "commit_message": pending_commit["message"],
                "objects": objects_data
            }
            
            self.report({'INFO'}, "Creating commit in database...")
            commit_resp = requests.post(
                f"{prefs.api_url}/api/projects/{prefs.project_id}/commits",
                json=commit_payload,
                headers=headers,
                timeout=10
            )
            commit_resp.raise_for_status()
            commit_data = commit_resp.json()
            
            # Success! Update UI state
            wm["bvcs_last_pushed"] = {
                "folder": s3_folder_name,
                "bucket": bucket,
                "commit_id": commit_data.get("commit_id"),
                "commit_hash": commit_data.get("commit_hash"),
                "pushed_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Clear pending commit
            if "bvcs_pending_commit" in wm:
                del wm["bvcs_pending_commit"]
            
            logger.info(f"Pushed to s3://{bucket}/{s3_folder_name} and DB commit {commit_data.get('commit_hash')}")
            self.report({'INFO'}, f"Successfully pushed to S3 and database!")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create commit in database: {e}")
            self.report({'ERROR'}, f"Database error: {e}")
            return {'CANCELLED'}
        except Exception as e:
            logger.error(f"Failed to push: {e}")
            self.report({'ERROR'}, f"Push failed: {e}")
            return {'CANCELLED'}
            
        return {'FINISHED'}

class BVCS_OT_PullProject(bpy.types.Operator):
    bl_idname = "bvcs.pull_project"
    bl_label = "Pull Latest from Database and S3"

    def execute(self, context):
        prefs = get_prefs(context)
        if not prefs.project_id:
            self.report({'ERROR'}, "No project selected")
            return {'CANCELLED'}
        
        try:
            # Step 1: Get latest commit from database
            headers = {"Authorization": f"Bearer {prefs.auth_token}"}
            self.report({'INFO'}, "Fetching commit history...")
            commits_resp = requests.get(
                f"{prefs.api_url}/api/projects/{prefs.project_id}/commits",
                headers=headers,
                timeout=10
            )
            commits_resp.raise_for_status()
            commits = commits_resp.json()
            
            if not commits:
                self.report({'ERROR'}, "No commits found for this project")
                return {'CANCELLED'}
            
            # Get the most recent commit
            latest_commit = commits[0]
            commit_id = latest_commit.get("commit_id")
            
            # Step 2: Get objects from this commit
            self.report({'INFO'}, "Fetching commit objects...")
            objects_resp = requests.get(
                f"{prefs.api_url}/api/projects/{prefs.project_id}/commits/{commit_id}/objects",
                headers=headers,
                timeout=10
            )
            objects_resp.raise_for_status()
            objects = objects_resp.json()
            
            if not objects:
                self.report({'ERROR'}, "No objects found in commit")
                return {'CANCELLED'}
            
            # Step 3: Download .blend file from S3
            s3_info, err = make_s3_client(prefs)
            if err:
                self.report({'ERROR'}, f"S3 error: {err}")
                return {'CANCELLED'}
            
            client = s3_info["client"]
            
            # Find the main .blend file object
            blend_obj = next((obj for obj in objects if obj.get("object_type") == "BLEND_FILE"), None)
            if not blend_obj:
                self.report({'ERROR'}, "No .blend file found in commit")
                return {'CANCELLED'}
            
            # Parse S3 path (format: s3://bucket/path/to/file)
            s3_path = blend_obj.get("json_data_path")
            if not s3_path or not s3_path.startswith("s3://"):
                self.report({'ERROR'}, "Invalid S3 path in commit")
                return {'CANCELLED'}
            
            # Extract bucket and key from s3:// URL
            s3_parts = s3_path.replace("s3://", "").split("/", 1)
            if len(s3_parts) != 2:
                self.report({'ERROR'}, "Could not parse S3 path")
                return {'CANCELLED'}
            
            bucket, key = s3_parts
            
            # Download the file
            self.report({'INFO'}, f"Downloading from S3...")
            temp_dir = os.path.join(tempfile.gettempdir(), "bvcs_pull")
            os.makedirs(temp_dir, exist_ok=True)
            local_path = os.path.join(temp_dir, os.path.basename(key))
            
            client.download_file(bucket, key, local_path)
            
            # Step 4: Open the downloaded file in Blender
            self.report({'INFO'}, "Opening file...")
            bpy.ops.wm.open_mainfile(filepath=local_path)
            
            context.window_manager["bvcs_last_pulled"] = {
                "commit_id": commit_id,
                "commit_hash": latest_commit.get("commit_hash"),
                "commit_message": latest_commit.get("commit_message"),
                "s3_path": s3_path,
                "pulled_at": datetime.now(timezone.utc).isoformat()
            }
            
            logger.info(f"Pulled commit {latest_commit.get('commit_hash')} from database and S3")
            self.report({'INFO'}, f"Successfully pulled: {latest_commit.get('commit_message')}")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to pull from database: {e}")
            self.report({'ERROR'}, f"Database error: {e}")
            return {'CANCELLED'}
        except Exception as e:
            logger.error(f"Failed to pull: {e}")
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
            layout.label(text="S3 Config:")
            layout.prop(prefs, "s3_bucket", text="Bucket")
            
            # Show pending commit (waiting to be pushed)
            wm = context.window_manager
            if "bvcs_pending_commit" in wm:
                layout.separator()
                layout.label(text="Pending Commit:", icon='INFO')
                pending = wm["bvcs_pending_commit"]
                layout.label(text=f"  {pending.get('message', 'N/A')}", icon='FILE_TICK')
                layout.label(text="  (Click Push to sync)")
            
            # Show last push info if available
            if "bvcs_last_pushed" in wm:
                layout.separator()
                layout.label(text="Last Push:")
                last_push = wm["bvcs_last_pushed"]
                layout.label(text=f"  Commit: {last_push.get('commit_hash', 'N/A')[:8]}...", icon='CHECKMARK')
                
            # Show last pull info if available
            if "bvcs_last_pulled" in wm:
                layout.separator()
                layout.label(text="Last Pull:")
                last_pull = wm["bvcs_last_pulled"]
                layout.label(text=f"  {last_pull.get('commit_message', 'N/A')}", icon='IMPORT')

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
    BVCS_OT_RefreshS3,
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