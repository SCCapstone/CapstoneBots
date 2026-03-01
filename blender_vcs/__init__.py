from collections import defaultdict

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
import importlib
from uuid import uuid4
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urlparse

ADDON_VENDOR_DIR = os.path.join(os.path.dirname(__file__), "_vendor")
if os.path.isdir(ADDON_VENDOR_DIR) and ADDON_VENDOR_DIR not in sys.path:
    sys.path.insert(0, ADDON_VENDOR_DIR)

HAS_BOTO3 = False
BOTO3_INSTALL_ATTEMPTED = False

def _try_import_boto3():
    global boto3, BotoCoreError, ClientError, BotocoreConfig, HAS_BOTO3
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
        from botocore.config import Config as BotocoreConfig
        HAS_BOTO3 = True
    except Exception:
        HAS_BOTO3 = False
    return HAS_BOTO3

def ensure_boto3_installed():
    """
    Ensure boto3 exists in Blender's Python environment.
    Installs into add-on local _vendor directory to avoid system-wide changes.
    """
    global BOTO3_INSTALL_ATTEMPTED

    if _try_import_boto3():
        return True, None

    if BOTO3_INSTALL_ATTEMPTED:
        return False, "boto3 is not available and automatic install already failed in this session."
    BOTO3_INSTALL_ATTEMPTED = True

    try:
        os.makedirs(ADDON_VENDOR_DIR, exist_ok=True)

        # Ensure pip exists in Blender Python, then install boto3 into _vendor.
        subprocess.run(
            [sys.executable, "-m", "ensurepip", "--upgrade"],
            capture_output=True,
            text=True,
            check=False
        )
        result = subprocess.run(
            [
                sys.executable, "-m", "pip", "install",
                "--disable-pip-version-check",
                "--target", ADDON_VENDOR_DIR,
                "boto3"
            ],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            if len(err) > 300:
                err = err[-300:]
            return False, f"Automatic boto3 install failed: {err or 'pip returned non-zero exit code'}"

        if ADDON_VENDOR_DIR not in sys.path:
            sys.path.insert(0, ADDON_VENDOR_DIR)
        importlib.invalidate_caches()
        if _try_import_boto3():
            logger.info("boto3 installed into add-on _vendor successfully.")
            return True, None
        return False, "boto3 install completed but import still failed."
    except Exception as e:
        return False, f"Automatic boto3 install failed: {e}"

_try_import_boto3()

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
        # default="http://localhost:8000/"
        default="https://blendercollab.pakshpatel.tech/capstone-deploy-backend"
    )
    frontend_signup_url: bpy.props.StringProperty(
        name="Frontend Sign Up URL",
        # default="http://localhost:3000/signup"
        default="https://blendercollab.pakshpatel.tech/signup"
        # add proper url before beta release
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
        default="",
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
        layout.prop(self, "frontend_signup_url")
        layout.prop(self, "auth_token")
        layout.prop(self, "project_id")

        layout.separator()
        layout.label(text="S3 Configuration (auto-fetched on login)")
        has_s3 = bool(self.s3_access_key and self.s3_secret_key and self.s3_bucket)
        if has_s3:
            layout.label(text="✓ S3 credentials configured", icon='CHECKMARK')
        else:
            layout.label(text="S3 credentials will be fetched when you log in", icon='INFO')
        box = layout.box()
        box.prop(self, "s3_access_key")
        box.prop(self, "s3_secret_key")
        box.prop(self, "s3_bucket")
        box.prop(self, "s3_endpoint")
        box.prop(self, "s3_region")
        box.prop(self, "s3_secure")
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
    if not getattr(prefs, "auth_token", None):
        logger.warning("Cannot fetch S3 config: not logged in")
        return
    headers = {"Authorization": f"Bearer {prefs.auth_token}"}
    try:
        resp = requests.get(f"{prefs.api_url}/api/auth/s3-config", headers=headers, timeout=5)
        resp.raise_for_status()
        s3_data = resp.json()
        prefs.s3_access_key = s3_data.get("access_key", "")
        prefs.s3_secret_key = s3_data.get("secret_key", "")
        prefs.s3_bucket = s3_data.get("bucket", "")
        prefs.s3_endpoint = s3_data.get("endpoint", "")
        prefs.s3_region = s3_data.get("region", "us-east-1")
        prefs.s3_secure = s3_data.get("secure", True)
        logger.info("S3 credentials fetched from backend successfully")
    except Exception as e:
        logger.warning(f"Failed to fetch S3 credentials from backend: {e}")

def make_s3_client(prefs):
    """
    Creates a boto3 S3 client using preferences or environment.
    Returns (client_info, error_msg). If client_info is None, error_msg explains why.
    """
    # prefer prefs values; fallback to env vars
    access_key = prefs.s3_access_key or os.environ.get("S3_ACCESS_KEY") or os.environ.get("AWS_ACCESS_KEY_ID")
    secret_key = prefs.s3_secret_key or os.environ.get("S3_SECRET_KEY") or os.environ.get("AWS_SECRET_ACCESS_KEY")
    bucket = prefs.s3_bucket or os.environ.get("S3_BUCKET")
    endpoint = prefs.s3_endpoint or os.environ.get("S3_ENDPOINT") or None
    region = prefs.s3_region or os.environ.get("S3_REGION", "us-east-1")
    secure = prefs.s3_secure

    if not HAS_BOTO3:
        ok, install_err = ensure_boto3_installed()
        if not ok:
            return None, install_err

    if not access_key or not secret_key or not bucket:
        return None, "S3 credentials or bucket not configured in preferences or environment."

    try:
        session = boto3.session.Session()
        # Use botocore Config for signature_version and retries
        botocore_conf = BotocoreConfig(signature_version='s3v4')
        s3_client = session.client(
            service_name='s3',
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=endpoint if endpoint else None,
            config=botocore_conf
        )
    except Exception as e:
        return None, f"Failed to create S3 client: {e}"

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
    
def upload_file_to_s3(local_file_path, bucket, s3_key_prefix, client):
    """
    Upload a single file to S3.
    local_file_path: path to the local file
    bucket: S3 bucket name
    s3_key_prefix: prefix/folder in the bucket (e.g. 'projectid_timestamp')
    client: boto3 s3 client
    """
    try:
        filename = os.path.basename(local_file_path)
        s3_key = os.path.join(s3_key_prefix, filename).replace("\\", "/")
        client.upload_file(local_file_path, bucket, s3_key)
        logger.info(f"Uploaded {local_file_path} to s3://{bucket}/{s3_key}")
        return s3_key  # return S3 key used
    except Exception as e:
        logger.error(f"Failed to upload file to S3: {e}")
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

class BVCS_OT_OpenSignupPage(bpy.types.Operator):
    bl_idname = "bvcs.open_signup"
    bl_label = "Sign Up"

    def execute(self, context):
        prefs = get_prefs(context)
        signup_url = (prefs.frontend_signup_url or "").strip()
        if not signup_url:
            self.report({'ERROR'}, "Frontend Sign Up URL is not configured")
            return {'CANCELLED'}
        parsed = urlparse(signup_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            self.report({'ERROR'}, "Sign Up URL must be a valid http:// or https:// URL")
            return {'CANCELLED'}

        try:
            webbrowser.open_new_tab(signup_url)
            self.report({'INFO'}, "Opened Sign Up page in browser")
            return {'FINISHED'}
        except Exception as e:
            logger.error(f"Failed to open signup page: {e}")
            self.report({'ERROR'}, f"Could not open browser: {e}")
            return {'CANCELLED'}

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
        items=lambda self, context: get_user_projects_for_enum(context)
    )

    def execute(self, context):
        if not self.project_enum or self.project_enum == "__NO_PROJECTS__":
            self.report({'ERROR'}, "No project selected")
            return {'CANCELLED'}
        prefs = get_prefs(context)
        prefs.project_id = self.project_enum
        _refresh_project_blend_file_cache(context, prefs)
        context.window_manager.bvcs_project_file = "NONE"
        context.window_manager["bvcs_last_synced_commit_hash"] = ""
        if "bvcs_push_conflict" in context.window_manager:
            del context.window_manager["bvcs_push_conflict"]
        if "bvcs_push_conflict_compare" in context.window_manager:
            del context.window_manager["bvcs_push_conflict_compare"]
        self.report({'INFO'}, f"Selected project {self.project_enum}")
        logger.info(f"Project selected: {self.project_enum}")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

def get_user_projects(context):
    prefs = get_prefs(context)
    if not prefs.auth_token:
        logger.warning("Cannot fetch projects: missing auth token.")
        return []

    headers = {"Authorization": f"Bearer {prefs.auth_token}"}
    try:
        api_base = prefs.api_url.rstrip("/")
        resp = requests.get(f"{api_base}/api/projects", headers=headers, timeout=10)
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, list):
            projects = payload
        elif isinstance(payload, dict):
            projects = payload.get("projects") or payload.get("items") or payload.get("data") or []
        else:
            projects = []

        enum_items = []
        for p in projects:
            if not isinstance(p, dict):
                continue
            project_id = p.get("project_id") or p.get("id")
            if not project_id:
                continue
            project_name = p.get("name") or f"Project {project_id}"
            project_description = p.get("description") or ""
            enum_items.append((str(project_id), str(project_name), str(project_description)))
        return enum_items
    except Exception as e:
        logger.error(f"Failed to fetch projects: {e}")
        return []


