# Storage System - Quick Reference Guide

## Overview

The storage system handles all file operations for Blender projects in CapstoneBots using MinIO (S3-compatible) object storage.

## Key Classes & Functions

### StorageService (Core Service)

```python
from storage.storage_service import get_storage_service

storage = get_storage_service()  # Get singleton instance

# Path generation
json_path = storage.get_object_json_path(project_id, object_id, commit_hash)
mesh_path = storage.get_object_mesh_path(project_id, object_id, commit_hash)
snapshot_path = storage.get_snapshot_path(project_id, commit_hash, timestamp)

# Uploads
json_path = storage.upload_object_json(project_id, object_id, commit_hash, json_data)
mesh_path = storage.upload_object_mesh(project_id, object_id, commit_hash, mesh_bytes)
snapshot_path = storage.upload_snapshot(project_id, commit_hash, timestamp, blend_bytes)

# Downloads
json_data = storage.download_object_json(path)
mesh_bytes = storage.download_object_mesh(path)
blend_bytes = storage.download_snapshot(path)

# Deduplication
blob_hash = storage.compute_blob_hash(data)  # SHA256
exists = storage.object_exists(path)
size = storage.get_object_size(path)

# Statistics
versions = storage.list_project_versions(project_id)
objects = storage.list_project_objects(project_id)
stats = storage.estimate_project_storage(project_id)
```

### StorageUtils (Utilities)

```python
from storage.storage_utils import StorageUtils

# Path and hash operations
hash = StorageUtils.compute_content_hash(data)
parsed = StorageUtils.parse_storage_path("projects/{id}/objects/...")
is_valid = StorageUtils.validate_object_type("MESH")

# Metadata and validation
is_valid, error = StorageUtils.validate_json_data(json_dict)
metadata = StorageUtils.create_metadata("Cube", "MESH", custom_field="value")

# Formatting
size_str = StorageUtils.format_file_size(1048576)  # "1.00 MB"
```

### DeduplicationManager (Dedup Tracking)

```python
from storage.storage_utils import DeduplicationManager

dedup = DeduplicationManager(storage)

# Check and register
if dedup.should_store_separately(blob_hash):
    path = storage.upload_object_json(...)
    dedup.register_hash(blob_hash, path)
else:
    path = dedup.get_duplicate_path(blob_hash)

# Calculate savings
savings = dedup.calculate_savings(total_size, actual_stored)
print(f"Saved {savings['percent_saved']}%")
```

### VersioningHelper (Version Management)

```python
from storage.storage_utils import VersioningHelper

# Version tagging
tag = VersioningHelper.create_version_tag(commit_hash, timestamp_str)
components = VersioningHelper.parse_version_tag(tag)

# Version ranges
range_str = VersioningHelper.get_version_range(start_hash, end_hash)
```

## API Endpoints

### Upload Object
```
POST /api/projects/{project_id}/objects/upload

Query Parameters:
  object_id: UUID
  commit_hash: str
  object_name: str
  object_type: str

Files:
  json_file: application/json
  mesh_file: application/octet-stream (optional)

Returns: {object_id, object_name, object_type, json_path, mesh_path, blob_hash, sizes}
```

### Download Commit
```
GET /api/projects/{project_id}/commits/{commit_id}/download

Returns: JSON file with all objects in commit
```

### Version History
```
GET /api/projects/{project_id}/versions?limit=50

Returns: List of commits with snapshot info
```

### Storage Stats
```
GET /api/projects/{project_id}/storage-stats

Returns: {total_bytes, objects_bytes, versions_bytes, total_mb}
```

### Create Snapshot
```
POST /api/projects/{project_id}/commits/{commit_id}/snapshot

File: .blend file

Returns: {snapshot_path, file_size}
```

## Storage Structure

```
projects/
├── {project_id}/
│   ├── objects/
│   │   └── {object_id}/
│   │       ├── {commit_hash}.json
│   │       └── mesh-data/{commit_hash}.bin
│   ├── versions/
│   │   └── {timestamp}_{commit_hash}.blend
│   ├── metadata/
│   │   └── {project_id}.json
│   └── dedup/
│       └── {blob_hash}.json
└── dedup/
    └── {blob_hash}.json
```

## Common Workflows

### Upload a Commit

```python
from storage.storage_service import get_storage_service

storage = get_storage_service()

for obj in commit_objects:
    # Upload JSON metadata
    json_path = storage.upload_object_json(
        project_id, obj['object_id'], commit_hash, obj['json_data']
    )
    
    # Upload mesh if available
    if obj['mesh_data']:
        mesh_path = storage.upload_object_mesh(
            project_id, obj['object_id'], commit_hash, obj['mesh_data']
        )
```

### Download a Commit

```python
# Query objects from database
objects = await db.execute(
    select(BlenderObject).where(BlenderObject.commit_id == commit_id)
)

# Download from storage
commit_data = {"objects": []}
for obj in objects:
    json_data = storage.download_object_json(obj.json_data_path)
    commit_data["objects"].append(json_data)

return commit_data
```

### Check Deduplication

```python
blob_hash = storage.compute_blob_hash(json_data)

if storage.object_exists(dedup_path):
    # Reuse existing
    json_path = dedup_path
else:
    # Upload new
    json_path = storage.upload_object_json(...)
```

### Get Project Storage Stats

```python
stats = storage.estimate_project_storage(project_id)

print(f"Total: {stats['total_mb']}MB")
print(f"Objects: {stats['objects_bytes']} bytes")
print(f"Versions: {stats['versions_bytes']} bytes")
```

## Error Handling

```python
from minio.error import S3Error

try:
    storage.upload_object_json(...)
except S3Error as e:
    if e.code == "NoSuchBucket":
        # Bucket doesn't exist
    elif e.code == "NoSuchKey":
        # Object not found
    else:
        # Other S3 error
        logger.error(f"S3 Error: {e}")
except Exception as e:
    # Network or other error
    logger.error(f"Error: {e}")
```

## Configuration

Required environment variables:

```bash
S3_ENDPOINT=localhost:9000         # MinIO endpoint
S3_ACCESS_KEY=minioadmin           # Access key
S3_SECRET_KEY=minioadmin           # Secret key
S3_SECURE=false                    # Use HTTPS
S3_REGION=us-east-1                # Region
S3_BUCKET=capstonebots             # Bucket name
```

## Performance Tips

1. **Batch Operations**: Group uploads/downloads when possible
2. **Deduplication**: Check for duplicates before uploading
3. **Streaming**: Use streaming responses for large files
4. **Compression**: Consider GZIP for metadata
5. **Caching**: Cache frequently accessed objects

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Connection refused | Check S3_ENDPOINT is accessible |
| NoSuchKey error | Verify object was uploaded |
| NoSuchBucket error | Bucket doesn't exist or wrong name |
| Permission denied | Check S3_ACCESS_KEY and S3_SECRET_KEY |
| Out of disk space | Archive old versions or increase storage |

## Related Documentation

- [Storage & Versioning System](../STORAGE.md) - Complete guide
- [Integration Examples](./examples.py) - Code examples
- [API Documentation](http://localhost:8000/docs) - Interactive API docs

---

**Last Updated**: February 2026
