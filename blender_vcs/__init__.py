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

if "bpy" in locals():
    # If the add-on is reloaded, ensure submodules are reloaded too
    from . import object_serialization, push_pull, diff, staging, merge
    importlib.reload(object_serialization)
    importlib.reload(push_pull)
    importlib.reload(diff)
    importlib.reload(staging)
    importlib.reload(merge)
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urlparse

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

    def draw(self, context):
        layout = self.layout
        layout.label(text="Server")
        layout.prop(self, "api_url")
        layout.prop(self, "frontend_signup_url")
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
        prefs = None
        try:
            prefs = get_prefs(bpy.context)
        except Exception:
            pass
        wm["bvcs_logged_in"] = bool(prefs and getattr(prefs, "auth_token", None))
    return wm


def _get_active_branch_name(wm):
    """Return the currently active branch name (default 'main')."""
    return str(wm.get("bvcs_active_branch_name") or "main")


def _get_active_branch_id(wm):
    """Return the currently active branch ID (empty string if not set)."""
    return str(wm.get("bvcs_active_branch_id") or "")


def _set_active_branch(wm, branch_id, branch_name):
    """Set the active branch in window manager state."""
    wm["bvcs_active_branch_id"] = str(branch_id)
    wm["bvcs_active_branch_name"] = str(branch_name)


def _fetch_branches_list(prefs):
    """Fetch branches for the current project. Returns list of dicts."""
    headers = get_auth_headers(prefs)
    api_base = get_api_base(prefs)
    project_id = prefs.project_id
    if not project_id:
        return []
    try:
        resp = requests.get(
            f"{api_base}/api/projects/{project_id}/branches",
            headers=headers, timeout=10,
        )
        resp.raise_for_status()
        branches = resp.json()
        return branches if isinstance(branches, list) else []
    except Exception as e:
        logger.error(f"Failed to fetch branches: {e}")
        return []


def _ensure_active_branch(wm, prefs):
    """Ensure we have a valid active branch set for the current project.

    The cached branch_id can be stale across project switches (e.g. the
    previous project was deleted), so always verify it exists in the
    current project's branch list before trusting it.
    """
    branches = _fetch_branches_list(prefs)
    if not branches:
        return
    cached_id = _get_active_branch_id(wm)
    if cached_id and any(b.get("branch_id") == cached_id for b in branches):
        return
    main = next((b for b in branches if b.get("branch_name") == "main"), branches[0])
    _set_active_branch(wm, main["branch_id"], main["branch_name"])

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
        resp = requests.get(f"{get_api_base(prefs)}/api/auth/me", headers=headers, timeout=5)
        resp.raise_for_status()
        user = resp.json()
        return normalize_user_dict(user)
    except Exception as e:
        logger.error(f"Failed to fetch logged-in user: {e}")
        return None

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

# ---------------- Token Refresh ----------------
# Refresh interval: 50 minutes (token lifetime defaults to 60 min)
_TOKEN_REFRESH_INTERVAL = 50 * 60  # seconds

