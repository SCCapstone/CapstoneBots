"""
Storage Integration Examples

Demonstrates how to use the StorageService and related utilities
in real application scenarios.
"""

from uuid import UUID, uuid4
from datetime import datetime
import json

from storage.storage_service import StorageService, get_storage_service
from storage.storage_utils import StorageUtils, DeduplicationManager, VersioningHelper


# ============== Example 1: Uploading a Commit with Objects ==============

def example_upload_commit():
    """
    Example: Upload a complete commit with multiple Blender objects.
    This is called when a user creates a commit from the Blender addon.
    """
    
    # Get storage service
    storage = get_storage_service()
    
    # Project and commit info
    project_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    commit_hash = "abc1234f5678def90ab12cd34ef567890abcdef1"
    timestamp = datetime.now()
    
    # Create sample Blender objects
    objects_to_upload = [
        {
            "object_id": uuid4(),
            "object_name": "Cube",
            "object_type": "MESH",
            "json_data": {
                "name": "Cube",
                "type": "MESH",
                "transform": {
                    "location": [0, 0, 0],
                    "rotation": [0, 0, 0],
                    "scale": [1, 1, 1]
                },
                "vertices": [...],  # Simplified
                "faces": [...]
            },
            "mesh_data": b"binary mesh data here..."
        },
        {
            "object_id": uuid4(),
            "object_name": "Light",
            "object_type": "LIGHT",
            "json_data": {
                "name": "Light",
                "type": "LIGHT",
                "light_type": "SUN",
                "energy": 2.0,
                "transform": {...}
            },
            "mesh_data": None  # Lights don't have mesh data
        }
    ]
    
    # Upload each object
    for obj in objects_to_upload:
        # Upload JSON metadata
        json_path = storage.upload_object_json(
            project_id=project_id,
            object_id=obj["object_id"],
            commit_hash=commit_hash,
            json_data=obj["json_data"]
        )
        print(f"✓ Uploaded {obj['object_name']} metadata: {json_path}")
        
        # Upload mesh if available
        if obj["mesh_data"]:
            mesh_path = storage.upload_object_mesh(
                project_id=project_id,
                object_id=obj["object_id"],
                commit_hash=commit_hash,
                mesh_data=obj["mesh_data"]
            )
            print(f"✓ Uploaded {obj['object_name']} mesh: {mesh_path}")
    
    # Upload full .blend snapshot for recovery
    blend_snapshot = b"full blend file binary data..."
    snapshot_path = storage.upload_snapshot(
        project_id=project_id,
        commit_hash=commit_hash,
        timestamp=timestamp,
        blend_data=blend_snapshot
    )
    print(f"✓ Uploaded snapshot: {snapshot_path}")


# ============== Example 2: Implementing Deduplication ==============

def example_deduplication():
    """
    Example: Detect and skip uploading duplicate object data.
    This saves storage space when the same object is committed unchanged.
    """
    
    storage = get_storage_service()
    dedup_manager = DeduplicationManager(storage)
    
    project_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    commit_hash_1 = "commit_hash_1"
    commit_hash_2 = "commit_hash_2"
    
    # Object that appears in both commits (unchanged)
    object_json = {
        "name": "Cube",
        "type": "MESH",
        "vertices": [...]
    }
    
    # First commit: Upload the object
    print("--- Commit 1: Upload Cube ---")
    blob_hash = storage.compute_blob_hash(object_json)
    
    if dedup_manager.should_store_separately(blob_hash):
        json_path = storage.upload_object_json(
            project_id=project_id,
            object_id=uuid4(),
            commit_hash=commit_hash_1,
            json_data=object_json
        )
        dedup_manager.register_hash(blob_hash, json_path)
        print(f"✓ Uploaded new object: {json_path}")
    
    # Second commit: Same object, unchanged
    print("\n--- Commit 2: Same Cube (unchanged) ---")
    blob_hash_2 = storage.compute_blob_hash(object_json)
    
    if not dedup_manager.should_store_separately(blob_hash_2):
        # Reuse existing path
        existing_path = dedup_manager.get_duplicate_path(blob_hash_2)
        print(f"✓ Duplicate detected! Reusing: {existing_path}")
        print(f"✓ Saved {len(json.dumps(object_json))} bytes of storage")
    
    # Calculate savings
    total_size = len(json.dumps(object_json)) * 2  # 2 commits
    actual_stored = len(json.dumps(object_json))   # Only 1 stored
    
    savings = dedup_manager.calculate_savings(total_size, actual_stored)
    print(f"\n📊 Deduplication Savings:")
    print(f"   Total size: {savings['total_size']} bytes")
    print(f"   Actual stored: {savings['actual_stored']} bytes")
    print(f"   Saved: {savings['percent_saved']}%")


