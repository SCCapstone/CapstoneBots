# Blender VCS Addon — Claude Code Instructions

## Overview

BVCS (Blender Version Control System) is a Blender addon that enables version control directly from within Blender. Users can login, create/open projects, commit changes, push/pull .blend files, and resolve conflicts — all from the N-Panel sidebar.

## Architecture

The entire addon lives in a single file — `blender_vcs/__init__.py` (~1800 lines). The `export/` directory contains the packaged ZIP for distribution.

### Code Organization (within `__init__.py`)

```
1. bl_info dict (addon metadata)
2. Imports + boto3 auto-installer
3. Logger setup
4. AddonPreferences (BVCSAddonPreferences — API URL, JWT token, S3 config)
5. Helper functions (get_prefs, auth, S3 client, file utils)
6. Operators (BVCS_OT_* classes — login, logout, create/select project, commit, push, pull, etc.)
7. UI Panels (BVCS_PT_* classes — sidebar panels in the N-Panel)
8. register() / unregister() functions
```

### Key Components

| Component | Description |
|-----------|-------------|
| `BVCSAddonPreferences` | Stores API URL, JWT token, S3 credentials in Blender prefs |
| `BVCS_OT_Login/Logout` | JWT authentication against backend API |
| `BVCS_OT_CreateProject` | Creates new project via backend API |
| `BVCS_OT_SelectProject` | Opens existing project with enum selector |
| `BVCS_OT_Commit` | Exports scene objects as JSON + commits to backend |
| `BVCS_OT_Push` | Uploads .blend file to S3 |
| `BVCS_OT_Pull` | Downloads latest .blend from S3 and opens it |
| `BVCS_OT_CheckConflicts` | Detects merge conflicts at the object level |
| `make_s3_client()` | Creates boto3 S3 client from addon preferences |
| `fetch_user_s3_credentials()` | Fetches S3 config from backend `/api/auth/s3-config` |

## Development Notes

### Blender Python API (bpy)
- Target Blender version: **4.5.0+** (see `bl_info["blender"]`)
- All operators must inherit from `bpy.types.Operator` and define `bl_idname`, `bl_label`
- Operator IDs follow the pattern `bvcs.<action>` (e.g., `bvcs.login`, `bvcs.commit`)
- UI panels inherit from `bpy.types.Panel` with `bl_space_type = 'VIEW_3D'` and `bl_region_type = 'UI'`
- Use `self.report({'ERROR'}, msg)` for user-facing errors in operators, `logger.error()` for log output
- Use `bpy.props.*Property()` for operator and preferences properties (StringProperty, BoolProperty, etc.)
- Use `invoke_props_dialog()` for operators that need user input before execution

### Network Communication
- All REST calls use the `requests` library (synchronous — Blender's Python is single-threaded)
- API base URL from `prefs.api_url`, auth via `Bearer {prefs.auth_token}` header
- Always set `timeout=5` or `timeout=10` on requests to avoid hanging Blender
- Use `ThreadPoolExecutor` for concurrent S3 operations (see `_refresh_project_blend_file_cache`)

### S3 Operations
- boto3 is auto-installed at runtime if missing (into `_vendor/` subdirectory)
- S3 credentials are fetched from backend on login via `/api/auth/s3-config`
- `make_s3_client()` creates the client and handles credential fetching
- S3 URIs follow the format `s3://bucket/key`
- Upload operations: `upload_file_to_s3()`, `upload_folder_to_s3()`

### File Handling
- `.blend` files are uploaded as-is to S3
- Object data is exported as JSON with mesh data serialized separately
- SHA-256 hashing for content deduplication
- Temp files go in `tempfile.gettempdir()` under `bvcs_*` subdirectories
- `_cleanup_bvcs_temp_dirs()` removes stale temp files (>24h old)

## Coding Conventions

1. **Single-file addon** — keep everything in `__init__.py`. If the file grows significantly beyond 2000 lines, consider splitting into a package structure
2. **Operator naming** — `BVCS_OT_<ActionName>` for operators, `BVCS_PT_<PanelName>` for panels
3. **Preferences access** — always use `get_prefs(context)` helper, never access addon preferences directly
4. **Error reporting** — use `self.report({'ERROR'}, msg)` in operators for user-visible errors
5. **Logging** — use the `logger` instance (BVCS logger) for debug/info/error output
6. **Global state** — minimize globals. Use `bpy.context.window_manager` properties for runtime state
7. **Registration** — all classes must be registered in `register()` and unregistered in `unregister()`

## Security Rules

1. **JWT token** — stored in addon preferences (persisted in Blender's user prefs). Cleared on logout
2. **S3 credentials** — fetched from backend, stored in preferences. Never hardcoded. Cleared on logout
3. **No secrets in source** — S3 keys, API keys, and passwords must never appear in the source code
4. **URL validation** — validate URLs before opening in browser (see `BVCS_OT_OpenSignupPage`)
5. **Request timeouts** — always set timeouts on HTTP requests to prevent Blender from freezing
6. **Temp file cleanup** — clean up temp directories to avoid leaking data on shared machines

## Testing Guidelines

Testing is not yet set up but should follow these patterns when implemented:

- **Unit tests**: Use `unittest` with mocked `bpy` module (bpy is not available outside Blender)
- **Mock strategy**: Create mock classes for `bpy.types.Operator`, `bpy.types.Panel`, `bpy.props`
- **Network mocking**: Use `unittest.mock.patch` to mock `requests.get/post` calls
- **S3 mocking**: Mock `boto3` client or use `moto` library for S3 simulation
- **Key scenarios to test**: login flow, project creation, commit/push, conflict detection
- **Integration testing**: Run against a local backend + MinIO instance with Blender in background mode (`blender --background --python test_script.py`)

## Distribution

- The addon is packaged as `export/blender_vcs.zip` for users to install via Blender preferences
- After making changes to `blender_vcs/__init__.py`, rebuild the ZIP:
  ```bash
  cd export && zip -r blender_vcs.zip blender_vcs/
  ```
- Install guide: `export/README.md`
