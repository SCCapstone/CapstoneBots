# Storage and Versioning System Documentation

## Overview

CapstoneBots implements a sophisticated file routing and object storage system using MinIO (S3-compatible) storage. The system is designed to efficiently handle Blender projects with version control capabilities, similar to Git but optimized for 3D assets.

## Architecture

### Storage Hierarchy

```
s3://bucket/
├── projects/
│   ├── {project_id}/
│   │   ├── versions/
│   │   │   └── {timestamp}_{commit_hash[:8]}.blend
│   │   ├── objects/
│   │   │   └── {object_id}/
│   │   │       ├── {commit_hash}.json          (object metadata)
│   │   │       └── mesh-data/
│   │   │           └── {commit_hash}.bin       (binary mesh data)
│   │   ├── metadata/
│   │   │   └── {project_id}.json
│   │   └── dedup/
│   │       └── {blob_hash}.json                (deduplicated content)
│   └── dedup/                                   (global deduplication)
│       └── {blob_hash}.json
```

### Key Components

#### 1. **StorageService** (`storage/storage_service.py`)
The core service layer managing all MinIO interactions:
- **Path Generation**: Constructs hierarchical storage paths
- **Uploads**: JSON metadata and binary mesh data
- **Downloads**: Retrieves objects by path
- **Deduplication**: Tracks content hashes to avoid duplicates
- **Batch Operations**: List and delete multiple objects
- **Statistics**: Calculate project storage usage

#### 2. **Storage Routes** (`routers/storage.py`)
FastAPI endpoints for file operations:
- Object upload with metadata validation
- Commit downloads with full reconstruction
- Version history viewing
- Storage statistics
- Snapshot management

#### 3. **Storage Utilities** (`storage/storage_utils.py`)
Helper classes and functions:
- **StorageUtils**: Path parsing, hashing, validation
- **DeduplicationManager**: Content deduplication tracking
- **VersioningHelper**: Version tag creation and parsing
- **StorageCompression**: GZIP compression utilities

#### 4. **Schemas** (`schemas.py`)
Pydantic models for storage operations:
- `StorageObjectInfo`: Object metadata
- `ProjectStorageStats`: Storage statistics
- `VersionHistoryResponse`: Version listing
- `CommitDataRequest`: Upload request structure

## API Endpoints

### Object Management

#### Upload Blender Object
```
POST /api/projects/{project_id}/objects/upload
Parameters:
  - object_id: UUID
  - commit_hash: str
  - object_name: str
  - object_type: str (MESH, CAMERA, LIGHT, etc.)
Files:
  - json_file: Object metadata as JSON
  - mesh_file: Optional binary mesh data
```

**Response:**
```json
{
  "object_id": "uuid",
  "object_name": "Cube",
  "object_type": "MESH",
  "json_path": "projects/{project_id}/objects/{object_id}/{commit_hash}.json",
  "mesh_path": "projects/{project_id}/objects/{object_id}/mesh-data/{commit_hash}.bin",
  "blob_hash": "sha256hash",
  "json_size": 2048,
  "mesh_size": 102400
}
```

#### Download Commit
```
GET /api/projects/{project_id}/commits/{commit_id}/download
```

**Response:** Downloads JSON file containing full commit state with all objects

#### Download Single Object
```
GET /api/projects/{project_id}/commits/{commit_id}/objects/{object_id}/download
```

### Version Management

#### Get Version History
```
GET /api/projects/{project_id}/versions?limit=50
```

**Response:**
```json
[
  {
    "commit_id": "uuid",
    "commit_hash": "abc1234f...",
    "commit_message": "Updated lighting",
    "author_id": "user-uuid",
    "committed_at": "2025-12-04T10:30:00",
    "snapshot_path": "projects/{project_id}/versions/{timestamp}_{hash}.blend",
    "snapshot_size": 5242880
  }
]
```

#### Get Storage Statistics
```
GET /api/projects/{project_id}/storage-stats
```