# ============== Example 3: Downloading a Complete Commit ==============

def example_download_commit():
    """
    Example: Reconstruct and download a complete commit state.
    This is used when a user wants to download a specific version.
    """
    
    storage = get_storage_service()
    
    project_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    
    # Objects in commit (from database query in real scenario)
    objects_in_commit = [
        {
            "object_id": uuid4(),
            "object_name": "Cube",
            "json_data_path": "projects/123.../objects/abc.../commit_hash.json",
            "mesh_data_path": "projects/123.../objects/abc.../mesh-data/commit_hash.bin"
        },
        {
            "object_id": uuid4(),
            "object_name": "Camera",
            "json_data_path": "projects/123.../objects/def.../commit_hash.json",
            "mesh_data_path": None
        }
    ]
    
    # Download each object
    commit_data = {
        "objects": []
    }
    
    for obj in objects_in_commit:
        # Download JSON
        json_data = storage.download_object_json(obj["json_data_path"])
        
        # Download mesh if available
        mesh_data = None
        if obj["mesh_data_path"]:
            try:
                mesh_data = storage.download_object_mesh(obj["mesh_data_path"])
            except Exception as e:
                print(f"⚠️  Warning: Could not download mesh for {obj['object_name']}: {e}")
        
        commit_data["objects"].append({
            "object_name": obj["object_name"],
            "json_data": json_data,
            "mesh_data": mesh_data  # Binary data
        })
        
        print(f"✓ Downloaded {obj['object_name']}")
    
    # Save to file
    with open("downloaded_commit.json", "w") as f:
        # JSON can't contain binary, so we'd handle mesh_data separately
        json.dump({"objects": [
            {k: v for k, v in obj.items() if k != "mesh_data"}
            for obj in commit_data["objects"]
        ]}, f, indent=2)
    
    print(f"✓ Commit data saved to downloaded_commit.json")


# ============== Example 4: Version History with Storage Info ==============

def example_version_history():
    """
    Example: Retrieve version history with storage statistics.
    Shows how to display commit timeline with file sizes.
    """
    
    storage = get_storage_service()
    
    project_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    
    # List all version snapshots (from database in real scenario)
    versions = [
        {
            "commit_id": uuid4(),
            "commit_hash": "abc123defg...",
            "commit_message": "Initial scene setup",
            "committed_at": datetime(2025, 12, 1, 10, 0, 0),
        },
        {
            "commit_id": uuid4(),
            "commit_hash": "def456ghij...",
            "commit_message": "Added lighting",
            "committed_at": datetime(2025, 12, 2, 15, 30, 0),
        },
        {
            "commit_id": uuid4(),
            "commit_hash": "ghi789jklm...",
            "commit_message": "Updated materials",
            "committed_at": datetime(2025, 12, 3, 14, 0, 0),
        }
    ]
    
    # Add storage info to each version
    print("📋 Version History with Storage Information:\n")
    for version in versions:
        snapshot_path = storage.get_snapshot_path(
            project_id,
            version["commit_hash"],
            version["committed_at"]
        )
        
        # Check if snapshot exists and get size
        snapshot_size = None
        try:
            if storage.object_exists(snapshot_path):
                snapshot_size = storage.get_object_size(snapshot_path)
        except:
            pass
        
        # Format for display
        timestamp = version["committed_at"].strftime("%Y-%m-%d %H:%M:%S")
        hash_short = version["commit_hash"][:8]
        message = version["commit_message"]
        
        size_str = f" ({StorageUtils.format_file_size(snapshot_size)})" if snapshot_size else ""
        
        print(f"  {timestamp} | {hash_short} | {message}{size_str}")
    
    # Get total storage stats
    stats = storage.estimate_project_storage(project_id)
    print(f"\n📊 Total Storage: {stats['total_mb']} MB")
    print(f"   Objects: {StorageUtils.format_file_size(stats['objects_bytes'])}")
    print(f"   Versions: {StorageUtils.format_file_size(stats['versions_bytes'])}")