def _refresh_token():
    """Periodically refresh the JWT token. Registered with bpy.app.timers."""
    try:
        prefs_container = bpy.context.preferences.addons.get(BL_ID)
        if not prefs_container:
            return None  # stop timer — addon unregistered
        prefs = prefs_container.preferences
        token = getattr(prefs, "auth_token", None)
        if not token:
            return None  # stop timer — logged out

        resp = requests.post(
            f"{get_api_base(prefs)}/api/auth/refresh",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            new_token = resp.json().get("access_token")
            if new_token:
                prefs.auth_token = new_token
                logger.info("Token refreshed successfully")
        else:
            logger.warning(f"Token refresh failed (HTTP {resp.status_code})")
    except Exception as e:
        logger.warning(f"Token refresh error: {e}")
    return _TOKEN_REFRESH_INTERVAL  # schedule next refresh


def _start_token_refresh_timer():
    """Start the periodic token refresh timer if not already running."""
    if not bpy.app.timers.is_registered(_refresh_token):
        bpy.app.timers.register(_refresh_token, first_interval=_TOKEN_REFRESH_INTERVAL, persistent=True)


def _stop_token_refresh_timer():
    """Stop the periodic token refresh timer."""
    if bpy.app.timers.is_registered(_refresh_token):
        bpy.app.timers.unregister(_refresh_token)

# ---------------- Operators ----------------
class BVCS_OT_Login(bpy.types.Operator):
    bl_idname = "bvcs.login"
    bl_label = "Login to BVCS"

    email: bpy.props.StringProperty(name="Email")
    password: bpy.props.StringProperty(name="Password", subtype='PASSWORD')

    def execute(self, context):
        prefs = get_prefs(context)
        url = f"{get_api_base(prefs)}/api/auth/login"
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
                # Start periodic token refresh
                _start_token_refresh_timer()
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
        _stop_token_refresh_timer()
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
            resp = requests.post(f"{get_api_base(prefs)}/api/projects", json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            project = resp.json()
            proj_id = project.get("project_id") or project.get("id")
            if proj_id:
                prefs.project_id = str(proj_id)
                # Mirror SelectProject initialization so the new project is
                # immediately usable without requiring "Open Existing Project".
                wm = context.window_manager
                _refresh_project_blend_file_cache(context, prefs)
                wm.bvcs_project_file = "NONE"
                wm["bvcs_last_synced_commit_hash"] = ""
                if "bvcs_push_conflict" in wm:
                    del wm["bvcs_push_conflict"]
                if "bvcs_push_conflict_compare" in wm:
                    del wm["bvcs_push_conflict_compare"]
                wm["bvcs_active_branch_id"] = ""
                wm["bvcs_active_branch_name"] = "main"
                _ensure_active_branch(wm, prefs)
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
        # Initialize active branch to "main" for the new project
        context.window_manager["bvcs_active_branch_id"] = ""
        context.window_manager["bvcs_active_branch_name"] = "main"
        _ensure_active_branch(context.window_manager, prefs)
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
        api_base = get_api_base(prefs)
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
    url = prefs.api_url.rstrip("/")
    # Auto-correct HTTPS→HTTP for localhost connections (local dev never uses SSL)
    if url.startswith("https://localhost") or url.startswith("https://127.0.0.1"):
        url = "http://" + url[len("https://"):]
        logger.warning(f"Auto-corrected HTTPS to HTTP for local dev: {url}")
    return url


def get_auth_headers(prefs):
    return {"Authorization": f"Bearer {prefs.auth_token}"}


PROJECT_BLEND_FILE_ITEMS = [("NONE", "No commits found", "Push objects to this project first")]
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
    """Refresh the commit history dropdown for the 'Load Commit' feature.

    Lists recent commits on the active branch so users can checkout any
    previous commit at the object level.
    """
    global PROJECT_BLEND_FILE_ITEMS, PROJECT_BLEND_FILE_MAP, PROJECT_BLEND_FILE_PROJECT_ID

    PROJECT_BLEND_FILE_MAP = {}
    PROJECT_BLEND_FILE_ITEMS = [("NONE", "No commits found", "Push objects to this project first")]
    PROJECT_BLEND_FILE_PROJECT_ID = str(getattr(prefs, "project_id", "") or "")

    if not getattr(prefs, "project_id", None) or not getattr(prefs, "auth_token", None):
        return

    headers = get_auth_headers(prefs)
    api_base = get_api_base(prefs)
    project_id = prefs.project_id

    try:
        commits_resp = requests.get(
            f"{api_base}/api/projects/{project_id}/commits",
            params={"branch_name": _get_active_branch_name(bpy.context.window_manager)},
            headers=headers,
            timeout=10,
        )
        commits_resp.raise_for_status()
        commits = commits_resp.json()
        if not isinstance(commits, list) or not commits:
            return

        # Limit to 20 most recent commits
        recent_commits = [c for c in commits[:20] if c.get("commit_id")]
        if not recent_commits:
            return

        PROJECT_BLEND_FILE_ITEMS = [("NONE", "Select a commit to load...", "Choose a commit to reconstruct the scene from")]
        PROJECT_BLEND_FILE_MAP = {}
        for idx, commit in enumerate(recent_commits):
            enum_id = f"COMMIT_{idx}"
            short_hash = str(commit.get("commit_hash", ""))[:8]
            msg = str(commit.get("commit_message", ""))[:40]
            branch_name = str(commit.get("branch_name", ""))
            label = f"[{short_hash}] {msg}"
            desc = f"Commit {short_hash} on {branch_name}" if branch_name else f"Commit {short_hash}"
            PROJECT_BLEND_FILE_ITEMS.append((enum_id, label, desc))
            PROJECT_BLEND_FILE_MAP[enum_id] = {
                "commit_id": commit.get("commit_id"),
                "commit_hash": commit.get("commit_hash"),
                "commit_message": commit.get("commit_message"),
                "branch_name": branch_name,
            }
    except Exception as e:
        logger.error(f"Failed to load commit list: {e}")


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


def _validate_presigned_url(url):
    if not isinstance(url, str) or not url:
        raise ValueError("Presigned URL is empty")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"Rejected presigned URL with unsupported scheme: {parsed.scheme!r}")
    return url


def _get_latest_remote_blend_file_info(prefs):
    headers = get_auth_headers(prefs)
    api_base = get_api_base(prefs)
    project_id = prefs.project_id

    commits_resp = requests.get(
        f"{api_base}/api/projects/{project_id}/commits",
        params={"branch_name": _get_active_branch_name(bpy.context.window_manager)},
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
    """Return the hash string of the tip of the active branch on the remote (or "").

    Directly queries the commits API for the latest commit on the active branch.
    """
    try:
        headers = get_auth_headers(prefs)
        api_base = get_api_base(prefs)
        project_id = prefs.project_id
        if not project_id:
            return ""

        resp = requests.get(
            f"{api_base}/api/projects/{project_id}/commits",
            params={"branch_name": _get_active_branch_name(bpy.context.window_manager)},
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        commits = resp.json()
        if not isinstance(commits, list) or not commits:
            return ""
        return str(commits[0].get("commit_hash") or "")
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
    if not isinstance(s3_uri, str) or not s3_uri:
        raise RuntimeError("Missing S3 path in file info")

    # Derive a reasonable local filename from the s3 key (used for temp file name only).
    try:
        _, key = _parse_s3_uri(s3_uri)
    except ValueError:
        key = s3_uri
    # Strip any path components the backend might have included — we only want a
    # bare filename to join with our temp directory.
    raw_name = file_info.get("object_name") or os.path.basename(key)
    file_name = os.path.basename(str(raw_name).replace("\\", "/"))
    if not file_name or file_name in (".", ".."):
        file_name = "download.blend"
    if not file_name.lower().endswith(".blend"):
        file_name = f"{file_name}.blend"

    # Ask the backend for a short-lived presigned download URL. The backend verifies
    # project membership and validates the path prefix — clients no longer hold S3 keys.
    project_id = (file_info.get("project_id") or getattr(prefs, "project_id", "") or "").strip()
    if not project_id:
        raise RuntimeError("Project ID is required to download project files")

    api_base = get_api_base(prefs)
    headers = get_auth_headers(prefs)
    try:
        resp = requests.get(
            f"{api_base}/api/projects/{project_id}/files/download",
            params={"path": s3_uri},
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        url = (resp.json() or {}).get("url")
    except Exception as e:
        raise RuntimeError(f"Failed to get download URL: {e}")
    if not url:
        raise RuntimeError("Backend did not return a download URL")
    try:
        _validate_presigned_url(url)
    except ValueError as e:
        raise RuntimeError(str(e))

    temp_dir = os.path.join(tempfile.gettempdir(), temp_subdir)
    os.makedirs(temp_dir, exist_ok=True)
    local_path = os.path.join(temp_dir, file_name)
    # Defense in depth: ensure the resolved path is still inside temp_dir.
    temp_root = os.path.abspath(temp_dir)
    if os.path.commonpath([temp_root, os.path.abspath(local_path)]) != temp_root:
        raise RuntimeError("Refusing to write outside temp directory")

    # Stream to a .part file and atomically rename on success so a failed
    # download cannot leave a truncated .blend that later gets opened.
    partial_path = local_path + ".part"
    try:
        with requests.get(url, stream=True, timeout=120, allow_redirects=False) as dl:
            dl.raise_for_status()
            with open(partial_path, "wb") as fh:
                for chunk in dl.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        fh.write(chunk)
        os.replace(partial_path, local_path)
    except Exception as e:
        try:
            if os.path.exists(partial_path):
                os.remove(partial_path)
        except OSError:
            pass
        raise RuntimeError(f"Failed to download blend file: {e}")
    return local_path


# ---------------- Object-Level Imports ----------------
from blender_vcs.object_serialization import (
    serialize_object_metadata,
    serialize_mesh_data,
    compute_object_hash,
    deserialize_mesh_data,
    reconstruct_object_from_json,
    reconstruct_scene,
    clear_scene,
)
from blender_vcs.staging import StagingArea
from blender_vcs.diff import compute_scene_diff, ObjectStatus
from blender_vcs.merge import compute_object_diff, ConflictType, MergePlan
from blender_vcs.push_pull import (
    prepare_push_objects,
    build_commit_objects_list,
    prepare_pull_data,
    build_commit_objects_hash_map,
    MESH_TYPES,
)

# Global staging area instance
_staging_area = StagingArea()


def _get_parent_commit_objects(prefs) -> dict:
    """Fetch objects from the parent commit (branch HEAD).

    Returns mapping of object_name → {blob_hash, json_data_path, mesh_data_path}.
    """
    headers = get_auth_headers(prefs)
    api_base = get_api_base(prefs)
    project_id = prefs.project_id

    try:
        commits_resp = requests.get(
            f"{api_base}/api/projects/{project_id}/commits",
            params={"branch_name": _get_active_branch_name(bpy.context.window_manager)},
            headers=headers,
            timeout=10,
        )
        commits_resp.raise_for_status()
        commits = commits_resp.json()
        if not isinstance(commits, list) or not commits:
            return {}

        latest_commit = commits[0]
        commit_id = latest_commit.get("commit_id")
        if not commit_id:
            return {}

        objects_resp = requests.get(
            f"{api_base}/api/projects/{project_id}/commits/{commit_id}/objects",
            headers=headers,
            timeout=10,
        )
        objects_resp.raise_for_status()
        commit_objects = objects_resp.json()
        if not isinstance(commit_objects, list):
            return {}

        result = {}
        for obj in commit_objects:
            if not isinstance(obj, dict):
                continue
            name = obj.get("object_name")
            if name:
                result[name] = {
                    "blob_hash": obj.get("blob_hash"),
                    "json_data_path": obj.get("json_data_path"),
                    "mesh_data_path": obj.get("mesh_data_path"),
                    "object_type": obj.get("object_type"),
                    "object_id": obj.get("object_id"),
                }
        return result
    except Exception as e:
        logger.error(f"Failed to fetch parent commit objects: {e}")
        return {}


def _get_commit_objects_by_hash(prefs, commit_hash: str) -> dict:
    """Fetch objects from a commit identified by its hash.

    Returns mapping of object_name → blob_hash (string).
    Falls back to empty dict on any error.
    """
    if not commit_hash:
        return {}
    headers = get_auth_headers(prefs)
    api_base = get_api_base(prefs)
    project_id = prefs.project_id
    try:
        resp = requests.get(
            f"{api_base}/api/projects/{project_id}/commits/by-hash/{commit_hash}/objects",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        objects_list = resp.json()
        if not isinstance(objects_list, list):
            return {}
        return {
            obj.get("object_name"): obj.get("blob_hash", "")
            for obj in objects_list
            if isinstance(obj, dict) and obj.get("object_name")
        }
    except Exception as e:
        logger.warning(f"Failed to fetch commit objects by hash '{commit_hash[:8]}': {e}")
        return {}


def _get_commit_objects_full_by_hash(prefs, commit_hash: str) -> dict:
    """Fetch full object data from a commit identified by its hash.

    Returns mapping of object_name → {blob_hash, json_data_path, mesh_data_path, object_type}.
    """
    if not commit_hash:
        return {}
    headers = get_auth_headers(prefs)
    api_base = get_api_base(prefs)
    project_id = prefs.project_id
    try:
        resp = requests.get(
            f"{api_base}/api/projects/{project_id}/commits/by-hash/{commit_hash}/objects",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        objects_list = resp.json()
        if not isinstance(objects_list, list):
            return {}
        result = {}
        for obj in objects_list:
            if not isinstance(obj, dict):
                continue
            name = obj.get("object_name")
            if name:
                result[name] = {
                    "blob_hash": obj.get("blob_hash"),
                    "json_data_path": obj.get("json_data_path"),
                    "mesh_data_path": obj.get("mesh_data_path"),
                    "object_type": obj.get("object_type"),
                    "object_id": obj.get("object_id"),
                }
        return result
    except Exception as e:
        logger.warning(f"Failed to fetch full commit objects by hash '{commit_hash[:8]}': {e}")
        return {}


def _download_remote_object(prefs, obj_info: dict):
    """Download a single object's metadata JSON and optional mesh binary from S3.

    Args:
        prefs: Addon preferences with auth/API config.
        obj_info: Dict with json_data_path, mesh_data_path, object_name keys.

    Returns:
        (metadata_dict, mesh_bytes_or_None) or raises on failure.
    """
    headers = get_auth_headers(prefs)
    api_base = get_api_base(prefs)
    project_id = prefs.project_id

    json_path = obj_info.get("json_data_path")
    if not json_path:
        raise RuntimeError(f"No json_data_path for object '{obj_info.get('object_name')}'")

    # Download JSON metadata
    url_resp = requests.get(
        f"{api_base}/api/projects/{project_id}/objects/download-url",
        params={"path": json_path},
        headers=headers, timeout=10,
    )
    url_resp.raise_for_status()
    presigned_url = url_resp.json().get("url")
    if not presigned_url:
        raise RuntimeError(f"No presigned URL for {json_path}")
    _validate_presigned_url(presigned_url)

    json_resp = requests.get(presigned_url, timeout=15)
    json_resp.raise_for_status()
    metadata = json_resp.json()

    # Download mesh binary if available
    mesh_binary = None
    mesh_path = obj_info.get("mesh_data_path")
    if mesh_path:
        try:
            mesh_url_resp = requests.get(
                f"{api_base}/api/projects/{project_id}/objects/download-url",
                params={"path": mesh_path},
                headers=headers, timeout=10,
            )
            mesh_url_resp.raise_for_status()
            mesh_presigned = mesh_url_resp.json().get("url")
            if mesh_presigned:
                _validate_presigned_url(mesh_presigned)
                mesh_resp = requests.get(mesh_presigned, timeout=30)
                mesh_resp.raise_for_status()
                mesh_binary = mesh_resp.content
        except Exception as e:
            logger.warning(f"Failed to download mesh for '{obj_info.get('object_name')}': {e}")

    return metadata, mesh_binary


# ---------------- Stage Objects ----------------
class BVCS_OT_StageObjects(bpy.types.Operator):
    bl_idname = "bvcs.stage_objects"
    bl_label = "Stage Selected Objects"

    def execute(self, context):
        selected_objects = context.selected_objects
        if not selected_objects:
            self.report({'ERROR'}, "No objects selected")
            return {'CANCELLED'}

        for obj in selected_objects:
            _staging_area.stage(obj.name)
        self.report({'INFO'}, f"Staged {len(selected_objects)} objects")
        logger.info(f"Staged objects: {_staging_area.get_staged_names()}")
        return {'FINISHED'}


class BVCS_OT_StageAll(bpy.types.Operator):
    bl_idname = "bvcs.stage_all"
    bl_label = "Stage All Objects"

    def execute(self, context):
        scene_names = [obj.name for obj in bpy.context.scene.objects]
        if not scene_names:
            self.report({'ERROR'}, "No objects in scene")
            return {'CANCELLED'}
        _staging_area.stage_all(scene_names)
        self.report({'INFO'}, f"Staged all {len(scene_names)} objects")
        return {'FINISHED'}


class BVCS_OT_UnstageObject(bpy.types.Operator):
    bl_idname = "bvcs.unstage_object"
    bl_label = "Unstage Selected Objects"

    def execute(self, context):
        selected_objects = context.selected_objects
        if not selected_objects:
            self.report({'ERROR'}, "No objects selected")
            return {'CANCELLED'}
        for obj in selected_objects:
            _staging_area.unstage(obj.name)
        self.report({'INFO'}, f"Unstaged {len(selected_objects)} objects")
        return {'FINISHED'}

class BVCS_OT_StageDeletion(bpy.types.Operator):
    bl_idname = "bvcs.stage_deletion"
    bl_label = "Stage Deletion"
    bl_description = "Stage a deleted object for removal in the next commit"

    object_name: bpy.props.StringProperty(name="Object Name")

    def execute(self, context):
        if not self.object_name:
            self.report({'ERROR'}, "No object name specified")
            return {'CANCELLED'}
        _staging_area.stage_deletion(self.object_name)
        self.report({'INFO'}, f"Staged deletion: {self.object_name}")
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

        # Require staged objects or deletions
        if not _staging_area.has_staged_changes():
            self.report({'ERROR'}, "No objects staged. Stage objects before committing.")
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

            # Capture staged object names and deletions in the pending commit
            staged_names = _staging_area.get_staged_names()
            staged_deletions = _staging_area.get_staged_deletions()

            # Store commit info locally (will be synced to DB when pushed)
            # NOTE: lists are JSON-serialized because Blender IDProperties
            # don't reliably round-trip lists of strings.
            context.window_manager["bvcs_pending_commit"] = {
                "message": self.commit_message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "file_path": local_file_path,
                "base_commit_hash": base_commit_hash,
                "staged_objects_json": json.dumps(staged_names),
                "staged_deletions_json": json.dumps(staged_deletions),
            }

            total = len(staged_names) + len(staged_deletions)
            parts = []
            if staged_names:
                parts.append(f"{len(staged_names)} changed")
            if staged_deletions:
                parts.append(f"{len(staged_deletions)} deleted")
            self.report({'INFO'}, f"Committed locally: {self.commit_message} ({', '.join(parts)})")
            logger.info(f"Local commit created: {self.commit_message}, staged: {staged_names}, deletions: {staged_deletions}")

        except Exception as e:
            self.report({'ERROR'}, f"Commit failed: {e}")
            logger.error(f"Commit failed: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

# ---------------- Branch Operators ----------------

# Cache for branch enum items
_BRANCH_ENUM_ITEMS = [("main", "main", "Default branch")]
_BRANCH_ENUM_PROJECT_ID = ""


def _refresh_branch_enum(context):
    """Refresh the cached branch enum items."""
    global _BRANCH_ENUM_ITEMS, _BRANCH_ENUM_PROJECT_ID
    prefs = get_prefs(context)
    project_id = getattr(prefs, "project_id", "") or ""
    if not project_id or not getattr(prefs, "auth_token", None):
        _BRANCH_ENUM_ITEMS = [("main", "main", "Default branch")]
        return
    _BRANCH_ENUM_PROJECT_ID = project_id
    branches = _fetch_branches_list(prefs)
    if branches:
        _BRANCH_ENUM_ITEMS = [
            (b["branch_id"], b["branch_name"], f"Branch: {b['branch_name']}")
            for b in branches
        ]
    else:
        _BRANCH_ENUM_ITEMS = [("main", "main", "Default branch")]


def _branch_enum_items(self, context):
    return _BRANCH_ENUM_ITEMS


class BVCS_OT_SwitchBranch(bpy.types.Operator):
    bl_idname = "bvcs.switch_branch"
    bl_label = "Switch Branch"

    branch_enum: bpy.props.EnumProperty(
        name="Branch",
        description="Choose a branch",
        items=_branch_enum_items,
    )

    def execute(self, context):
        wm = context.window_manager
        prefs = get_prefs(context)

        if not self.branch_enum:
            self.report({'ERROR'}, "No branch selected")
            return {'CANCELLED'}

        # Find the branch name from the enum
        branches = _fetch_branches_list(prefs)
        selected = next(
            (b for b in branches if b["branch_id"] == self.branch_enum),
            None,
        )
        if not selected:
            self.report({'ERROR'}, "Branch not found")
            return {'CANCELLED'}

        _set_active_branch(wm, selected["branch_id"], selected["branch_name"])
        wm["bvcs_last_synced_commit_hash"] = ""
        self.report({'INFO'}, f"Switched to branch: {selected['branch_name']}")
        return {'FINISHED'}

    def invoke(self, context, event):
        _refresh_branch_enum(context)
        return context.window_manager.invoke_props_dialog(self)


class BVCS_OT_CreateBranch(bpy.types.Operator):
    bl_idname = "bvcs.create_branch"
    bl_label = "Create Branch"

    branch_name: bpy.props.StringProperty(
        name="Branch Name",
        description="Name for the new branch",
        default="",
    )

    def execute(self, context):
        prefs = get_prefs(context)
        wm = context.window_manager

        if not prefs.project_id:
            self.report({'ERROR'}, "No project selected")
            return {'CANCELLED'}
        if not self.branch_name.strip():
            self.report({'ERROR'}, "Branch name cannot be empty")
            return {'CANCELLED'}

        headers = get_auth_headers(prefs)
        api_base = get_api_base(prefs)

        payload = {"branch_name": self.branch_name.strip()}

        # If we have a current branch HEAD, use it as source
        active_branch_id = _get_active_branch_id(wm)
        if active_branch_id:
            branches = _fetch_branches_list(prefs)
            current = next((b for b in branches if b["branch_id"] == active_branch_id), None)
            if current and current.get("head_commit_id"):
                payload["source_commit_id"] = current["head_commit_id"]

        try:
            resp = requests.post(
                f"{api_base}/api/projects/{prefs.project_id}/branches",
                json=payload,
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            new_branch = resp.json()
        except Exception as e:
            self.report({'ERROR'}, f"Failed to create branch: {e}")
            return {'CANCELLED'}

        # Switch to the new branch
        _set_active_branch(wm, new_branch["branch_id"], new_branch["branch_name"])
        wm["bvcs_last_synced_commit_hash"] = ""
        self.report({'INFO'}, f"Created and switched to branch: {new_branch['branch_name']}")
        return {'FINISHED'}

    def invoke(self, context, event):
        self.branch_name = ""
        return context.window_manager.invoke_props_dialog(self)


class BVCS_OT_DeleteBranch(bpy.types.Operator):
    bl_idname = "bvcs.delete_branch"
    bl_label = "Delete Branch"

    branch_enum: bpy.props.EnumProperty(
        name="Branch",
        description="Choose a branch to delete",
        items=_branch_enum_items,
    )

    def execute(self, context):
        prefs = get_prefs(context)
        wm = context.window_manager

        if not self.branch_enum:
            self.report({'ERROR'}, "No branch selected")
            return {'CANCELLED'}

        branches = _fetch_branches_list(prefs)
        selected = next(
            (b for b in branches if b["branch_id"] == self.branch_enum),
            None,
        )
        if not selected:
            self.report({'ERROR'}, "Branch not found")
            return {'CANCELLED'}

        if selected["branch_name"] == "main":
            self.report({'ERROR'}, "Cannot delete the default branch")
            return {'CANCELLED'}

        headers = get_auth_headers(prefs)
        api_base = get_api_base(prefs)
        try:
            resp = requests.delete(
                f"{api_base}/api/projects/{prefs.project_id}/branches/{selected['branch_id']}",
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
        except Exception as e:
            self.report({'ERROR'}, f"Failed to delete branch: {e}")
            return {'CANCELLED'}

        # If we deleted the active branch, switch to main
        if _get_active_branch_id(wm) == selected["branch_id"]:
            main = next((b for b in branches if b.get("branch_name") == "main"), None)
            if main:
                _set_active_branch(wm, main["branch_id"], main["branch_name"])
            else:
                wm["bvcs_active_branch_id"] = ""
                wm["bvcs_active_branch_name"] = "main"
            wm["bvcs_last_synced_commit_hash"] = ""

        self.report({'INFO'}, f"Deleted branch: {selected['branch_name']}")
        return {'FINISHED'}

    def invoke(self, context, event):
        _refresh_branch_enum(context)
        return context.window_manager.invoke_props_dialog(self)


# Cache for the source-branch enum used by BVCS_OT_MergeBranch
_MERGE_SOURCE_BRANCH_ITEMS = [("NONE", "No other branches", "No branches available to merge from")]


def _merge_source_branch_items(self, context):
    return _MERGE_SOURCE_BRANCH_ITEMS


class BVCS_OT_MergeBranch(bpy.types.Operator):
    """Merge another branch into the current branch on the server."""
    bl_idname = "bvcs.merge_branch"
    bl_label = "Merge Branch"

    source_branch_id: bpy.props.EnumProperty(
        name="From",
        description="Branch to merge into the current branch",
        items=_merge_source_branch_items,
    )
    commit_message: bpy.props.StringProperty(
        name="Message",
        description="Optional commit message for the merge commit",
        default="",
    )

    def invoke(self, context, event):
        global _MERGE_SOURCE_BRANCH_ITEMS
        prefs = get_prefs(context)
        wm = context.window_manager

        if not prefs.project_id:
            self.report({'ERROR'}, "No project selected")
            return {'CANCELLED'}
        if not prefs.auth_token:
            self.report({'ERROR'}, "Not logged in")
            return {'CANCELLED'}

        _ensure_active_branch(wm, prefs)
        active_branch_id = _get_active_branch_id(wm)
        if not active_branch_id:
            self.report({'ERROR'}, "No active branch — switch to a branch first")
            return {'CANCELLED'}

        branches = _fetch_branches_list(prefs)
        sources = [b for b in branches if str(b.get("branch_id")) != str(active_branch_id)]
        if not sources:
            self.report({'ERROR'}, "No other branches to merge from. Create a branch first.")
            return {'CANCELLED'}

        _MERGE_SOURCE_BRANCH_ITEMS = [
            (str(b["branch_id"]), b["branch_name"], f"Merge from {b['branch_name']}")
            for b in sources
        ]
        self.source_branch_id = _MERGE_SOURCE_BRANCH_ITEMS[0][0]
        self.commit_message = ""
        return context.window_manager.invoke_props_dialog(self, width=440)

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        target_name = _get_active_branch_name(wm)
        layout.label(text=f"Target: {target_name}", icon='OUTLINER_OB_CURVE')
        layout.prop(self, "source_branch_id")
        layout.prop(self, "commit_message")
        layout.separator()
        layout.label(text="The server merges branch histories.", icon='INFO')
        layout.label(text="Pull after merging to update your local scene.", icon='INFO')

    def execute(self, context):
        prefs = get_prefs(context)
        wm = context.window_manager

        if not self.source_branch_id or self.source_branch_id == "NONE":
            self.report({'ERROR'}, "No source branch selected")
            return {'CANCELLED'}

        active_branch_id = _get_active_branch_id(wm)
        if not active_branch_id:
            self.report({'ERROR'}, "No active branch")
            return {'CANCELLED'}

        if str(self.source_branch_id) == str(active_branch_id):
            self.report({'ERROR'}, "Source and target branches are the same")
            return {'CANCELLED'}

        api_base = get_api_base(prefs)
        headers = get_auth_headers(prefs)
        payload = {"source_branch_id": str(self.source_branch_id)}
        if self.commit_message.strip():
            payload["commit_message"] = self.commit_message.strip()

        try:
            resp = requests.post(
                f"{api_base}/api/projects/{prefs.project_id}/branches/{active_branch_id}/merge",
                json=payload,
                headers=headers,
                timeout=30,
            )
        except Exception as e:
            logger.error(f"Merge request failed: {e}")
            self.report({'ERROR'}, f"Merge request failed: {e}")
            return {'CANCELLED'}

        target_name = _get_active_branch_name(wm)
        source_name = next(
            (item[1] for item in _MERGE_SOURCE_BRANCH_ITEMS if item[0] == self.source_branch_id),
            "source",
        )

        if resp.status_code == 200:
            try:
                commit = resp.json()
            except Exception:
                commit = {}
            short_hash = str(commit.get("commit_hash", ""))[:8]
            # Invalidate sync state so the user is prompted to pull the merge result
            wm["bvcs_last_synced_commit_hash"] = ""
            msg = (
                f"Merged '{source_name}' into '{target_name}'"
                + (f" (commit {short_hash})." if short_hash else ".")
                + " Click Pull to sync your scene."
            )
            self.report({'INFO'}, msg)
            return {'FINISHED'}

        if resp.status_code == 409:
            try:
                detail = resp.json().get("detail", {})
            except Exception:
                detail = {}
            conflicts = detail.get("conflicts", []) if isinstance(detail, dict) else []
            names = [c.get("object_name", "?") for c in conflicts]
            preview = ", ".join(names[:5]) + ("…" if len(names) > 5 else "")
            self.report(
                {'ERROR'},
                f"Merge conflicts on {len(names)} object(s){': ' + preview if names else ''}. "
                "Resolve via Pull on the target branch or merge in the opposite direction first.",
            )
            return {'CANCELLED'}

        try:
            err = resp.json().get("detail", resp.text)
        except Exception:
            err = resp.text
        self.report({'ERROR'}, f"Merge failed ({resp.status_code}): {err}")
        return {'CANCELLED'}


# ---------------- Push / Pull / Conflicts ----------------
class BVCS_OT_Push(bpy.types.Operator):
    bl_idname = "bvcs.push"
    bl_label = "Push to Remote"

    def execute(self, context):
        prefs = get_prefs(context)
        wm = context.window_manager

        if not prefs.project_id:
            self.report({'ERROR'}, "No project selected")
            return {'CANCELLED'}

        # Get pending commit info
        pending_commit = wm.get("bvcs_pending_commit")
        if not pending_commit:
            self.report({'ERROR'}, "No commit to push. Please commit first.")
            return {'CANCELLED'}

        # ── Conflict check ──────────────────────────────────────────────
        try:
            remote_commit_hash = _get_latest_remote_commit_hash(prefs)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to check remote state: {e}")
            return {'CANCELLED'}

        user = get_logged_in_user(prefs)
        base_commit_hash = str(pending_commit.get("base_commit_hash") or "")

        if remote_commit_hash:
            if not base_commit_hash:
                self.report(
                    {'ERROR'},
                    "Push blocked: remote history exists but your commit has no base. Pull first."
                )
                return {'CANCELLED'}
            if base_commit_hash != remote_commit_hash:
                # Object-level three-way merge check
                # Base = last synced commit (common ancestor)
                base_objects_map = _get_commit_objects_by_hash(prefs, base_commit_hash)

                # Remote = current remote HEAD
                parent_objects = _get_parent_commit_objects(prefs)
                remote_objects_map = {
                    name: data.get("blob_hash", "")
                    for name, data in parent_objects.items()
                }

                # Local = current scene
                scene_objects_map = {}
                for obj in bpy.context.scene.objects:
                    meta = serialize_object_metadata(obj)
                    mesh_bin = None
                    if obj.type in MESH_TYPES and obj.data is not None:
                        mesh_bin = serialize_mesh_data(obj)
                    scene_objects_map[obj.name] = compute_object_hash(meta, mesh_bin)

                merge_plan = compute_object_diff(
                    base_objects_map,
                    scene_objects_map,
                    remote_objects_map,
                )
                if merge_plan.conflicts:
                    conflict_names = [c["object_name"] for c in merge_plan.conflicts]

                    # Get remote commit ID for merge parent reference
                    remote_commit_id = ""
                    try:
                        commits_resp = requests.get(
                            f"{get_api_base(prefs)}/api/projects/{prefs.project_id}/commits",
                            params={"branch_name": _get_active_branch_name(bpy.context.window_manager)},
                            headers=get_auth_headers(prefs), timeout=10,
                        )
                        commits_resp.raise_for_status()
                        commits = commits_resp.json()
                        if isinstance(commits, list) and commits:
                            remote_commit_id = str(commits[0].get("commit_id", ""))
                    except Exception:
                        pass

                    # Store enriched conflict state
                    wm["bvcs_merge_conflicts"] = {
                        "flow": "push",
                        "base_commit_hash": base_commit_hash,
                        "remote_commit_hash": remote_commit_hash,
                        "remote_commit_id": remote_commit_id,
                        "detected_at": datetime.now(timezone.utc).isoformat(),
                        "merge_plan": {
                            "auto_merge_local": merge_plan.auto_merge_local,
                            "auto_merge_remote": merge_plan.auto_merge_remote,
                            "unchanged": merge_plan.unchanged,
                            "conflicts": merge_plan.conflicts,
                        },
                    }

                    # Populate conflict items for UI
                    wm.bvcs_conflict_items.clear()
                    for c in merge_plan.conflicts:
                        item = wm.bvcs_conflict_items.add()
                        item.object_name = c["object_name"]
                        item.conflict_type = str(c.get("conflict_type", ""))
                        item.local_hash = str(c.get("local_hash", ""))[:10]
                        item.remote_hash = str(c.get("remote_hash", ""))[:10]
                        # Set sensible defaults based on conflict type
                        ctype = str(c.get("conflict_type", ""))
                        if ctype == "DELETED_LOCALLY":
                            item.resolution = "KEEP_REMOTE"
                        elif ctype == "DELETED_REMOTELY":
                            item.resolution = "KEEP_LOCAL"
                        else:
                            item.resolution = "KEEP_LOCAL"

                    # Also keep legacy key for backward compatibility
                    wm["bvcs_push_conflict"] = {
                        "base_commit_hash": base_commit_hash,
                        "remote_commit_hash": remote_commit_hash,
                        "conflict_objects": conflict_names,
                        "detected_at": datetime.now(timezone.utc).isoformat(),
                    }

                    self.report(
                        {'ERROR'},
                        f"Push blocked: conflicts on {', '.join(conflict_names)}. Resolve in the panel before pushing."
                    )
                    return {'CANCELLED'}

                # No conflicts — can proceed (auto-merge)
                logger.info("No object-level conflicts, proceeding with push")

        # ── Prepare objects ──────────────────────────────────────────────
        self.report({'INFO'}, "Preparing objects for upload...")

        parent_objects = _get_parent_commit_objects(prefs)
        scene_objects = list(bpy.context.scene.objects)

        # Decode staged names and deletions from JSON strings (stored this
        # way because Blender IDProperties don't reliably round-trip string lists).
        staged_names = set()
        staged_json = pending_commit.get("staged_objects_json", "")
        if staged_json:
            try:
                staged_names = set(json.loads(str(staged_json)))
            except (json.JSONDecodeError, TypeError):
                logger.warning("Could not parse staged_objects_json, treating all objects as staged")
                staged_names = set()
        # Backward compat: old commits stored "staged_objects" as a raw list
        if not staged_names:
            raw = pending_commit.get("staged_objects", [])
            try:
                staged_names = set(str(n) for n in raw if n)
            except (TypeError, ValueError):
                staged_names = set()

        staged_deletions = set()
        deletions_json = pending_commit.get("staged_deletions_json", "")
        if deletions_json:
            try:
                staged_deletions = set(json.loads(str(deletions_json)))
            except (json.JSONDecodeError, TypeError):
                staged_deletions = set()

        push_result = prepare_push_objects(
            scene_objects,
            parent_objects,
            staged_names=staged_names if staged_names else None,
            staged_deletions=staged_deletions,
        )

        # ── Upload changed objects via presigned URLs / direct upload ────
        headers = get_auth_headers(prefs)
        api_base = get_api_base(prefs)

        # Get active branch ID
        wm = context.window_manager
        _ensure_active_branch(wm, prefs)
        active_branch_id = _get_active_branch_id(wm)
        active_branch_name = _get_active_branch_name(wm)
        if not active_branch_id:
            # Fallback: fetch branches and find the active one
            try:
                branches_list = _fetch_branches_list(prefs)
                active_branch = next(
                    (b for b in branches_list if b.get("branch_name") == active_branch_name),
                    None,
                )
                if not active_branch:
                    self.report({'ERROR'}, f"Branch '{active_branch_name}' not found")
                    return {'CANCELLED'}
                active_branch_id = active_branch["branch_id"]
                _set_active_branch(wm, active_branch_id, active_branch_name)
            except Exception as e:
                self.report({'ERROR'}, f"Failed to fetch branches: {e}")
                return {'CANCELLED'}

        if not user:
            user = get_logged_in_user(prefs)
        if not user:
            self.report({'ERROR'}, "Cannot get logged-in user")
            return {'CANCELLED'}

        upload_results = {}
        changed_objects = [obj for obj in push_result if obj["changed"]]
        unchanged_objects = [obj for obj in push_result if not obj["changed"]]

        self.report({'INFO'}, f"Uploading {len(changed_objects)} changed objects...")

        for obj_data in changed_objects:
            name = obj_data["object_name"]

            try:
                # Upload JSON metadata via the storage endpoint
                json_bytes = json.dumps(obj_data["metadata"], indent=2).encode("utf-8")

                import io
                files = {"json_file": ("metadata.json", io.BytesIO(json_bytes), "application/json")}
                if obj_data["mesh_binary"]:
                    files["mesh_file"] = ("mesh.bin", io.BytesIO(obj_data["mesh_binary"]), "application/octet-stream")

                upload_resp = requests.post(
                    f"{api_base}/api/projects/{prefs.project_id}/objects/stage-upload",
                    params={
                        "object_name": name,
                        "object_type": obj_data["object_type"],
                        "blob_hash": obj_data["blob_hash"],
                    },
                    files=files,
                    headers=headers,
                    timeout=30,
                )
                upload_resp.raise_for_status()
                upload_data = upload_resp.json()

                upload_results[name] = {
                    "json_data_path": upload_data.get("json_path", ""),
                    "mesh_data_path": upload_data.get("mesh_path"),
                    "blob_hash": obj_data["blob_hash"],
                }
            except Exception as e:
                logger.error(f"Failed to upload object {name}: {e}")
                self.report({'ERROR'}, f"Failed to upload {name}: {e}")
                return {'CANCELLED'}

        # Build the full commit objects list (changed + unchanged)
        commit_objects = build_commit_objects_list(push_result, upload_results)

        # ── Create commit in database ────────────────────────────────────
        try:
            commit_payload = {
                "branch_id": active_branch_id,
                "commit_message": pending_commit["message"],
                "objects": commit_objects,
            }

            self.report({'INFO'}, "Creating commit in database...")
            commit_resp = requests.post(
                f"{api_base}/api/projects/{prefs.project_id}/commits",
                json=commit_payload,
                headers=headers,
                timeout=15,
            )
            commit_resp.raise_for_status()
            commit_data = commit_resp.json()
        except Exception as e:
            logger.error(f"Failed to create commit: {e}")
            self.report({'ERROR'}, f"Commit creation failed: {e}")
            return {'CANCELLED'}

        # ── Update UI state ──────────────────────────────────────────────
        wm["bvcs_last_pushed"] = {
            "commit_id": commit_data.get("commit_id"),
            "commit_hash": commit_data.get("commit_hash"),
            "pushed_at": datetime.now(timezone.utc).isoformat(),
            "objects_uploaded": len(changed_objects),
            "objects_reused": len(unchanged_objects),
        }
        wm["bvcs_last_synced_commit_hash"] = commit_data.get("commit_hash") or ""
        if "bvcs_push_conflict" in wm:
            del wm["bvcs_push_conflict"]
        if "bvcs_push_conflict_compare" in wm:
            del wm["bvcs_push_conflict_compare"]
        if "bvcs_pending_commit" in wm:
            del wm["bvcs_pending_commit"]

        # Clear staging area after successful push
        _staging_area.clear()

        _refresh_project_blend_file_cache(context, prefs)

        logger.info(
            f"Pushed {len(changed_objects)} new + {len(unchanged_objects)} reused objects, "
            f"commit {commit_data.get('commit_hash')}"
        )
        self.report(
            {'INFO'},
            f"Push successful! {len(changed_objects)} uploaded, {len(unchanged_objects)} reused."
        )

        return {'FINISHED'}

class BVCS_OT_PullProject(bpy.types.Operator):
    bl_idname = "bvcs.pull_project"
    bl_label = "Pull Latest from Remote"

    # Set to True when the user confirms a dirty-state merge via the dialog
    _confirmed_dirty_pull: bool = False
    # Cached merge plan from the dirty-state check (avoids re-computation)
    _cached_pull_merge_plan = None

    def invoke(self, context, event):
        """Check local state before pulling. If dirty, show confirmation dialog."""
        prefs = get_prefs(context)
        wm = context.window_manager

        if not prefs.project_id:
            self.report({'ERROR'}, "No project selected")
            return {'CANCELLED'}

        # Determine if local state is dirty
        has_staged = bool(_staging_area.staged_objects)
        has_pending = bool(wm.get("bvcs_pending_commit"))
        is_dirty = has_staged or has_pending

        if not is_dirty:
            # Clean state — proceed directly
            self.__class__._confirmed_dirty_pull = False
            self.__class__._cached_pull_merge_plan = None
            return self.execute(context)

        # Dirty state — we need to check for merge conflicts before asking
        try:
            remote_commit_hash = _get_latest_remote_commit_hash(prefs)
            synced_hash = _get_last_synced_commit_hash(wm)

            if not remote_commit_hash or remote_commit_hash == synced_hash:
                # Remote hasn't changed — safe to inform user
                self.report({'INFO'}, "Already up to date")
                return {'CANCELLED'}

            # Fetch remote commit objects for merge check
            headers = get_auth_headers(prefs)
            api_base = get_api_base(prefs)
            project_id = prefs.project_id

            commits_resp = requests.get(
                f"{api_base}/api/projects/{project_id}/commits",
                params={"branch_name": _get_active_branch_name(bpy.context.window_manager)},
                headers=headers, timeout=10,
            )
            commits_resp.raise_for_status()
            commits = commits_resp.json()
            if not isinstance(commits, list) or not commits:
                self.report({'ERROR'}, "No commits found for this project")
                return {'CANCELLED'}

            latest_commit = commits[0]
            commit_id = latest_commit.get("commit_id")

            objects_resp = requests.get(
                f"{api_base}/api/projects/{project_id}/commits/{commit_id}/objects",
                headers=headers, timeout=10,
            )
            objects_resp.raise_for_status()
            remote_objects_list = objects_resp.json()
            if not isinstance(remote_objects_list, list):
                remote_objects_list = []

            # Build hash maps for three-way merge
            remote_hash_map = build_commit_objects_hash_map(remote_objects_list)

            # Base = last synced commit (common ancestor)
            base_hash_map = _get_commit_objects_by_hash(prefs, synced_hash)

            # Build local scene hash map
            scene_hash_map = {}
            for obj in bpy.context.scene.objects:
                meta = serialize_object_metadata(obj)
                mesh_bin = None
                if obj.type in MESH_TYPES and obj.data is not None:
                    mesh_bin = serialize_mesh_data(obj)
                scene_hash_map[obj.name] = compute_object_hash(meta, mesh_bin)

            merge_plan = compute_object_diff(
                base_hash_map,
                scene_hash_map,
                remote_hash_map,
            )
            self.__class__._cached_pull_merge_plan = merge_plan

            if merge_plan.conflicts:
                # Block pull — conflicts found
                conflict_names = [c["object_name"] for c in merge_plan.conflicts]

                # Get remote commit ID for merge parent reference
                remote_commit_id = str(latest_commit.get("commit_id", ""))

                # Store enriched conflict state
                wm["bvcs_merge_conflicts"] = {
                    "flow": "pull",
                    "base_commit_hash": synced_hash,
                    "remote_commit_hash": remote_commit_hash,
                    "remote_commit_id": remote_commit_id,
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                    "merge_plan": {
                        "auto_merge_local": merge_plan.auto_merge_local,
                        "auto_merge_remote": merge_plan.auto_merge_remote,
                        "unchanged": merge_plan.unchanged,
                        "conflicts": merge_plan.conflicts,
                    },
                }

                # Populate conflict items for UI
                wm.bvcs_conflict_items.clear()
                for c in merge_plan.conflicts:
                    item = wm.bvcs_conflict_items.add()
                    item.object_name = c["object_name"]
                    item.conflict_type = str(c.get("conflict_type", ""))
                    item.local_hash = str(c.get("local_hash", ""))[:10]
                    item.remote_hash = str(c.get("remote_hash", ""))[:10]
                    ctype = str(c.get("conflict_type", ""))
                    if ctype == "DELETED_LOCALLY":
                        item.resolution = "KEEP_REMOTE"
                    elif ctype == "DELETED_REMOTELY":
                        item.resolution = "KEEP_LOCAL"
                    else:
                        item.resolution = "KEEP_LOCAL"

                # Legacy key for backward compatibility
                wm["bvcs_push_conflict"] = {
                    "base_commit_hash": synced_hash,
                    "remote_commit_hash": remote_commit_hash,
                    "conflict_objects": conflict_names,
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                }

                self.report(
                    {'ERROR'},
                    f"Pull blocked: merge conflicts on {', '.join(conflict_names)}. "
                    f"Resolve conflicts in the panel before pulling."
                )
                return {'CANCELLED'}

            # No conflicts — show confirmation dialog
            self.__class__._confirmed_dirty_pull = False
            return context.window_manager.invoke_confirm(self, event)

        except Exception as e:
            logger.error(f"Pull pre-check failed: {e}")
            self.report({'ERROR'}, f"Pull pre-check failed: {e}")
            return {'CANCELLED'}

    def execute(self, context):
        prefs = get_prefs(context)
        wm = context.window_manager

        if not prefs.project_id:
            self.report({'ERROR'}, "No project selected")
            return {'CANCELLED'}

        # Determine if local state is dirty
        has_staged = bool(_staging_area.staged_objects)
        has_pending = bool(wm.get("bvcs_pending_commit"))
        is_dirty = has_staged or has_pending

        headers = get_auth_headers(prefs)
        api_base = get_api_base(prefs)
        project_id = prefs.project_id

        try:
            # ── Already-up-to-date check ─────────────────────────────────
            remote_commit_hash = _get_latest_remote_commit_hash(prefs)
            synced_hash = _get_last_synced_commit_hash(wm)

            if not remote_commit_hash:
                self.report({'ERROR'}, "No remote commits found")
                return {'CANCELLED'}

            if remote_commit_hash == synced_hash:
                self.report({'INFO'}, "Already up to date")
                return {'FINISHED'}

            # ── Fetch latest commit ──────────────────────────────────────
            commits_resp = requests.get(
                f"{api_base}/api/projects/{project_id}/commits",
                params={"branch_name": _get_active_branch_name(bpy.context.window_manager)},
                headers=headers,
                timeout=10,
            )
            commits_resp.raise_for_status()
            commits = commits_resp.json()
            if not isinstance(commits, list) or not commits:
                self.report({'ERROR'}, "No commits found for this project")
                return {'CANCELLED'}

            latest_commit = commits[0]
            commit_id = latest_commit.get("commit_id")

            # Fetch commit objects
            objects_resp = requests.get(
                f"{api_base}/api/projects/{project_id}/commits/{commit_id}/objects",
                headers=headers,
                timeout=10,
            )
            objects_resp.raise_for_status()
            commit_objects = objects_resp.json()

            if not isinstance(commit_objects, list) or not commit_objects:
                self.report({'ERROR'}, "No objects in latest commit")
                return {'CANCELLED'}

            # Check for backward compatibility with BLEND_FILE commits
            pull_data = prepare_pull_data(commit_objects)
            legacy_blend = next((obj for obj in pull_data if obj["is_legacy_blend"]), None)

            if legacy_blend:
                # Fallback: old-style BLEND_FILE commit — download .blend directly
                logger.info("Legacy BLEND_FILE commit detected, falling back to .blend download")
                latest_remote = _get_latest_remote_blend_file_info(prefs)
                if not latest_remote:
                    self.report({'ERROR'}, "No remote .blend file found")
                    return {'CANCELLED'}
                _open_project_file_info(context, prefs, latest_remote)
            else:
                # ── Object-level pull ────────────────────────────────────
                # Decide whether to clear the scene (full replace) or merge
                should_clear = not is_dirty

                self.report({'INFO'}, f"Downloading {len(pull_data)} objects...")

                objects_data = []
                mesh_binaries = {}

                for obj_info in pull_data:
                    name = obj_info["object_name"]
                    json_path = obj_info["json_data_path"]

                    # Download JSON metadata via presigned URL
                    try:
                        url_resp = requests.get(
                            f"{api_base}/api/projects/{project_id}/objects/download-url",
                            params={"path": json_path},
                            headers=headers,
                            timeout=10,
                        )
                        url_resp.raise_for_status()
                        presigned_url = url_resp.json().get("url")
                        if presigned_url:
                            _validate_presigned_url(presigned_url)
                            json_resp = requests.get(presigned_url, timeout=15)
                            json_resp.raise_for_status()
                            obj_metadata = json_resp.json()
                        else:
                            logger.warning(f"No presigned URL for {name}, skipping")
                            continue
                    except Exception as e:
                        logger.error(f"Failed to download metadata for {name}: {e}")
                        continue

                    objects_data.append(obj_metadata)

                    # Download mesh binary if present
                    if obj_info["has_mesh"] and obj_info["mesh_data_path"]:
                        try:
                            mesh_url_resp = requests.get(
                                f"{api_base}/api/projects/{project_id}/objects/download-url",
                                params={"path": obj_info["mesh_data_path"]},
                                headers=headers,
                                timeout=10,
                            )
                            mesh_url_resp.raise_for_status()
                            mesh_presigned = mesh_url_resp.json().get("url")
                            if mesh_presigned:
                                _validate_presigned_url(mesh_presigned)
                                mesh_resp = requests.get(mesh_presigned, timeout=30)
                                mesh_resp.raise_for_status()
                                mesh_binaries[name] = mesh_resp.content
                        except Exception as e:
                            logger.error(f"Failed to download mesh for {name}: {e}")

                if objects_data:
                    # Reconstruct scene — clear first if clean state
                    reconstruct_scene(objects_data, mesh_binaries,
                                      clear_existing=should_clear)

                    # Save as .blend locally
                    local_file = bpy.context.blend_data.filepath
                    if local_file:
                        bpy.ops.wm.save_mainfile()

            # ── Update sync state ────────────────────────────────────────
            wm["bvcs_last_pulled"] = {
                "commit_id": latest_commit.get("commit_id"),
                "commit_hash": latest_commit.get("commit_hash"),
                "commit_message": latest_commit.get("commit_message"),
                "pulled_at": datetime.now(timezone.utc).isoformat(),
                "object_count": len(pull_data) if not legacy_blend else 1,
            }
            wm["bvcs_last_synced_commit_hash"] = latest_commit.get("commit_hash") or ""
            if "bvcs_push_conflict" in wm:
                del wm["bvcs_push_conflict"]
            if "bvcs_push_conflict_compare" in wm:
                del wm["bvcs_push_conflict_compare"]

            # If dirty pull succeeded, rebase the pending commit
            if is_dirty:
                pending = wm.get("bvcs_pending_commit")
                if isinstance(pending, dict):
                    pending["base_commit_hash"] = latest_commit.get("commit_hash") or ""
                    wm["bvcs_pending_commit"] = pending

            # Clear the cached merge plan
            self.__class__._cached_pull_merge_plan = None

            _refresh_project_blend_file_cache(context, prefs)

            short_hash = str(latest_commit.get("commit_hash", ""))[:8]
            action = "merged" if is_dirty else "replaced scene with"
            self.report({'INFO'}, f"Pulled: {action} commit {short_hash} ({len(pull_data)} objects)")
            logger.info(f"Pulled commit {latest_commit.get('commit_hash')} (dirty={is_dirty})")

        except Exception as e:
            logger.error(f"Failed to pull: {e}")
            self.report({'ERROR'}, f"Pull failed: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}

class BVCS_OT_LoadProjectFile(bpy.types.Operator):
    """Load a specific commit's objects into the scene (object-level checkout)."""
    bl_idname = "bvcs.load_project_file"
    bl_label = "Load Commit"

    def execute(self, context):
        prefs = get_prefs(context)
        wm = context.window_manager

        if not prefs.project_id:
            self.report({'ERROR'}, "No project selected")
            return {'CANCELLED'}
        if not prefs.auth_token:
            self.report({'ERROR'}, "Not logged in")
            return {'CANCELLED'}

        selected = wm.bvcs_project_file
        if not selected or selected == "NONE":
            self.report({'ERROR'}, "Select a commit first")
            return {'CANCELLED'}

        commit_info = PROJECT_BLEND_FILE_MAP.get(selected)
        if not commit_info:
            self.report({'ERROR'}, "Selected commit is no longer available")
            return {'CANCELLED'}

        commit_id = commit_info.get("commit_id")
        commit_hash = commit_info.get("commit_hash", "")
        if not commit_id:
            self.report({'ERROR'}, "Invalid commit data")
            return {'CANCELLED'}

        headers = get_auth_headers(prefs)
        api_base = get_api_base(prefs)
        project_id = prefs.project_id

        try:
            # Fetch objects for the selected commit
            objects_resp = requests.get(
                f"{api_base}/api/projects/{project_id}/commits/{commit_id}/objects",
                headers=headers,
                timeout=10,
            )
            objects_resp.raise_for_status()
            commit_objects = objects_resp.json()

            if not isinstance(commit_objects, list) or not commit_objects:
                self.report({'ERROR'}, "No objects in this commit")
                return {'CANCELLED'}

            pull_data = prepare_pull_data(commit_objects)

            # Check for legacy BLEND_FILE commits
            legacy_blend = next((obj for obj in pull_data if obj["is_legacy_blend"]), None)
            if legacy_blend:
                # Fallback: old-style BLEND_FILE commit — download .blend directly
                logger.info("Legacy BLEND_FILE commit detected, falling back to .blend download")
                file_info = {
                    "s3_path": legacy_blend["json_data_path"],
                    "object_name": legacy_blend["object_name"],
                    "commit_id": commit_id,
                    "commit_hash": commit_hash,
                    "commit_message": commit_info.get("commit_message", ""),
                }
                _open_project_file_info(context, prefs, file_info)
                return {'FINISHED'}

            # Object-level checkout: download and reconstruct scene
            self.report({'INFO'}, f"Loading {len(pull_data)} objects from commit {commit_hash[:8]}...")

            objects_data = []
            mesh_binaries = {}

            for obj_info in pull_data:
                name = obj_info["object_name"]
                json_path = obj_info["json_data_path"]

                try:
                    url_resp = requests.get(
                        f"{api_base}/api/projects/{project_id}/objects/download-url",
                        params={"path": json_path},
                        headers=headers,
                        timeout=10,
                    )
                    url_resp.raise_for_status()
                    presigned_url = url_resp.json().get("url")
                    if presigned_url:
                        _validate_presigned_url(presigned_url)
                        data_resp = requests.get(presigned_url, timeout=30)
                        data_resp.raise_for_status()
                        metadata = data_resp.json()
                        objects_data.append(metadata)

                    # Download mesh binary if available
                    mesh_path = obj_info.get("mesh_data_path")
                    if mesh_path:
                        mesh_url_resp = requests.get(
                            f"{api_base}/api/projects/{project_id}/objects/download-url",
                            params={"path": mesh_path},
                            headers=headers,
                            timeout=10,
                        )
                        mesh_url_resp.raise_for_status()
                        mesh_presigned = mesh_url_resp.json().get("url")
                        if mesh_presigned:
                            _validate_presigned_url(mesh_presigned)
                            mesh_resp = requests.get(mesh_presigned, timeout=30)
                            mesh_resp.raise_for_status()
                            mesh_binaries[name] = mesh_resp.content
                except Exception as e:
                    logger.warning(f"Failed to download object '{name}': {e}")

            if not objects_data:
                self.report({'ERROR'}, "Failed to download any objects")
                return {'CANCELLED'}

            # Clear scene and reconstruct
            reconstruct_scene(objects_data, mesh_binaries, clear_existing=True)

            # Update sync state
            wm["bvcs_last_synced_commit_hash"] = commit_hash
            wm["bvcs_last_pulled"] = {
                "commit_id": commit_id,
                "commit_hash": commit_hash,
                "commit_message": commit_info.get("commit_message", ""),
                "pulled_at": datetime.now(timezone.utc).isoformat(),
                "object_count": len(objects_data),
            }

            self.report({'INFO'}, f"Loaded {len(objects_data)} objects from commit {commit_hash[:8]}")
            return {'FINISHED'}
        except Exception as e:
            logger.error(f"Failed to load commit: {e}")
            self.report({'ERROR'}, f"Load failed: {e}")
            return {'CANCELLED'}

class BVCS_ConflictItem(bpy.types.PropertyGroup):
    """Per-object conflict entry displayed in the N-panel."""
    object_name: bpy.props.StringProperty(name="Object")
    conflict_type: bpy.props.StringProperty(name="Type")
    local_hash: bpy.props.StringProperty(name="Local Hash")
    remote_hash: bpy.props.StringProperty(name="Remote Hash")
    resolution: bpy.props.EnumProperty(
        name="Resolution",
        items=[
            ("KEEP_LOCAL", "Keep Local", "Keep your local version"),
            ("KEEP_REMOTE", "Keep Remote", "Use the remote version"),
            ("KEEP_BOTH", "Keep Both", "Import remote as ObjectName.remote for comparison"),
            ("DELETE", "Delete", "Remove this object from the commit"),
        ],
        default="KEEP_LOCAL",
    )


class BVCS_OT_ApplyConflictResolutions(bpy.types.Operator):
    """Apply per-object conflict resolutions and create a merge commit."""
    bl_idname = "bvcs.apply_conflict_resolutions"
    bl_label = "Apply Conflict Resolutions"

    def execute(self, context):
        prefs = get_prefs(context)
        wm = context.window_manager

        if not prefs.project_id or not prefs.auth_token:
            self.report({'ERROR'}, "Not logged in or no project selected")
            return {'CANCELLED'}

        conflict_state = wm.get("bvcs_merge_conflicts")
        if not conflict_state:
            self.report({'ERROR'}, "No merge conflicts to resolve")
            return {'CANCELLED'}

        conflict_items = wm.bvcs_conflict_items
        if not conflict_items:
            self.report({'ERROR'}, "No conflict items found")
            return {'CANCELLED'}

        # Validate all conflicts have a resolution
        for item in conflict_items:
            if not item.resolution:
                self.report({'ERROR'}, f"No resolution set for '{item.object_name}'")
                return {'CANCELLED'}

        merge_plan_data = conflict_state.get("merge_plan", {})
        remote_commit_hash = str(conflict_state.get("remote_commit_hash", ""))
        remote_commit_id = str(conflict_state.get("remote_commit_id", ""))

        # Fetch remote objects (full data) for objects we need from remote
        remote_objects_full = _get_commit_objects_full_by_hash(prefs, remote_commit_hash)

        headers = get_auth_headers(prefs)
        api_base = get_api_base(prefs)

        # ── Process KEEP_BOTH and KEEP_REMOTE: download + import remote objects ──
        objects_to_import = []  # (metadata, mesh_binary, target_name)

        for item in conflict_items:
            if item.resolution in ("KEEP_REMOTE", "KEEP_BOTH"):
                remote_obj = remote_objects_full.get(item.object_name)
                if not remote_obj:
                    self.report({'ERROR'}, f"Remote data not found for '{item.object_name}'")
                    return {'CANCELLED'}
                try:
                    metadata, mesh_binary = _download_remote_object(prefs, remote_obj)
                    if item.resolution == "KEEP_BOTH":
                        # Rename to .remote for side-by-side comparison
                        target_name = f"{item.object_name}.remote"
                        metadata["object_name"] = target_name
                    else:
                        target_name = item.object_name
                    objects_to_import.append((metadata, mesh_binary, target_name))
                except Exception as e:
                    logger.error(f"Failed to download remote '{item.object_name}': {e}")
                    self.report({'ERROR'}, f"Download failed for '{item.object_name}': {e}")
                    return {'CANCELLED'}

        # ── Apply resolutions to the Blender scene ──
        for item in conflict_items:
            if item.resolution == "KEEP_LOCAL":
                # Nothing to do — local scene already has this object
                pass
            elif item.resolution in ("KEEP_REMOTE", "DELETE"):
                # Remove local object and its orphan data-block
                local_obj = bpy.data.objects.get(item.object_name)
                if local_obj:
                    obj_data_ref = local_obj.data  # mesh/camera/light data
                    bpy.data.objects.remove(local_obj, do_unlink=True)
                    # Remove orphan data-block so the name is freed for re-creation
                    if obj_data_ref and obj_data_ref.users == 0:
                        try:
                            for collection in (bpy.data.meshes, bpy.data.cameras,
                                               bpy.data.lights, bpy.data.armatures):
                                if obj_data_ref.name in collection:
                                    collection.remove(obj_data_ref)
                                    break
                        except Exception:
                            pass
            # KEEP_BOTH: don't remove local, remote will be added with .remote suffix

        # Import remote objects into scene
        if objects_to_import:
            import_data = [md for md, _, _ in objects_to_import]
            import_meshes = {}
            for md, mesh_bin, target_name in objects_to_import:
                if mesh_bin:
                    import_meshes[target_name] = mesh_bin
            reconstruct_scene(import_data, import_meshes, clear_existing=False)

        # ── Also handle auto-merge remote objects (changed only on remote side) ──
        auto_remote_names = merge_plan_data.get("auto_merge_remote", [])
        if auto_remote_names:
            auto_import_data = []
            auto_import_meshes = {}
            for name in auto_remote_names:
                remote_obj = remote_objects_full.get(name)
                if not remote_obj:
                    continue
                try:
                    metadata, mesh_binary = _download_remote_object(prefs, remote_obj)
                    auto_import_data.append(metadata)
                    if mesh_binary:
                        auto_import_meshes[name] = mesh_binary
                except Exception as e:
                    logger.warning(f"Failed to auto-merge remote object '{name}': {e}")
            if auto_import_data:
                reconstruct_scene(auto_import_data, auto_import_meshes, clear_existing=False)

        # ── Now build and push the merge commit ──
        self.report({'INFO'}, "Building merge commit...")

        try:
            # Get active branch ID
            _ensure_active_branch(wm, prefs)
            merge_branch_id = _get_active_branch_id(wm)
            if not merge_branch_id:
                branches_list = _fetch_branches_list(prefs)
                active_br = next(
                    (b for b in branches_list if b.get("branch_name") == _get_active_branch_name(wm)),
                    None,
                )
                if not active_br:
                    self.report({'ERROR'}, f"Branch '{_get_active_branch_name(wm)}' not found")
                    return {'CANCELLED'}
                merge_branch_id = active_br["branch_id"]

            # Build the full scene snapshot for the merge commit
            parent_objects = _get_parent_commit_objects(prefs)
            scene_objects = list(bpy.context.scene.objects)

            # All scene objects are staged for the merge commit
            staged_names = {obj.name for obj in scene_objects}
            staged_deletions = set()

            # Objects with resolution DELETE should be excluded
            for item in conflict_items:
                if item.resolution == "DELETE":
                    staged_deletions.add(item.object_name)
                    staged_names.discard(item.object_name)

            push_result = prepare_push_objects(
                scene_objects,
                parent_objects,
                staged_names=staged_names,
                staged_deletions=staged_deletions,
            )

            # Upload changed objects
            upload_results = {}
            changed_objects = [obj for obj in push_result if obj["changed"]]

            for obj_data in changed_objects:
                name = obj_data["object_name"]
                try:
                    import io
                    json_bytes = json.dumps(obj_data["metadata"], indent=2).encode("utf-8")
                    files = {"json_file": ("metadata.json", io.BytesIO(json_bytes), "application/json")}
                    if obj_data["mesh_binary"]:
                        files["mesh_file"] = ("mesh.bin", io.BytesIO(obj_data["mesh_binary"]), "application/octet-stream")

                    upload_resp = requests.post(
                        f"{api_base}/api/projects/{prefs.project_id}/objects/stage-upload",
                        params={
                            "object_name": name,
                            "object_type": obj_data["object_type"],
                            "blob_hash": obj_data["blob_hash"],
                        },
                        files=files,
                        headers=headers,
                        timeout=30,
                    )
                    upload_resp.raise_for_status()
                    upload_data = upload_resp.json()
                    upload_results[name] = {
                        "json_data_path": upload_data.get("json_path", ""),
                        "mesh_data_path": upload_data.get("mesh_path"),
                        "blob_hash": obj_data["blob_hash"],
                    }
                except Exception as e:
                    logger.error(f"Failed to upload merge object {name}: {e}")
                    self.report({'ERROR'}, f"Upload failed for {name}: {e}")
                    return {'CANCELLED'}

            commit_objects = build_commit_objects_list(push_result, upload_results)

            # Build conflict summary for commit message
            resolution_summary = ", ".join(
                f"{item.object_name}={item.resolution}" for item in conflict_items
            )
            pending = wm.get("bvcs_pending_commit")
            original_msg = (pending.get("message") if pending else None) or "Merge remote changes"
            merge_msg = f"Merge: {original_msg} [resolved: {resolution_summary}]"

            # Create merge commit
            commit_payload = {
                "branch_id": merge_branch_id,
                "commit_message": merge_msg,
                "objects": commit_objects,
                "merge_commit": True,
                "merge_parent_id": remote_commit_id if remote_commit_id else None,
            }

            commit_resp = requests.post(
                f"{api_base}/api/projects/{prefs.project_id}/commits",
                json=commit_payload,
                headers=headers,
                timeout=15,
            )
            commit_resp.raise_for_status()
            commit_data = commit_resp.json()

        except Exception as e:
            logger.error(f"Merge commit creation failed: {e}")
            self.report({'ERROR'}, f"Merge commit failed: {e}")
            return {'CANCELLED'}

        # ── Clean up state ──
        wm["bvcs_last_pushed"] = {
            "commit_id": commit_data.get("commit_id"),
            "commit_hash": commit_data.get("commit_hash"),
            "pushed_at": datetime.now(timezone.utc).isoformat(),
            "objects_uploaded": len(changed_objects),
            "objects_reused": len(push_result) - len(changed_objects),
        }
        wm["bvcs_last_synced_commit_hash"] = commit_data.get("commit_hash") or ""

        # Clear conflict state
        if "bvcs_merge_conflicts" in wm:
            del wm["bvcs_merge_conflicts"]
        if "bvcs_push_conflict" in wm:
            del wm["bvcs_push_conflict"]
        if "bvcs_push_conflict_compare" in wm:
            del wm["bvcs_push_conflict_compare"]
        if "bvcs_pending_commit" in wm:
            del wm["bvcs_pending_commit"]
        wm.bvcs_conflict_items.clear()
        _staging_area.clear()

        short_hash = str(commit_data.get("commit_hash", ""))[:8]
        self.report({'INFO'}, f"Merge commit created: {short_hash}")
        logger.info(f"Merge commit {commit_data.get('commit_hash')} with {len(conflict_items)} resolved conflicts")

        return {'FINISHED'}


class BVCS_OT_CancelMerge(bpy.types.Operator):
    """Cancel the current merge and discard conflict state."""
    bl_idname = "bvcs.cancel_merge"
    bl_label = "Cancel Merge"

    def execute(self, context):
        wm = context.window_manager
        if "bvcs_merge_conflicts" in wm:
            del wm["bvcs_merge_conflicts"]
        if "bvcs_push_conflict" in wm:
            del wm["bvcs_push_conflict"]
        if "bvcs_push_conflict_compare" in wm:
            del wm["bvcs_push_conflict_compare"]
        wm.bvcs_conflict_items.clear()
        self.report({'INFO'}, "Merge cancelled, conflict state cleared")
        return {'FINISHED'}

class BVCS_OT_PreviewRemoteConflicts(bpy.types.Operator):
    """Download remote conflict objects and open them in a new Blender window for comparison."""
    bl_idname = "bvcs.preview_remote_conflicts"
    bl_label = "Preview Remote"

    def execute(self, context):
        prefs = get_prefs(context)
        wm = context.window_manager

        if not prefs.project_id or not prefs.auth_token:
            self.report({'ERROR'}, "Not logged in or no project selected")
            return {'CANCELLED'}

        conflict_state = wm.get("bvcs_merge_conflicts")
        if not conflict_state:
            self.report({'ERROR'}, "No merge conflicts to preview")
            return {'CANCELLED'}

        conflict_items = wm.bvcs_conflict_items
        if not conflict_items:
            self.report({'ERROR'}, "No conflict items")
            return {'CANCELLED'}

        remote_commit_hash = str(conflict_state.get("remote_commit_hash", ""))
        remote_objects_full = _get_commit_objects_full_by_hash(prefs, remote_commit_hash)
        if not remote_objects_full:
            self.report({'ERROR'}, "Could not fetch remote objects")
            return {'CANCELLED'}

        # Download all remote conflict objects to a temp directory
        temp_dir = os.path.join(tempfile.gettempdir(), "bvcs_conflict_preview")
        # Clean out old preview data
        if os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        os.makedirs(temp_dir, exist_ok=True)

        downloaded_names = []

        for item in conflict_items:
            remote_obj = remote_objects_full.get(item.object_name)
            if not remote_obj:
                logger.warning(f"Remote data not found for '{item.object_name}', skipping preview")
                continue
            try:
                metadata, mesh_binary = _download_remote_object(prefs, remote_obj)

                # Write metadata JSON
                json_path = os.path.join(temp_dir, f"{item.object_name}.json")
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(metadata, f)

                # Write mesh binary if present
                if mesh_binary:
                    mesh_path = os.path.join(temp_dir, f"{item.object_name}.mesh")
                    with open(mesh_path, "wb") as f:
                        f.write(mesh_binary)

                downloaded_names.append(item.object_name)
            except Exception as e:
                logger.error(f"Failed to download remote '{item.object_name}': {e}")
                self.report({'WARNING'}, f"Could not download '{item.object_name}': {e}")

        if not downloaded_names:
            self.report({'ERROR'}, "No remote objects could be downloaded")
            return {'CANCELLED'}

        # Build a Python script that imports the addon's reconstruct_scene
        # and uses it with the downloaded data — so materials, modifiers, UVs,
        # node trees, etc. are all fully reconstructed.
        output_blend = os.path.join(temp_dir, "remote_conflicts.blend")
        script_path = os.path.join(temp_dir, "_reconstruct.py")

        # The addon package lives next to this __init__.py.
        # We add its parent to sys.path so the background Blender can import it.
        addon_pkg_dir = os.path.dirname(os.path.dirname(__file__))

        script = f'''\
import sys, os, json

# Make the addon package importable without installing it
sys.path.insert(0, {addon_pkg_dir!r})

from blender_vcs.object_serialization import reconstruct_scene

temp_dir = {temp_dir!r}
names = {json.dumps(downloaded_names)}

objects_data = []
mesh_binaries = {{}}

for name in names:
    json_path = os.path.join(temp_dir, name + ".json")
    mesh_path = os.path.join(temp_dir, name + ".mesh")

    with open(json_path, "r", encoding="utf-8") as f:
        objects_data.append(json.load(f))

    if os.path.isfile(mesh_path):
        with open(mesh_path, "rb") as f:
            mesh_binaries[name] = f.read()

reconstruct_scene(objects_data, mesh_binaries, clear_existing=True)

import bpy
bpy.ops.wm.save_as_mainfile(filepath={output_blend!r})
'''

        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script)

        # Run Blender in background to create the .blend
        blender_bin = bpy.app.binary_path
        if not blender_bin or not os.path.isfile(blender_bin):
            self.report({'ERROR'}, "Blender binary not found")
            return {'CANCELLED'}

        self.report({'INFO'}, "Building remote preview file...")

        try:
            result = subprocess.run(
                [blender_bin, "--background", "--python", script_path],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                stderr_tail = (result.stderr or "")[-800:]
                logger.error(f"Preview build failed: {stderr_tail}")
                self.report({'ERROR'}, "Failed to build remote preview file")
                return {'CANCELLED'}
        except subprocess.TimeoutExpired:
            self.report({'ERROR'}, "Preview build timed out")
            return {'CANCELLED'}

        if not os.path.isfile(output_blend):
            self.report({'ERROR'}, "Preview .blend file was not created")
            return {'CANCELLED'}

        # Open the preview in a new Blender window
        subprocess.Popen([blender_bin, output_blend])

        self.report({'INFO'},
                    f"Opened remote preview with {len(downloaded_names)} objects: "
                    f"{', '.join(downloaded_names)}")
        return {'FINISHED'}


class BVCS_OT_CheckConflicts(bpy.types.Operator):
    """Detect object-level conflicts between local scene and remote HEAD.

    Populates the panel's per-object conflict resolution UI (the same one used
    by Push/Pull) so the user can pick a resolution for each conflicting object.
    """
    bl_idname = "bvcs.check_conflicts"
    bl_label = "Check Merge Conflicts"

    def execute(self, context):
        prefs = get_prefs(context)
        wm = context.window_manager

        if not prefs.project_id:
            self.report({'ERROR'}, "No project selected")
            return {'CANCELLED'}
        if not prefs.auth_token:
            self.report({'ERROR'}, "Not logged in")
            return {'CANCELLED'}

        try:
            parent_objects = _get_parent_commit_objects(prefs)
            if not parent_objects:
                self.report({'INFO'}, "No remote commits on the active branch — nothing to compare against")
                return {'FINISHED'}

            scene_objects_map = {}
            for obj in bpy.context.scene.objects:
                meta = serialize_object_metadata(obj)
                mesh_bin = None
                if obj.type in MESH_TYPES and obj.data is not None:
                    mesh_bin = serialize_mesh_data(obj)
                scene_objects_map[obj.name] = compute_object_hash(meta, mesh_bin)

            remote_objects_map = {
                name: data.get("blob_hash", "")
                for name, data in parent_objects.items()
            }

            base_hash = _get_last_synced_commit_hash(wm)
            remote_hash = _get_latest_remote_commit_hash(prefs)

            if not remote_hash:
                self.report({'INFO'}, "No remote commits found on the active branch")
                return {'FINISHED'}

            base_objects_map = (
                _get_commit_objects_by_hash(prefs, base_hash)
                if base_hash and base_hash != remote_hash
                else {}
            )

            merge_plan = compute_object_diff(
                base_objects_map,
                scene_objects_map,
                remote_objects_map,
            )

            if not merge_plan.conflicts:
                if "bvcs_merge_conflicts" in wm:
                    del wm["bvcs_merge_conflicts"]
                if "bvcs_push_conflict" in wm:
                    del wm["bvcs_push_conflict"]
                wm.bvcs_conflict_items.clear()
                self.report({'INFO'}, "No merge conflicts detected")
                return {'FINISHED'}

            # Look up the remote commit's UUID so the panel can reference it
            remote_commit_id = ""
            try:
                api_base = get_api_base(prefs)
                headers = get_auth_headers(prefs)
                commits_resp = requests.get(
                    f"{api_base}/api/projects/{prefs.project_id}/commits",
                    params={"branch_name": _get_active_branch_name(wm)},
                    headers=headers,
                    timeout=10,
                )
                commits_resp.raise_for_status()
                commits = commits_resp.json() or []
                if commits:
                    remote_commit_id = str(commits[0].get("commit_id", ""))
            except Exception as e:
                logger.warning(f"Could not resolve remote commit id for conflict state: {e}")

            wm["bvcs_merge_conflicts"] = {
                "flow": "check",
                "base_commit_hash": base_hash or "",
                "remote_commit_hash": remote_hash,
                "remote_commit_id": remote_commit_id,
                "detected_at": datetime.now(timezone.utc).isoformat(),
                "merge_plan": {
                    "auto_merge_local": merge_plan.auto_merge_local,
                    "auto_merge_remote": merge_plan.auto_merge_remote,
                    "unchanged": merge_plan.unchanged,
                    "conflicts": merge_plan.conflicts,
                },
            }

            wm.bvcs_conflict_items.clear()
            for c in merge_plan.conflicts:
                item = wm.bvcs_conflict_items.add()
                item.object_name = c["object_name"]
                item.conflict_type = str(c.get("conflict_type", ""))
                item.local_hash = str(c.get("local_hash", ""))[:10]
                item.remote_hash = str(c.get("remote_hash", ""))[:10]
                ctype = str(c.get("conflict_type", ""))
                if ctype == "DELETED_LOCALLY":
                    item.resolution = "KEEP_REMOTE"
                elif ctype == "DELETED_REMOTELY":
                    item.resolution = "KEEP_LOCAL"
                else:
                    item.resolution = "KEEP_LOCAL"

            wm["bvcs_push_conflict"] = {
                "base_commit_hash": base_hash or "",
                "remote_commit_hash": remote_hash,
                "conflict_objects": [c["object_name"] for c in merge_plan.conflicts],
                "detected_at": datetime.now(timezone.utc).isoformat(),
            }

            count = len(merge_plan.conflicts)
            self.report(
                {'WARNING'},
                f"Found {count} conflict(s). Resolve each below, then click Apply Resolutions."
            )
            return {'FINISHED'}
        except Exception as e:
            logger.error(f"Failed to check conflicts: {e}")
            self.report({'ERROR'}, f"Failed to check conflicts: {e}")
            return {'CANCELLED'}

# ---------------- Diff/Status Operator ----------------
class BVCS_OT_RefreshStatus(bpy.types.Operator):
    bl_idname = "bvcs.refresh_status"
    bl_label = "Refresh Object Status"

    _cached_diff = {}

    def execute(self, context):
        prefs = get_prefs(context)
        if not prefs.project_id or not prefs.auth_token:
            self.report({'ERROR'}, "Not logged in or no project selected")
            return {'CANCELLED'}

        try:
            parent_objects = _get_parent_commit_objects(prefs)

            # Build scene hash map
            scene_hashes = {}
            for obj in bpy.context.scene.objects:
                meta = serialize_object_metadata(obj)
                mesh_bin = None
                if obj.type in MESH_TYPES and obj.data is not None:
                    mesh_bin = serialize_mesh_data(obj)
                scene_hashes[obj.name] = compute_object_hash(meta, mesh_bin)

            # Build parent hash map
            parent_hashes = {
                name: data.get("blob_hash", "")
                for name, data in parent_objects.items()
            }

            diff = compute_scene_diff(scene_hashes, parent_hashes)
            BVCS_OT_RefreshStatus._cached_diff = diff

            modified = sum(1 for s in diff.values() if s == ObjectStatus.MODIFIED)
            added = sum(1 for s in diff.values() if s == ObjectStatus.ADDED)
            deleted = sum(1 for s in diff.values() if s == ObjectStatus.DELETED)

            self.report({'INFO'}, f"Status: {modified} modified, {added} new, {deleted} deleted")
        except Exception as e:
            logger.error(f"Status refresh failed: {e}")
            self.report({'ERROR'}, f"Status refresh failed: {e}")
            return {'CANCELLED'}

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
            layout.operator("bvcs.open_signup")
            layout.operator("bvcs.login")

        if prefs.project_id:
            layout.label(text=f"Project: {prefs.project_id}")

            # ── Branch ──
            layout.separator()
            box = layout.box()
            box.label(text="Branch", icon='OUTLINER_OB_CURVE')
            branch_name = _get_active_branch_name(wm)
            box.label(text=f"  Current: {branch_name}", icon='CHECKMARK')
            row = box.row(align=True)
            row.operator("bvcs.switch_branch", text="Switch")
            row.operator("bvcs.create_branch", text="New")
            row.operator("bvcs.delete_branch", text="Delete")
            box.operator("bvcs.merge_branch", text="Merge Branch", icon='AUTOMERGE_ON')

            # ── Object Status / Diff ──
            layout.separator()
            box = layout.box()
            box.label(text="Object Status", icon='FILE_REFRESH')
            box.operator("bvcs.refresh_status", text="Refresh Status")

            diff = BVCS_OT_RefreshStatus._cached_diff
            if diff:
                for name, status in sorted(diff.items()):
                    icon = 'NONE'
                    if status == ObjectStatus.MODIFIED:
                        icon = 'FILE_BLEND'
                    elif status == ObjectStatus.ADDED:
                        icon = 'ADD'
                    elif status == ObjectStatus.DELETED:
                        icon = 'REMOVE'
                    row = box.row(align=True)
                    row.label(text=f"  [{status.value}] {name}", icon=icon)
                    # Show "Stage Deletion" button for deleted objects
                    if status == ObjectStatus.DELETED and not _staging_area.is_staged_for_deletion(name):
                        op = row.operator("bvcs.stage_deletion", text="", icon='TRASH')
                        op.object_name = name
            else:
                box.label(text="  No changes detected")

            # ── Staging Area ──
            layout.separator()
            box = layout.box()
            box.label(text="Staging Area", icon='CHECKBOX_HLT')
            row = box.row(align=True)
            row.operator("bvcs.stage_objects", text="Stage Selected")
            row.operator("bvcs.stage_all", text="Stage All")
            row.operator("bvcs.unstage_object", text="Unstage")

            staged = _staging_area.get_staged_names()
            staged_dels = _staging_area.get_staged_deletions()
            if staged or staged_dels:
                for name in staged:
                    status_icon = 'CHECKMARK'
                    # Show status indicator if available
                    if name in diff:
                        st = diff[name]
                        if st == ObjectStatus.MODIFIED:
                            status_icon = 'FILE_BLEND'
                        elif st == ObjectStatus.ADDED:
                            status_icon = 'ADD'
                    box.label(text=f"  {name}", icon=status_icon)
                for name in staged_dels:
                    box.label(text=f"  {name} (delete)", icon='TRASH')
            else:
                box.label(text="  No objects staged")

            # ── Commit / Push / Pull ──
            layout.separator()
            layout.operator("bvcs.commit")
            layout.operator("bvcs.push")
            layout.operator("bvcs.pull_project")

            row = layout.row(align=True)
            row.prop(context.window_manager, "bvcs_project_file", text="Commits")
            row.operator("bvcs.load_project_file", text="Load")

            layout.operator("bvcs.check_conflicts")

            # Show pending commit (waiting to be pushed)
            wm = context.window_manager
            if "bvcs_pending_commit" in wm:
                layout.separator()
                box = layout.box()
                box.label(text="Pending Commit:", icon='INFO')
                pending = wm["bvcs_pending_commit"]
                box.label(text=f"  {pending.get('message', 'N/A')}", icon='FILE_TICK')
                staged_count = len(pending.get("staged_objects", []))
                box.label(text=f"  {staged_count} objects staged")
                box.label(text="  (Click Push to sync)")

            # ── Merge Conflicts (per-object resolution) ──
            if "bvcs_merge_conflicts" in wm and wm.bvcs_conflict_items:
                conflict_state = wm["bvcs_merge_conflicts"]
                merge_plan = conflict_state.get("merge_plan", {})
                layout.separator()
                box = layout.box()
                flow = conflict_state.get("flow", "push").title()
                box.label(text=f"Merge Conflicts ({flow})", icon='ERROR')
                box.label(text=f"  Remote: {str(conflict_state.get('remote_commit_hash', ''))[:8]}...")

                # Show auto-resolved summary
                auto_local = len(merge_plan.get("auto_merge_local", []))
                auto_remote = len(merge_plan.get("auto_merge_remote", []))
                if auto_local or auto_remote:
                    box.label(text=f"  Auto-resolved: {auto_local} local, {auto_remote} remote", icon='CHECKMARK')

                # Show each conflict with resolution dropdown
                for i, item in enumerate(wm.bvcs_conflict_items):
                    conflict_box = box.box()
                    row = conflict_box.row()
                    row.label(text=item.object_name, icon='ERROR')
                    row.label(text=item.conflict_type)
                    row2 = conflict_box.row()
                    row2.label(text=f"Local: {item.local_hash}")
                    row2.label(text=f"Remote: {item.remote_hash}")
                    conflict_box.prop(item, "resolution", text="Resolution")

                # Preview + action buttons
                box.operator("bvcs.preview_remote_conflicts", text="Preview Remote Side", icon='WINDOW')
                row = box.row(align=True)
                row.operator("bvcs.apply_conflict_resolutions", text="Apply Resolutions", icon='CHECKMARK')
                row.operator("bvcs.cancel_merge", text="Cancel", icon='X')

            elif "bvcs_push_conflict" in wm:
                # Fallback: legacy conflict display (no merge_plan data)
                conflict = wm["bvcs_push_conflict"]
                layout.separator()
                box = layout.box()
                box.label(text="Push Conflict Detected", icon='ERROR')
                box.label(text=f"  Remote: {str(conflict.get('remote_commit_hash', ''))[:8]}...")
                conflict_objs = conflict.get("conflict_objects", [])
                if conflict_objs:
                    for cname in conflict_objs:
                        box.label(text=f"    {cname}", icon='ERROR')
                box.operator("bvcs.check_conflicts", text="Resolve Conflicts")

            # Show last push info
            if "bvcs_last_pushed" in wm:
                layout.separator()
                layout.label(text="Last Push:")
                last_push = wm["bvcs_last_pushed"]
                layout.label(text=f"  Commit: {last_push.get('commit_hash', 'N/A')[:8]}...", icon='CHECKMARK')
                uploaded = last_push.get("objects_uploaded", "?")
                reused = last_push.get("objects_reused", "?")
                layout.label(text=f"  {uploaded} uploaded, {reused} reused")

            # Show last pull info
            if "bvcs_last_pulled" in wm:
                layout.separator()
                layout.label(text="Last Pull:")
                last_pull = wm["bvcs_last_pulled"]
                layout.label(text=f"  {last_pull.get('commit_message', 'N/A')}", icon='IMPORT')
                obj_count = last_pull.get("object_count", "?")
                layout.label(text=f"  {obj_count} objects")

# ---------------- Registration ----------------
classes = [
    BVCSAddonPreferences,
    BVCS_ConflictItem,
    BVCS_OT_Login,
    BVCS_OT_OpenSignupPage,
    BVCS_OT_Logout,
    BVCS_OT_CreateProject,
    BVCS_OT_SelectProject,
    BVCS_OT_StageObjects,
    BVCS_OT_StageAll,
    BVCS_OT_UnstageObject,
    BVCS_OT_StageDeletion,
    BVCS_OT_Commit,
    BVCS_OT_SwitchBranch,
    BVCS_OT_CreateBranch,
    BVCS_OT_DeleteBranch,
    BVCS_OT_MergeBranch,
    BVCS_OT_Push,
    BVCS_OT_PullProject,
    BVCS_OT_LoadProjectFile,
    BVCS_OT_ApplyConflictResolutions,
    BVCS_OT_CancelMerge,
    BVCS_OT_PreviewRemoteConflicts,
    BVCS_OT_CheckConflicts,
    BVCS_OT_RefreshStatus,
    BVCS_PT_Panel,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.bvcs_project_file = bpy.props.EnumProperty(
        name="Commits",
        description="Select a commit to load into the scene",
        items=_enum_project_blend_files,
    )
    bpy.types.WindowManager.bvcs_conflict_items = bpy.props.CollectionProperty(
        type=BVCS_ConflictItem,
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
    if hasattr(bpy.types.WindowManager, "bvcs_conflict_items"):
        del bpy.types.WindowManager.bvcs_conflict_items
    if hasattr(bpy.types.WindowManager, "bvcs_project_file"):
        del bpy.types.WindowManager.bvcs_project_file
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

if __name__ == "__main__":
    register()