**Response:**
```json
{
  "project_id": "uuid",
  "total_bytes": 1048576,
  "objects_bytes": 819200,
  "versions_bytes": 229376,
  "total_mb": 1.0
}
```

#### Create Snapshot
```
POST /api/projects/{project_id}/commits/{commit_id}/snapshot
File: .blend file to backup
```

## Data Flow

### Creating a Commit

```
1. Client sends CommitCreateRequest
   ├── Branch ID
   ├── Author ID
   ├── Commit message
   └── List of Blender objects with data

2. Backend receives request
   ├── Validates project & branch exist
   ├── Creates Commit record in DB
   └── Flushes to get commit_id

3. For each Blender object:
   ├── Computes blob_hash from JSON
   ├── Checks if identical content exists
   ├── Uploads JSON metadata to storage
   ├── Uploads binary mesh data (if exists)
   ├── Creates BlenderObject record with storage paths
   └── Registers blob_hash for deduplication

4. Updates Branch.head_commit_id
5. Commits transaction
```

### Retrieving a Commit

```
1. Client requests download of commit_{commit_id}

2. Backend:
   ├── Verifies commit exists
   ├── Checks user authorization
   ├── Queries all objects in commit
   └── For each object:
       ├── Downloads JSON from storage
       ├── Includes mesh reference (if exists)
       └── Adds to response

3. Returns complete commit as JSON file
```

## Deduplication Strategy

### How It Works

1. **Hash Calculation**: Each object's JSON is hashed using SHA256
2. **Hash Comparison**: Check if hash exists in dedup index
3. **Path Reuse**: If identical, reference existing path instead of uploading
4. **Database Tracking**: `blob_hash` field enables dedup verification

### Example

```python
# Two commits with identical "Cube" object
commit_1: Cube -> blob_hash: abc123def456
commit_2: Cube -> blob_hash: abc123def456 (same)

# Storage:
projects/{id}/objects/{obj_id}/abc123def456.json  # Only stored once!

# Database:
- Commit 1's Cube: blob_hash=abc123def456, json_data_path=...
- Commit 2's Cube: blob_hash=abc123def456, json_data_path=... (same)
```

### Savings Calculation

```python
stats = storage.estimate_project_storage(project_id)
savings = (total_size - actual_stored) / total_size * 100
# Example: 1GB total, 500MB stored = 50% savings
```

## Performance Considerations

### Path Structure Benefits

1. **Hierarchical Organization**: Easy to browse and manage
2. **Project Isolation**: All project data in one prefix
3. **Fast Listing**: Can list objects by project/type without full scan
4. **Batch Operations**: Delete entire project with one prefix operation

### Deduplication Benefits

1. **Storage Efficiency**: Identical objects stored only once
2. **Bandwidth Savings**: Avoid uploading duplicate data
3. **Consistency**: Same content always has same hash

### Large File Handling

1. **Streaming**: Downloads use streaming responses
2. **Chunked Uploads**: Support for large mesh files
3. **Compression**: Optional GZIP for metadata

## Integration with Version Control

### Commit Hashing

```python
commit_hash = SHA256(
    project_id + branch_id + author_id + message + timestamp
)
```

Uses commit hash to:
- Uniquely identify commits
- Version storage paths
- Detect duplicate commits
- Build commit lineage

### Branch Management

- Each branch maintains `head_commit_id`
- Commits form parent-child chain via `parent_commit_id`
- Enables history traversal and merge operations

## Error Handling

### Upload Failures

```python
try:
    storage.upload_object_json(project_id, object_id, commit_hash, json_data)
except S3Error as e:
    logger.error(f"Upload failed: {e}")
    # Rollback transaction / cleanup
```

### Download Failures

```python
try:
    json_data = storage.download_object_json(path)
except S3Error as e:
    if e.code == "NoSuchKey":
        raise HTTPException(status_code=404, detail="Object not found")
```

## Configuration

The storage system is S3-compatible and works with both **AWS S3** (production) and **MinIO** (local development).

### AWS S3 (Production)