def get_user_projects_for_enum(context):
    projects = get_user_projects(context)
    if projects:
        return projects
    return [
        (
            "__NO_PROJECTS__",
            "No projects found",
            "Check login token, API URL, and backend status",
        )
    ]


def get_api_base(prefs):
    return prefs.api_url.rstrip("/")


def get_auth_headers(prefs):
    return {"Authorization": f"Bearer {prefs.auth_token}"}


def _enum_conflict_items(self, context):
    items = getattr(BVCS_OT_CheckConflicts, "_cached_conflict_items", None)
    if not items:
        return [("NONE", "No conflicts", "No conflicts available")]
    return items


PROJECT_BLEND_FILE_ITEMS = [("NONE", "No pushed .blend files", "Push a file to this project first")]
PROJECT_BLEND_FILE_MAP = {}
PROJECT_BLEND_FILE_PROJECT_ID = ""

# Temp subdirectory names used for downloaded .blend files.
_BVCS_TEMP_SUBDIRS = ("bvcs_backend_open", "bvcs_conflict_compare")

# Max age (in seconds) before a temp file is considered stale and eligible for cleanup.
_BVCS_TEMP_MAX_AGE_SECS = 24 * 60 * 60  # 24 hours

import time as _time

def _cleanup_bvcs_temp_dirs(max_age_secs=_BVCS_TEMP_MAX_AGE_SECS, force=False):
    """Remove stale BVCS temp files.

    By default only files older than *max_age_secs* are deleted so that
    files currently in use are not disrupted.  When *force* is ``True``
    every file (and the directory itself) is removed regardless of age.
    """
    now = _time.time()
    for subdir in _BVCS_TEMP_SUBDIRS:
        dir_path = os.path.join(tempfile.gettempdir(), subdir)
        if not os.path.isdir(dir_path):
            continue
        for fname in os.listdir(dir_path):
            fpath = os.path.join(dir_path, fname)
            try:
                if not os.path.isfile(fpath):
                    continue
                if force or (now - os.path.getmtime(fpath)) > max_age_secs:
                    os.remove(fpath)
                    logger.debug(f"Cleaned up temp file: {fpath}")
            except Exception:
                logger.debug(f"Could not remove temp file: {fpath}")
        # Remove the directory itself if it is now empty.
        try:
            if not os.listdir(dir_path):
                os.rmdir(dir_path)
        except Exception:
            pass