# ============== Example 5: Path Parsing and Utilities ==============

def example_utilities():
    """
    Example: Using storage utilities for common operations.
    """
    
    # Parse a storage path
    path = "projects/123e4567-e89b-12d3-a456-426614174000/objects/abc123/commit_hash.json"
    parsed = StorageUtils.parse_storage_path(path)
    print(f"Parsed path: {parsed}")
    # Output: {'project_id': '123e4567...', 'type': 'object', ...}
    
    # Compute content hash
    data = {"name": "Cube", "type": "MESH"}
    content_hash = StorageUtils.compute_content_hash(data)
    print(f"Content hash: {content_hash}")
    
    # Validate object type
    is_valid = StorageUtils.validate_object_type("MESH")
    print(f"MESH is valid: {is_valid}")  # True
    
    is_valid = StorageUtils.validate_object_type("INVALID")
    print(f"INVALID is valid: {is_valid}")  # False
    
    # Format file size
    size_mb = StorageUtils.format_file_size(1048576)
    print(f"1048576 bytes = {size_mb}")  # 1.00 MB
    
    # Version tagging
    tag = VersioningHelper.create_version_tag("abc123def456", "2025-12-04T10-30-00")
    print(f"Version tag: {tag}")  # v_2025-12-04T10-30-00_abc123de
    
    # Version range
    range_str = VersioningHelper.get_version_range("abc123def456", "xyz789uvwxyz")
    print(f"Version range: {range_str}")  # abc123de..xyz789uv


# ============== Example 6: Error Handling ==============

def example_error_handling():
    """
    Example: Proper error handling for storage operations.
    """
    
    storage = get_storage_service()
    project_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    object_id = uuid4()
    commit_hash = "abc123..."
    
    # Try uploading with error handling
    try:
        json_data = {"name": "Cube", "type": "MESH"}
        json_path = storage.upload_object_json(
            project_id, object_id, commit_hash, json_data
        )
        print(f"✓ Upload succeeded: {json_path}")
    except Exception as e:
        print(f"✗ Upload failed: {e}")
        # Cleanup, log, notify user
    
    # Try downloading with fallback
    try:
        data = storage.download_object_json("invalid/path.json")
    except Exception as e:
        print(f"⚠️  Download failed: {e}")
        # Use cached version or return error
    
    # Check existence before download
    path = "projects/.../some_object.json"
    if storage.object_exists(path):
        data = storage.download_object_json(path)
        print("✓ Object exists and downloaded")
    else:
        print("ℹ️  Object not found in storage")


if __name__ == "__main__":
    print("=" * 60)
    print("Storage Integration Examples")
    print("=" * 60)
    
    print("\n1️⃣  Uploading a Commit with Objects")
    print("-" * 60)
    # example_upload_commit()
    print("(Disabled - requires MinIO running)")
    
    print("\n2️⃣  Deduplication Example")
    print("-" * 60)
    # example_deduplication()
    print("(Disabled - requires MinIO running)")
    
    print("\n3️⃣  Downloading a Complete Commit")
    print("-" * 60)
    # example_download_commit()
    print("(Disabled - requires MinIO running)")
    
    print("\n4️⃣  Version History")
    print("-" * 60)
    # example_version_history()
    print("(Disabled - requires MinIO running)")
    
    print("\n5️⃣  Utilities Examples")
    print("-" * 60)
    example_utilities()
    
    print("\n6️⃣  Error Handling")
    print("-" * 60)
    example_error_handling()
    
    print("\n" + "=" * 60)
    print("Examples completed!")
    print("=" * 60)