Set these environment variables in your `.env` or `docker-compose.yml`:

```bash
S3_ENDPOINT=https://s3.us-east-1.amazonaws.com
S3_ACCESS_KEY=<your-aws-access-key>
S3_SECRET_KEY=<your-aws-secret-key>
S3_SECURE=true
S3_BUCKET=blender-vcs-prod
```

> The bucket must already exist in your AWS account. The backend will not create buckets on AWS automatically.

### MinIO (Local Development)

If you prefer local storage, the `docker-compose.yml` includes a MinIO service:

```bash
S3_ENDPOINT=http://minio:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_SECURE=false
S3_BUCKET=capstonebots
```

The MinIO web console is available at [http://localhost:9001](http://localhost:9001) (login: `minioadmin` / `minioadmin`).

### Switching Between S3 and MinIO

The `docker-compose.yml` defaults to AWS S3. To use local MinIO instead, override the S3 variables in your `.env`:

```env
S3_ENDPOINT=http://minio:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_SECURE=false
S3_BUCKET=capstonebots
```

Or pass them directly to `docker compose`:

```bash
S3_ENDPOINT=http://minio:9000 S3_ACCESS_KEY=minioadmin S3_SECRET_KEY=minioadmin S3_SECURE=false S3_BUCKET=capstonebots docker compose up --build
```

## Usage Examples

### Upload with Mesh Data

```python
from storage.storage_service import get_storage_service

storage = get_storage_service()

# Upload object JSON
json_path = storage.upload_object_json(
    project_id=project_uuid,
    object_id=object_uuid,
    commit_hash="abc123...",
    json_data={"name": "Cube", "transform": [...]}
)

# Upload mesh
mesh_path = storage.upload_object_mesh(
    project_id=project_uuid,
    object_id=object_uuid,
    commit_hash="abc123...",
    mesh_data=binary_mesh_bytes
)
```

### Check Deduplication

```python
blob_hash = storage.compute_blob_hash(json_data)

if storage.object_exists(dedup_path := storage.get_dedup_path(blob_hash)):
    # Reuse existing file
    storage_path = dedup_path
else:
    # Upload new file
    storage_path = storage.upload_object_json(...)
```

### Get Storage Stats

```python
stats = storage.estimate_project_storage(project_uuid)
print(f"Total: {stats['total_mb']}MB")
print(f"Objects: {stats['objects_bytes']} bytes")
print(f"Versions: {stats['versions_bytes']} bytes")
```

## Security Considerations

1. **Access Control**: All endpoints require authentication
2. **Project Isolation**: Users can only access their own projects
3. **Path Traversal**: Paths are constructed server-side, not user input
4. **Object Size Limits**: Should be enforced at API level (nginx/load balancer)

## Monitoring

### Key Metrics to Track

1. **Upload Count**: Objects uploaded per project
2. **Download Count**: Retrieval patterns
3. **Storage Size**: Total and per-project usage
4. **Deduplication Ratio**: Duplicate elimination effectiveness
5. **Error Rate**: Failed operations

### Logging

All operations are logged via Python's logging module:

```python
logger.info(f"Uploaded object JSON: {path}")
logger.error(f"Error uploading: {e}")
```

## Future Enhancements

1. **Versioning Policies**: Auto-archive old versions
2. **Compression**: Automatic GZIP for JSON
3. **Encryption**: At-rest and in-transit encryption
4. **Retention**: Configurable cleanup of old snapshots
5. **CDN Integration**: Cache frequently accessed objects
6. **Search**: Index and search object metadata

## Troubleshooting

### MinIO Connection Errors

```
Error: Connection refused
Solution: Verify S3_ENDPOINT is accessible
```

### Path Not Found

```
Error: NoSuchKey
Solution: Verify object was uploaded before attempting download
```

### Quota Exceeded

```
Error: Out of disk space
Solution: Archive old versions or increase storage capacity
```

---

**Documentation Last Updated**: February 2026
**API Version**: 1.0.0