def _refresh_project_blend_file_cache(context, prefs):
    global PROJECT_BLEND_FILE_ITEMS, PROJECT_BLEND_FILE_MAP, PROJECT_BLEND_FILE_PROJECT_ID

    PROJECT_BLEND_FILE_MAP = {}
    PROJECT_BLEND_FILE_ITEMS = [("NONE", "No pushed .blend files", "Push a file to this project first")]
    PROJECT_BLEND_FILE_PROJECT_ID = str(getattr(prefs, "project_id", "") or "")

    if not getattr(prefs, "project_id", None) or not getattr(prefs, "auth_token", None):
        return

    headers = get_auth_headers(prefs)
    api_base = get_api_base(prefs)
    project_id = prefs.project_id

    try:
        commits_resp = requests.get(
            f"{api_base}/api/projects/{project_id}/commits",
            params={"branch_name": "main"},
            headers=headers,
            timeout=10,
        )
        commits_resp.raise_for_status()
        commits = commits_resp.json()
        if not isinstance(commits, list) or not commits:
            return

        # Limit to 10 most recent commits to avoid excessive HTTP requests.
        recent_commits = [c for c in commits[:10] if c.get("commit_id")]

        def _fetch_commit_objects(commit):
            """Fetch objects for a single commit (runs in a thread)."""
            commit_id = commit.get("commit_id")
            resp = requests.get(
                f"{api_base}/api/projects/{project_id}/commits/{commit_id}/objects",
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            return commit, resp.json()

        # Fetch commit objects concurrently (up to 4 at a time).
        commit_results = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(_fetch_commit_objects, c): c
                for c in recent_commits
            }
            for future in as_completed(futures):
                try:
                    commit_results.append(future.result())
                except Exception:
                    logger.debug(f"Skipping commit {futures[future].get('commit_id')}: request failed")

        # Sort results to preserve original commit order (most recent first).
        commit_order = {c.get("commit_id"): i for i, c in enumerate(recent_commits)}
        commit_results.sort(key=lambda pair: commit_order.get(pair[0].get("commit_id"), 0))

        seen_paths = set()
        found_files = []

        for commit, commit_objects in commit_results:
            if not isinstance(commit_objects, list):
                continue

            for obj in commit_objects:
                if not isinstance(obj, dict):
                    continue
                if obj.get("object_type") != "BLEND_FILE":
                    continue
                s3_path = obj.get("json_data_path")
                if not isinstance(s3_path, str) or not s3_path.startswith("s3://"):
                    continue
                if s3_path in seen_paths:
                    continue

                seen_paths.add(s3_path)
                found_files.append({
                    "s3_path": s3_path,
                    "object_name": obj.get("object_name") or os.path.basename(s3_path),
                    "commit_id": commit.get("commit_id"),
                    "commit_hash": commit.get("commit_hash"),
                    "commit_message": commit.get("commit_message"),
                })

        if not found_files:
            return

        PROJECT_BLEND_FILE_ITEMS = [("NONE", "Select a project file...", "Choose a pushed .blend file to open")]
        PROJECT_BLEND_FILE_MAP = {}
        for idx, file_info in enumerate(found_files):
            enum_id = f"FILE_{idx}"
            short_hash = str(file_info.get("commit_hash", ""))[:8]
            label = f"{file_info['object_name']} [{short_hash}]"
            desc = file_info.get("s3_path", "")
            PROJECT_BLEND_FILE_ITEMS.append((enum_id, label, desc))
            PROJECT_BLEND_FILE_MAP[enum_id] = file_info
    except Exception as e:
        logger.error(f"Failed to load project file list: {e}")


def _enum_project_blend_files(self, context):
    try:
        prefs = get_prefs(context)
    except Exception:
        return [("NONE", "No project selected", "Select a project first")]

    project_id = str(getattr(prefs, "project_id", "") or "")
    if not project_id:
        return [("NONE", "No project selected", "Select a project first")]

    if project_id != PROJECT_BLEND_FILE_PROJECT_ID:
        _refresh_project_blend_file_cache(context, prefs)

    return PROJECT_BLEND_FILE_ITEMS


def _parse_s3_uri(s3_uri: str):
    if not isinstance(s3_uri, str) or not s3_uri.startswith("s3://"):
        raise ValueError("Invalid S3 URI")
    path = s3_uri[5:]
    first_slash = path.find("/")
    if first_slash <= 0 or first_slash == len(path) - 1:
        raise ValueError("S3 URI must include bucket and key")
    return path[:first_slash], path[first_slash + 1:]


