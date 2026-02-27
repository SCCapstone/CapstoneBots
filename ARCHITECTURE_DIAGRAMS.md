# Storage System Architecture Diagram

## Component Relationships

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FastAPI Application                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────┐ │
│  │  /api/projects     │  │  /api/projects     │  │ /api/projects  │ │
│  │  (projects.py)     │  │  (storage.py)      │  │ (users.py)     │ │
│  └────────┬───────────┘  └────────┬───────────┘  └────────┬───────┘ │
│           │                       │                        │         │
│  ┌────────▼───────────────────────▼──────────────────────────┐       │
│  │              Project & Commit Management                   │       │
│  │  - GET/POST projects                                       │       │
│  │  - GET/POST/PUT commits                                    │       │
│  │  - GET branches                                            │       │
│  └────────┬───────────────────────┬──────────────────────────┘       │
│           │                       │                                  │
│  ┌────────▼──────────┐  ┌────────▼──────────────┐                    │
│  │ Database Layer    │  │ Storage Services      │                    │
│  │ (SQLAlchemy ORM)  │  │ (StorageService)      │                    │
│  │                   │  │                       │                    │
│  │ - Projects        │  │ ✅ Upload objects    │                    │
│  │ - Commits         │  │ ✅ Download commits  │                    │
│  │ - BlenderObjects  │  │ ✅ Compute hashes    │                    │
│  │ - Branches        │  │ ✅ Manage paths      │                    │
│  │ - ObjectLocks     │  │ ✅ Statistics        │                    │
│  │ - MergeConflicts  │  │                       │                    │
│  └────────┬──────────┘  └────────┬──────────────┘                    │
│           │                      │                                   │
│  ┌────────▼──────────────────────▼─────────────────┐                 │
│  │           PostgreSQL Database                    │                 │
│  │  Projects, Commits, Objects, Locks, Conflicts   │                 │
│  └────────────────────────────────────────────────┘                  │
│                                                                        │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │              Storage Utilities Layer                        │      │
│  │  ┌──────────────┐ ┌─────────────────┐ ┌───────────────┐   │      │
│  │  │ StorageUtils │ │ DeduplicationMgr│ │VersioningMgr  │   │      │
│  │  │              │ │                 │ │               │   │      │
│  │  │ - Path ops   │ │ - Hash tracking │ │ - Version tags│   │      │
│  │  │ - Hashing    │ │ - Dedup check   │ │ - Ranges      │   │      │
│  │  │ - Validation │ │ - Savings calc  │ │ - Parsing     │   │      │
│  │  │ - Formatting │ │                 │ │               │   │      │
│  │  └──────────────┘ └─────────────────┘ └───────────────┘   │      │
│  └────────────────────────────────────────────────────────────┘      │
└──────────────────────┬────────────────────────────────────────────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  MinIO / S3     │
              │  Object Storage │
              └────────┬────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
   ┌────────┐    ┌───────┐    ┌─────────────┐
   │Objects │    │Versions│   │Deduplication│
   │ Store  │    │ Store  │   │  Index      │
   └────────┘    └───────┘    └─────────────┘

   projects/{id}/objects/{id}/{hash}.json       (JSON metadata)
   projects/{id}/objects/{id}/mesh-data/{hash}  (Binary mesh)
   projects/{id}/versions/{ts}_{hash}.blend     (Full snapshot)
   projects/dedup/{hash}.json                   (Deduplicated)
```

## Data Flow: Creating a Commit

```
Blender Addon / Frontend
          │
          ▼
┌──────────────────────────┐
│ POST /api/projects/{id}/ │
│      commits             │
│                          │
│ - Objects with JSON data │
│ - Optional mesh data     │
│ - Optional .blend file   │
└──────────────┬───────────┘
               │
               ▼
    ┌─────────────────────┐
    │ Validate & Authorize │
    │ - Check project      │
    │ - Check auth         │
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────┐
    │ Generate Commit Hash │
    │ SHA256(contents)     │
    └──────────┬───────────┘
               │
        ┌──────┴──────┐
        │             │
        ▼             ▼
   ┌────────┐   ┌────────────────┐
   │DB: Add │   │For Each Object │
   │Commit  │   └────────┬───────┘
   │Record  │            │
   └────────┘      ┌─────▼─────────────────┐
                   │ Compute blob_hash     │
                   │ SHA256(json_data)     │
                   └─────┬──────┬──────────┘
                         │      │
                    ┌────▼─┐ ┌──▼─────────────┐
                    │NEW?  │ │ Duplicate?     │
                    └────┬─┘ │ Check history  │
                         │   └──┬─────────────┘
                    ┌────▼──────▼──────┐
                    │ Upload to Storage│
                    │ MinIO.put_object │
                    │ (JSON + Mesh)    │
                    └────┬─────────────┘
                         │
                         ▼
            ┌──────────────────────────┐
            │ DB: Add BlenderObject    │
            │ with storage paths       │
            └────┬─────────────────────┘
                 │
                 ▼
         ┌──────────────┐
         │ Update Branch│
         │ HEAD pointer │
         └────┬─────────┘
              │
              ▼
      ┌───────────────┐
      │ Commit        │
      │ Transaction   │
      └───┬───────────┘
          │
          ▼
    ┌──────────────┐
    │ Return       │
    │ CommitID &   │
    │ Paths        │
    └──────────────┘