def _get_latest_remote_blend_file_info(prefs):
    headers = get_auth_headers(prefs)
    api_base = get_api_base(prefs)
    project_id = prefs.project_id

    commits_resp = requests.get(
        f"{api_base}/api/projects/{project_id}/commits",
        params={"branch_name": "main"},
        headers=headers,
        timeout=10,
    )
    commits_resp.raise_for_status()
    commits = commits_resp.json()
    if not isinstance(commits, list) or not commits:
        return None

    latest_commit = commits[0]
    commit_id = latest_commit.get("commit_id")
    if not commit_id:
        return None

    objects_resp = requests.get(
        f"{api_base}/api/projects/{project_id}/commits/{commit_id}/objects",
        headers=headers,
        timeout=10,
    )
    objects_resp.raise_for_status()
    commit_objects = objects_resp.json()
    if not isinstance(commit_objects, list):
        return None

    blend_obj = next(
        (
            obj for obj in commit_objects
            if isinstance(obj, dict)
            and obj.get("object_type") == "BLEND_FILE"
            and isinstance(obj.get("json_data_path"), str)
            and obj.get("json_data_path").startswith("s3://")
        ),
        None,
    )
    if not blend_obj:
        return None

    # include author information so we can make user-aware conflict decisions
    return {
        "s3_path": blend_obj.get("json_data_path"),
        "object_name": blend_obj.get("object_name") or os.path.basename(blend_obj.get("json_data_path")),
        "commit_id": latest_commit.get("commit_id"),
        "commit_hash": latest_commit.get("commit_hash"),
        "commit_message": latest_commit.get("commit_message"),
        "author_id": latest_commit.get("author_id"),
        # some API responses may include a username for convenience
        "author_username": latest_commit.get("author_username"),
    }


# ---------- remote chronology helpers ----------

def _get_latest_remote_commit_hash(prefs):
    """Return the hash string of the tip of main branch on the remote (or "").

    This simply delegates to ``_get_latest_remote_blend_file_info`` and pulls
    the commit_hash field.  It is used by synchronization logic to decide if
    the local state is still based on the same remote commit.
    """
    try:
        info = _get_latest_remote_blend_file_info(prefs) or {}
        return str(info.get("commit_hash") or "")
    except Exception:
        return ""


def _remote_ahead_of_sync(wm, prefs):
    """Return (ahead, remote_hash, synced_hash).

    ``ahead`` indicates whether the remote head is non-empty _and_ differs
    from whatever we last recorded in the window manager (via a pull or a
    successful push).
    """
    synced = _get_last_synced_commit_hash(wm)
    remote = _get_latest_remote_commit_hash(prefs)
    return (bool(remote and remote != synced), remote, synced)


def _get_last_synced_commit_hash(wm):
    hash_from_wm = wm.get("bvcs_last_synced_commit_hash")
    if hash_from_wm:
        return str(hash_from_wm)

    last_pulled = wm.get("bvcs_last_pulled") or {}
    if isinstance(last_pulled, dict) and last_pulled.get("commit_hash"):
        return str(last_pulled.get("commit_hash"))

    last_pushed = wm.get("bvcs_last_pushed") or {}
    if isinstance(last_pushed, dict) and last_pushed.get("commit_hash"):
        return str(last_pushed.get("commit_hash"))

    return ""


def _open_project_file_info(context, prefs, file_info: dict):
    if not isinstance(file_info, dict):
        raise RuntimeError("Invalid file info")

    # download the blend file; we defer writing to the window manager until
    # after the file has been opened, because opening a new file resets the
    # window manager and would otherwise wipe out any properties we set.
    s3_uri = file_info.get("s3_path")
    local_path = _download_project_file_info(prefs, file_info, temp_subdir="bvcs_backend_open")

    # open the downloaded file, blocking until the new file is active.
    bpy.ops.wm.open_mainfile(filepath=local_path)

    # now that the new blend is loaded, update sync state on the current wm
    wm = bpy.context.window_manager
    wm["bvcs_last_pulled"] = {
        "commit_id": file_info.get("commit_id"),
        "commit_hash": file_info.get("commit_hash"),
        "commit_message": file_info.get("commit_message"),
        "pulled_at": datetime.now(timezone.utc).isoformat(),
    }
    # record the hash so we know what the remote head was when we pulled.
    wm["bvcs_last_synced_commit_hash"] = file_info.get("commit_hash") or ""
    if "bvcs_push_conflict" in wm:
        del wm["bvcs_push_conflict"]
    if "bvcs_push_conflict_compare" in wm:
        del wm["bvcs_push_conflict_compare"]

    # If a local pending commit exists, rebase its base hash to the pulled/opened commit.
    # This prevents stale conflict state after pulling latest before pushing.
    pending = wm.get("bvcs_pending_commit")
    if isinstance(pending, dict):
        pending["base_commit_hash"] = file_info.get("commit_hash") or ""
        wm["bvcs_pending_commit"] = pending


def _open_selected_project_file(context, prefs, selected_id: str):
    file_info = PROJECT_BLEND_FILE_MAP.get(selected_id)
    if not file_info:
        raise RuntimeError("Selected file is no longer available")
    _open_project_file_info(context, prefs, file_info)