```

## Data Flow: Downloading a Commit

```
Frontend / API Client
          │
          ▼
┌────────────────────────────┐
│ GET /api/projects/{id}/    │
│     commits/{cid}/download │
└────────────┬───────────────┘
             │
             ▼
   ┌─────────────────────┐
   │ Validate & Authorize │
   │ - Check access       │
   └──────────┬───────────┘
              │
              ▼
   ┌──────────────────────┐
   │ Query DB for all     │
   │ BlenderObjects in    │
   │ this commit          │
   └──────────┬───────────┘
              │
              ▼
   ┌──────────────────────┐
   │ For each object:     │
   │ - Read JSON path     │
   │ - Read mesh path     │
   └──────────┬───────────┘
              │
        ┌─────▼─────┐
        │ Download  │
        │ from MinIO│
        │ get_obj() │
        └─────┬─────┘
              │
        ┌─────▼─────────────┐
        │ Deserialize JSON  │
        │ (keep mesh binary)│
        └─────┬─────────────┘
              │
              ▼
   ┌──────────────────────┐
   │ Compile complete     │
   │ commit JSON:         │
   │ {                    │
   │   objects: [...]     │
   │   metadata: {...}    │
   │ }                    │
   └──────────┬───────────┘
              │
              ▼
   ┌──────────────────────┐
   │ Stream download to   │
   │ client as JSON file  │
   │ (200 OK)             │
   └──────────────────────┘
```

## Storage Efficiency: Deduplication

```
Without Deduplication:
═══════════════════════

Commit 1: Upload Cube      → 2 KB
Commit 2: Upload Cube      → 2 KB (same, but uploaded again)
Commit 3: Upload Cube      → 2 KB (same, but uploaded again)

Total Storage: 6 KB
Efficiency: 33% (1 unique / 3 copies)


With Deduplication:
═══════════════════════

Commit 1:
  - Compute hash: "abc123def456"
  - Upload: projects/123/objects/456/abc123.json (2 KB)
  - Register: dedup_manager["abc123"] = path

Commit 2:
  - Compute hash: "abc123def456" (same!)
  - Check: hash exists? YES
  - Reuse: projects/123/objects/456/abc123.json (from dedup)
  - No upload needed

Commit 3:
  - Compute hash: "abc123def456" (same!)
  - Check: hash exists? YES
  - Reuse: projects/123/objects/456/abc123.json (from dedup)
  - No upload needed

Total Storage: 2 KB
Efficiency: 100% (1 unique / 3 references)
Savings: 66% (4 KB saved)
```

## Class Hierarchy

```
StorageService (Main Service)
├── Manages MinIO client connection
├── Handles all S3 operations
├── Logging and error handling
└── Methods:
    ├── Path generation (get_*_path)
    ├── Upload operations (upload_*)
    ├── Download operations (download_*)
    ├── Deduplication (compute_blob_hash)
    ├── Existence checks (object_exists)
    ├── Size retrieval (get_object_size)
    ├── Batch operations (list_*, delete_*)
    └── Statistics (estimate_project_storage)

StorageUtils (Static Utilities)
├── compute_content_hash() → SHA256
├── compute_commit_hash() → SHA256
├── validate_object_type() → bool
├── parse_storage_path() → Dict
├── format_file_size() → str
├── validate_json_data() → (bool, Optional[str])
└── create_metadata() → Dict

DeduplicationManager (Dedup Tracking)
├── _hash_index: Dict[blob_hash -> path]
├── should_store_separately() → bool
├── register_hash() → None
├── get_duplicate_path() → Optional[str]
└── calculate_savings() → Dict

VersioningHelper (Version Management)
├── create_version_tag() → str
├── parse_version_tag() → Dict
└── get_version_range() → str

StorageCompression (Compression Utilities)
├── compress_json() → bytes
└── decompress_json() → Dict
```

## Dependency Injection

```
FastAPI Dependency Chain:
═════════════════════════

get_current_user(token)
    ↓
    Returns: User (authenticated)

get_db()
    ↓
    Returns: AsyncSession (database)

get_storage_service()
    ↓
    Returns: StorageService (singleton)
             └── Connected to MinIO

Endpoint Example:
───────────────
@router.post("/commits")
async def create_commit(
    data: CommitCreateRequest,
    db: AsyncSession = Depends(get_db),                ✅
    storage: StorageService = Depends(get_storage_service),  ✅
    current_user: User = Depends(get_current_user)    ✅
):
    # All dependencies injected and ready
    storage.upload_object_json(...)
    db.add(...)
    ...
```

## Error Handling Flow

```
Storage Operation
      │
      ▼
  Try upload
      │
   ┌──┴──┐
   │     │
Success  S3Error
   │     │
   ├─────┤
   │     ├─► NoSuchBucket
   │     │   └─► Create bucket
   │     │
   │     ├─► NoSuchKey
   │     │   └─► Fallback to default
   │     │
   │     ├─► AccessDenied
   │     │   └─► Log & Return 403
   │     │
   │     └─► Other S3Error
   │         └─► Log & Return 500
   │
   ├─► Network Error
   │   └─► Log & Return 503
   │
   └─► Exception
       └─► Log & Return 500
```

---

This architecture provides:
- ✅ Scalability through S3-compatible storage
- ✅ Efficiency through deduplication
- ✅ Reliability through error handling
- ✅ Security through access control
- ✅ Maintainability through layered design

**Last Updated**: February 2026