def _download_project_file_info(prefs, file_info: dict, temp_subdir: str = "bvcs_backend_open"):
    if not isinstance(file_info, dict):
        raise RuntimeError("Invalid file info")
    s3_uri = file_info.get("s3_path")
    bucket, key = _parse_s3_uri(s3_uri)

    s3_info, err = make_s3_client(prefs)
    if err:
        raise RuntimeError(f"S3 error: {err}")
    client = s3_info["client"]

    file_name = file_info.get("object_name") or os.path.basename(key)
    if not str(file_name).lower().endswith(".blend"):
        file_name = f"{file_name}.blend"

    temp_dir = os.path.join(tempfile.gettempdir(), temp_subdir)
    os.makedirs(temp_dir, exist_ok=True)
    local_path = os.path.join(temp_dir, str(file_name))
    client.download_file(bucket, key, local_path)
    return local_path


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

            wm = context.window_manager
            base_commit_hash = _get_last_synced_commit_hash(wm)
            
            # Store commit info locally (will be synced to DB when pushed)
            context.window_manager["bvcs_pending_commit"] = {
                "message": self.commit_message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "file_path": local_file_path,
                "base_commit_hash": base_commit_hash,
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

        # Force Blender preferences UI to refresh so new values are visible
        try:
            context.preferences.is_dirty = True
        except Exception:
            # non-fatal; just continue
            pass

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

        try:
            latest_remote = _get_latest_remote_blend_file_info(prefs)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to check remote state: {e}")
            return {'CANCELLED'}

        # determine whether to perform a merge-style conflict check. if the
        # last remote commit was authored by the same user who is currently
        # pushing we treat the situation as safe (e.g. user pushing from a
        # second machine) and allow a fast-forward.
        user = get_logged_in_user(prefs)
        remote_author = (latest_remote or {}).get("author_id")
        if user and remote_author and user.get("user_id") == remote_author:
            logger.info("Remote head authored by same user, skipping merge conflict check")
        else:
            remote_commit_hash = (latest_remote or {}).get("commit_hash") or ""
            base_commit_hash = str(pending_commit.get("base_commit_hash") or "")
            if remote_commit_hash:
                # If there is a remote history but this local commit has no base,
                # the user likely hasn't pulled yet. Block the push and instruct them
                # to pull before creating their first commit.
                if not base_commit_hash:
                    wm["bvcs_push_conflict"] = {
                        "base_commit_hash": base_commit_hash,
                        "remote_commit_hash": remote_commit_hash,
                        "remote_commit_id": (latest_remote or {}).get("commit_id"),
                        "remote_commit_message": (latest_remote or {}).get("commit_message"),
                        "remote_s3_path": (latest_remote or {}).get("s3_path"),
                        "remote_object_name": (latest_remote or {}).get("object_name"),
                        "local_file_path": pending_commit.get("file_path") or local_file_path,
                        "detected_at": datetime.now(timezone.utc).isoformat(),
                    }
                    self.report(
                        {'ERROR'},
                        "Push blocked: remote history exists but your commit has no base. Pull the latest version before creating your first commit."
                    )
                    return {'CANCELLED'}
                # Normal conflict: local base differs from current remote head.
                if base_commit_hash != remote_commit_hash:
                    wm["bvcs_push_conflict"] = {
                        "base_commit_hash": base_commit_hash,
                        "remote_commit_hash": remote_commit_hash,
                        "remote_commit_id": (latest_remote or {}).get("commit_id"),
                        "remote_commit_message": (latest_remote or {}).get("commit_message"),
                        "remote_s3_path": (latest_remote or {}).get("s3_path"),
                        "remote_object_name": (latest_remote or {}).get("object_name"),
                        "local_file_path": pending_commit.get("file_path") or local_file_path,
                        "detected_at": datetime.now(timezone.utc).isoformat(),
                    }
                    self.report(
                        {'ERROR'},
                        "Push blocked: remote changed since your last pull. Pull latest, merge, then recommit before pushing."
                    )
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
            # Step 1: Upload only the .blend file to S3
            self.report({'INFO'}, "Uploading .blend to S3...")
            s3_key = upload_file_to_s3(local_file_path, bucket, s3_folder_name, client)
            if not s3_key:
                self.report({'ERROR'}, "Failed to upload .blend file to S3")
                return {'CANCELLED'}
            # Build the s3 path used in DB (s3://bucket/<s3_key>)
            s3_blend_path = f"s3://{bucket}/{s3_key}"
            
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
            wm["bvcs_last_synced_commit_hash"] = commit_data.get("commit_hash") or ""
            if "bvcs_push_conflict" in wm:
                del wm["bvcs_push_conflict"]
            if "bvcs_push_conflict_compare" in wm:
                del wm["bvcs_push_conflict_compare"]
            
            # Clear pending commit
            if "bvcs_pending_commit" in wm:
                del wm["bvcs_pending_commit"]

            _refresh_project_blend_file_cache(context, prefs)
            wm.bvcs_project_file = "NONE"
            
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
    bl_label = "Pull Latest from Remote"

    def execute(self, context):
        prefs = get_prefs(context)
        if not prefs.project_id:
            self.report({'ERROR'}, "No project selected")
            return {'CANCELLED'}

        try:
            latest_remote = _get_latest_remote_blend_file_info(prefs)
            if not latest_remote:
                self.report({'ERROR'}, "No remote .blend file found for this project")
                return {'CANCELLED'}

            _open_project_file_info(context, prefs, latest_remote)
            _refresh_project_blend_file_cache(context, prefs)
            context.window_manager.bvcs_project_file = "NONE"

            short_hash = str(latest_remote.get("commit_hash", ""))[:8]
            self.report({'INFO'}, f"Pulled latest remote commit {short_hash}")
            logger.info(f"Pulled latest remote commit {latest_remote.get('commit_hash')}")

        except Exception as e:
            logger.error(f"Failed to pull latest remote file: {e}")
            self.report({'ERROR'}, f"Pull failed: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}

class BVCS_OT_LoadProjectFile(bpy.types.Operator):
    bl_idname = "bvcs.load_project_file"
    bl_label = "Load Selected File"

    def execute(self, context):
        prefs = get_prefs(context)
        if not prefs.project_id:
            self.report({'ERROR'}, "No project selected")
            return {'CANCELLED'}
        if not prefs.auth_token:
            self.report({'ERROR'}, "Not logged in")
            return {'CANCELLED'}

        selected = context.window_manager.bvcs_project_file
        if not selected or selected == "NONE":
            self.report({'ERROR'}, "Select a project file first")
            return {'CANCELLED'}

        try:
            _open_selected_project_file(context, prefs, selected)
            self.report({'INFO'}, "Loaded selected file")
            return {'FINISHED'}
        except Exception as e:
            logger.error(f"Failed to load selected project file: {e}")
            self.report({'ERROR'}, f"Load failed: {e}")
            return {'CANCELLED'}

class BVCS_OT_ResolveMergeConflict(bpy.types.Operator):
    bl_idname = "bvcs.resolve_merge_conflict"
    bl_label = "Resolve Merge Conflict"

    resolution: bpy.props.EnumProperty(
        name="Action",
        description="Choose how to resolve this file conflict",
        items=[
            ("KEEP_MAIN", "Keep Main As-Is", "Keep remote/main version and discard local pending push"),
            ("PUSH_LOCAL", "Push My Version", "Keep your current file and allow push to main"),
        ],
        default="PUSH_LOCAL"
    )

    def invoke(self, context, event):
        prefs = get_prefs(context)
        wm = context.window_manager
        conflict = wm.get("bvcs_push_conflict")
        if not conflict:
            self.report({'ERROR'}, "No push conflict to resolve")
            return {'CANCELLED'}

        remote_s3_path = conflict.get("remote_s3_path")
        if not remote_s3_path:
            self.report({'ERROR'}, "Conflict missing remote file path")
            return {'CANCELLED'}

        remote_info = {
            "s3_path": remote_s3_path,
            "object_name": conflict.get("remote_object_name") or "remote_conflict.blend",
            "commit_id": conflict.get("remote_commit_id"),
            "commit_hash": conflict.get("remote_commit_hash"),
            "commit_message": conflict.get("remote_commit_message"),
        }

        try:
            remote_local_path = _download_project_file_info(
                prefs, remote_info, temp_subdir="bvcs_conflict_compare"
            )
            local_path = (
                conflict.get("local_file_path")
                or (wm.get("bvcs_pending_commit") or {}).get("file_path")
                or bpy.context.blend_data.filepath
            )

            wm["bvcs_push_conflict_compare"] = {
                "local_path": local_path or "",
                "remote_path": remote_local_path,
                "remote_commit_hash": conflict.get("remote_commit_hash"),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

            # Open remote version in a separate Blender instance for side-by-side comparison.
            blender_bin = bpy.app.binary_path
            if not blender_bin or not os.path.isfile(blender_bin):
                logger.error(f"Blender binary path is invalid or not found: {blender_bin!r}")
                self.report({'ERROR'}, "Cannot open remote file: Blender binary not found.")
                return {'CANCELLED'}

            if not remote_local_path or not os.path.isfile(remote_local_path):
                logger.error(f"Remote conflict file path is invalid or not found: {remote_local_path!r}")
                self.report({'ERROR'}, "Cannot open remote file: downloaded file not found.")
                return {'CANCELLED'}

            subprocess.Popen([blender_bin, remote_local_path])
            return context.window_manager.invoke_props_dialog(self, width=700)
        except Exception as e:
            logger.error(f"Failed to prepare merge conflict resolution: {e}")
            self.report({'ERROR'}, f"Resolve setup failed: {e}")
            return {'CANCELLED'}

    def execute(self, context):
        wm = context.window_manager
        conflict = wm.get("bvcs_push_conflict")
        if not conflict:
            self.report({'ERROR'}, "No push conflict to resolve")
            return {'CANCELLED'}

        remote_hash = str(conflict.get("remote_commit_hash") or "")
        if not remote_hash:
            self.report({'ERROR'}, "Conflict missing remote commit hash")
            return {'CANCELLED'}

        if self.resolution == "KEEP_MAIN":
            if "bvcs_pending_commit" in wm:
                del wm["bvcs_pending_commit"]
            wm["bvcs_last_synced_commit_hash"] = remote_hash
            if "bvcs_push_conflict_compare" in wm:
                del wm["bvcs_push_conflict_compare"]
            if "bvcs_push_conflict" in wm:
                del wm["bvcs_push_conflict"]
            self.report({'INFO'}, "Main kept as-is. Local pending push was discarded.")
            return {'FINISHED'}

        pending = wm.get("bvcs_pending_commit")
        if not pending:
            self.report({'ERROR'}, "No pending local commit to push")
            return {'CANCELLED'}

        pending["base_commit_hash"] = remote_hash
        if pending.get("message") and not str(pending.get("message")).startswith("Merge:"):
            pending["message"] = f"Merge: {pending['message']}"
        wm["bvcs_pending_commit"] = pending
        if "bvcs_push_conflict_compare" in wm:
            del wm["bvcs_push_conflict_compare"]
        if "bvcs_push_conflict" in wm:
            del wm["bvcs_push_conflict"]
        self.report(
            {'WARNING'},
            "Conflict resolved: your local version will be pushed. Any remote changes not manually merged into your file will be overwritten."
        )
        return {'FINISHED'}

    def draw(self, context):
        wm = context.window_manager
        compare = wm.get("bvcs_push_conflict_compare", {})
        layout = self.layout
        layout.label(text="Remote and local files are opened/prepared for comparison.", icon='INFO')
        layout.label(text=f"Local: {compare.get('local_path', '')}")
        layout.label(text=f"Remote: {compare.get('remote_path', '')}")
        layout.separator()
        layout.label(text="WARNING: 'Push My Version' does NOT auto-merge remote changes.", icon='ERROR')
        layout.label(text="Manually copy any needed changes from the remote file before pushing.")
        layout.separator()
        layout.prop(self, "resolution")

class BVCS_OT_CheckConflicts(bpy.types.Operator):
    bl_idname = "bvcs.check_conflicts"
    bl_label = "Check Merge Conflicts"

    _cached_conflicts = []
    _cached_conflict_items = []
    _cached_conflict_previews = {}

    conflict_id: bpy.props.EnumProperty(
        name="Conflict",
        description="Choose a conflict to resolve",
        items=_enum_conflict_items
    )
    resolution: bpy.props.EnumProperty(
        name="Resolution",
        description="Choose which version to keep",
        items=[
            ("LOCAL", "Keep Local", "Keep object version from target branch HEAD"),
            ("INCOMING", "Keep Incoming", "Keep object version from source commit"),
        ],
        default="LOCAL"
    )

    @staticmethod
    def _find_object(commit_objects, object_name):
        for obj in commit_objects:
            if obj.get("object_name") == object_name:
                return obj
        return None

    @staticmethod
    def _summarize_object(obj):
        if not obj:
            return "missing"
        blob = str(obj.get("blob_hash", ""))[:10]
        json_path = obj.get("json_data_path", "")
        if json_path:
            return f"blob={blob} path={os.path.basename(json_path)}"
        return f"blob={blob}"

    def _fetch_conflicts(self, prefs):
        api_base = get_api_base(prefs)
        headers = get_auth_headers(prefs)
        resp = requests.get(
            f"{api_base}/api/projects/{prefs.project_id}/conflicts",
            headers=headers,
            timeout=10
        )
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, list):
            return []
        return payload

    def execute(self, context):
        prefs = get_prefs(context)
        if not prefs.project_id:
            self.report({'ERROR'}, "No project selected")
            return {'CANCELLED'}
        if not prefs.auth_token:
            self.report({'ERROR'}, "Not logged in")
            return {'CANCELLED'}
        if not self.conflict_id:
            self.report({'ERROR'}, "No conflict selected")
            return {'CANCELLED'}

        conflict = next((c for c in self.__class__._cached_conflicts if str(c.get("conflict_id")) == self.conflict_id), None)
        if not conflict:
            self.report({'ERROR'}, "Selected conflict was not found")
            return {'CANCELLED'}

        try:
            api_base = get_api_base(prefs)
            headers = get_auth_headers(prefs)
            object_name = conflict.get("object_name")
            source_commit_id = conflict.get("source_commit_id")
            target_branch_id = conflict.get("target_branch_id")
            conflict_id = conflict.get("conflict_id")
            if not object_name or not source_commit_id or not target_branch_id or not conflict_id:
                self.report({'ERROR'}, "Conflict payload is missing required fields")
                return {'CANCELLED'}

            # Source side (incoming): object state from source commit.
            source_resp = requests.get(
                f"{api_base}/api/projects/{prefs.project_id}/commits/{source_commit_id}/objects",
                headers=headers,
                timeout=10
            )
            source_resp.raise_for_status()
            source_objects = source_resp.json()
            source_obj = self._find_object(source_objects, object_name)

            # Local side: object state from target branch HEAD commit.
            branches_resp = requests.get(
                f"{api_base}/api/projects/{prefs.project_id}/branches",
                headers=headers,
                timeout=10
            )
            branches_resp.raise_for_status()
            branches = branches_resp.json()
            target_branch = next((b for b in branches if str(b.get("branch_id")) == str(target_branch_id)), None)
            if not target_branch:
                self.report({'ERROR'}, "Target branch for this conflict was not found")
                return {'CANCELLED'}

            local_obj = None
            head_commit_id = target_branch.get("head_commit_id")
            if head_commit_id:
                local_resp = requests.get(
                    f"{api_base}/api/projects/{prefs.project_id}/commits/{head_commit_id}/objects",
                    headers=headers,
                    timeout=10
                )
                local_resp.raise_for_status()
                local_objects = local_resp.json()
                local_obj = self._find_object(local_objects, object_name)

            if self.resolution == "LOCAL":
                chosen_obj = local_obj
            else:
                chosen_obj = source_obj

            if not chosen_obj:
                self.report(
                    {'ERROR'},
                    f"Chosen version is missing for '{object_name}'. Try the other resolution option."
                )
                return {'CANCELLED'}

            commit_payload = {
                "branch_id": str(target_branch_id),
                "commit_message": f"Resolve conflict: {object_name} ({self.resolution})",
                "objects": [{
                    "object_name": chosen_obj.get("object_name"),
                    "object_type": chosen_obj.get("object_type"),
                    "json_data_path": chosen_obj.get("json_data_path"),
                    "mesh_data_path": chosen_obj.get("mesh_data_path"),
                    "parent_object_id": chosen_obj.get("parent_object_id"),
                    "blob_hash": chosen_obj.get("blob_hash"),
                }]
            }

            create_resp = requests.post(
                f"{api_base}/api/projects/{prefs.project_id}/commits",
                json=commit_payload,
                headers=headers,
                timeout=15
            )
            create_resp.raise_for_status()
            created_commit = create_resp.json()

            resolve_resp = requests.put(
                f"{api_base}/api/projects/{prefs.project_id}/conflicts/{conflict_id}",
                headers=headers,
                timeout=10
            )
            resolve_resp.raise_for_status()

            commit_hash = created_commit.get("commit_hash", "")[:8]
            self.report({'INFO'}, f"Conflict resolved for '{object_name}' via {self.resolution} (commit {commit_hash}...)")
            logger.info(f"Resolved conflict {conflict_id} for object '{object_name}' using {self.resolution}")
            return {'FINISHED'}
        except Exception as e:
            logger.error(f"Conflict resolution failed: {e}")
            self.report({'ERROR'}, f"Conflict resolution failed: {e}")
            return {'CANCELLED'}

    def invoke(self, context, event):
        prefs = get_prefs(context)
        if not prefs.project_id:
            self.report({'ERROR'}, "No project selected")
            return {'CANCELLED'}
        if not prefs.auth_token:
            self.report({'ERROR'}, "Not logged in")
            return {'CANCELLED'}

        try:
            conflicts = self._fetch_conflicts(prefs)
            unresolved = [c for c in conflicts if not c.get("resolved", False)]
            if not unresolved:
                self.report({'INFO'}, "No unresolved merge conflicts")
                self.__class__._cached_conflicts = []
                self.__class__._cached_conflict_items = []
                return {'CANCELLED'}

            self.__class__._cached_conflicts = unresolved
            self.__class__._cached_conflict_previews = {}
            self.__class__._cached_conflict_items = [
                (
                    str(c.get("conflict_id")),
                    f"{c.get('object_name', 'Unknown Object')} [{c.get('conflict_type', 'UNKNOWN')}]",
                    f"Source commit: {c.get('source_commit_id')} | Target branch: {c.get('target_branch_id')}"
                )
                for c in unresolved
                if c.get("conflict_id")
            ]

            api_base = get_api_base(prefs)
            headers = get_auth_headers(prefs)
            branches_resp = requests.get(
                f"{api_base}/api/projects/{prefs.project_id}/branches",
                headers=headers,
                timeout=10
            )
            branches_resp.raise_for_status()
            branches = branches_resp.json()

            for c in unresolved:
                cid = str(c.get("conflict_id", ""))
                if not cid:
                    continue
                object_name = c.get("object_name")
                source_commit_id = c.get("source_commit_id")
                target_branch_id = c.get("target_branch_id")

                source_obj = None
                local_obj = None

                if source_commit_id:
                    source_resp = requests.get(
                        f"{api_base}/api/projects/{prefs.project_id}/commits/{source_commit_id}/objects",
                        headers=headers,
                        timeout=10
                    )
                    source_resp.raise_for_status()
                    source_objects = source_resp.json()
                    source_obj = self._find_object(source_objects, object_name)

                target_branch = next((b for b in branches if str(b.get("branch_id")) == str(target_branch_id)), None)
                if target_branch and target_branch.get("head_commit_id"):
                    local_resp = requests.get(
                        f"{api_base}/api/projects/{prefs.project_id}/commits/{target_branch.get('head_commit_id')}/objects",
                        headers=headers,
                        timeout=10
                    )
                    local_resp.raise_for_status()
                    local_objects = local_resp.json()
                    local_obj = self._find_object(local_objects, object_name)

                self.__class__._cached_conflict_previews[cid] = {
                    "local": self._summarize_object(local_obj),
                    "incoming": self._summarize_object(source_obj),
                }

            if not self.__class__._cached_conflict_items:
                self.report({'ERROR'}, "Conflicts returned but no valid conflict IDs were found")
                return {'CANCELLED'}

            self.conflict_id = self.__class__._cached_conflict_items[0][0]
            return context.window_manager.invoke_props_dialog(self, width=680)
        except Exception as e:
            logger.error(f"Failed to fetch merge conflicts: {e}")
            self.report({'ERROR'}, f"Failed to fetch merge conflicts: {e}")
            return {'CANCELLED'}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "conflict_id")
        layout.prop(self, "resolution")
        preview = self.__class__._cached_conflict_previews.get(self.conflict_id, {})
        layout.label(text=f"Local: {preview.get('local', 'unknown')}")
        layout.label(text=f"Incoming: {preview.get('incoming', 'unknown')}")
        layout.label(text="Local = target branch HEAD, Incoming = source commit", icon='INFO')

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
            layout.operator("bvcs.open_signup")
            layout.operator("bvcs.login")

        if prefs.project_id:
            layout.label(text=f"Project: {prefs.project_id}")
            layout.operator("bvcs.stage_objects")
            layout.operator("bvcs.commit")
            layout.operator("bvcs.push")
            layout.operator("bvcs.pull_project")
            row = layout.row(align=True)
            row.prop(context.window_manager, "bvcs_project_file", text="Project Files")
            row.operator("bvcs.load_project_file", text="Load File")
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

            if "bvcs_push_conflict" in wm:
                conflict = wm["bvcs_push_conflict"]
                layout.separator()
                layout.label(text="Push Conflict Detected", icon='ERROR')
                layout.label(text=f"  Remote: {str(conflict.get('remote_commit_hash', ''))[:8]}...")
                layout.label(text=f"  Base: {str(conflict.get('base_commit_hash', ''))[:8]}...")
                layout.operator("bvcs.resolve_merge_conflict", text="Resolve Merge Conflict")
            
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
    BVCS_OT_OpenSignupPage,
    BVCS_OT_Logout,
    BVCS_OT_CreateProject,
    BVCS_OT_SelectProject,
    BVCS_OT_StageObjects,
    BVCS_OT_Commit,
    BVCS_OT_TestS3,
    BVCS_OT_RefreshS3,
    BVCS_OT_Push,
    BVCS_OT_PullProject,
    BVCS_OT_LoadProjectFile,
    BVCS_OT_ResolveMergeConflict,
    BVCS_OT_CheckConflicts,
    BVCS_PT_Panel
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.bvcs_project_file = bpy.props.EnumProperty(
        name="Project Files",
        description="Select a pushed .blend file",
        items=_enum_project_blend_files,
    )
    # Remove stale temp .blend files from previous sessions (older than 24 h).
    try:
        _cleanup_bvcs_temp_dirs()
    except Exception:
        logger.debug("Temp cleanup on register skipped due to error")

def unregister():
    # Force-remove all BVCS temp files when the addon is disabled.
    try:
        _cleanup_bvcs_temp_dirs(force=True)
    except Exception:
        logger.debug("Temp cleanup on unregister skipped due to error")
    if hasattr(bpy.types.WindowManager, "bvcs_project_file"):
        del bpy.types.WindowManager.bvcs_project_file
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

if __name__ == "__main__":
    register()
