# Integration Guide: Adding Storage to Commit Workflow

## Overview

This guide explains how to integrate the new StorageService into the existing commit creation and retrieval workflow in the projects router.

## Current Commit Workflow

The current `create_commit` endpoint in `routers/projects.py`:

```python
@router.post("/{project_id}/commits", response_model=CommitResponse)
async def create_commit(
    project_id: UUID,
    data: CommitCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    # 1. Validate branch exists
    # 2. Generate commit hash
    # 3. Create Commit record in DB
    # 4. Create BlenderObject records (with file_path references)
    # 5. Update branch HEAD
    # 6. Commit transaction
```

## Integration Steps

### Step 1: Update CommitCreateRequest Schema

**Current:**
```python
class CommitCreateRequest(BaseModel):
    branch_id: UUID
    author_id: UUID
    commit_message: str
    objects: List[BlenderObjectCreate]

class BlenderObjectCreate(BaseModel):
    object_name: str
    object_type: str
    json_data_path: str          # ❌ Just a path
    mesh_data_path: Optional[str]
    blob_hash: str
```

**Updated:**
```python
class BlenderObjectCreate(BaseModel):
    object_name: str
    object_type: str
    json_data: Dict[str, Any]     # ✅ Actual JSON data
    mesh_data: Optional[bytes]    # ✅ Actual binary data
    blob_hash: Optional[str]      # Will be computed if not provided

class CommitCreateRequest(BaseModel):
    branch_id: UUID
    author_id: UUID
    commit_message: str
    objects: List[BlenderObjectCreate]
    include_snapshot: bool = False  # Optional full .blend backup
```

### Step 2: Update create_commit Endpoint

**Enhanced implementation:**

```python
from storage.storage_service import StorageService, get_storage_service

@router.post("/{project_id}/commits", response_model=CommitResponse, status_code=status.HTTP_201_CREATED)
async def create_commit(
    project_id: UUID,
    data: CommitCreateRequest,
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),  # ✅ NEW
    current_user: User = Depends(get_current_user)           # ✅ NEW
):
    """
    Create a new commit with Blender objects.
    
    Enhanced to:
    1. Validate user owns project
    2. Upload object data to MinIO
    3. Store paths in database
    4. Support optional full snapshot
    """
    
    # 1. Verify project exists and user owns it
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.owner_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # 2. Verify branch exists
    branch = await db.get(Branch, data.branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    
    # 3. Generate commit hash (deterministic based on content)
    commit_content = json.dumps({
        "project_id": str(project_id),
        "branch_id": str(data.branch_id),
        "author_id": str(data.author_id),
        "message": data.commit_message,
        "objects": [
            {
                "name": obj.object_name,
                "type": obj.object_type,
                "data_hash": hashlib.sha256(
                    json.dumps(obj.json_data, sort_keys=True).encode()
                ).hexdigest()
            }
            for obj in data.objects
        ]
    }, sort_keys=True)
    commit_hash = hashlib.sha256(commit_content.encode()).hexdigest()
    
    # 4. Create Commit record
    new_commit = Commit(
        project_id=project_id,
        branch_id=data.branch_id,
        parent_commit_id=branch.head_commit_id,
        author_id=data.author_id,
        commit_message=data.commit_message,
        commit_hash=commit_hash,
        committed_at=datetime.utcnow()
    )
    db.add(new_commit)
    await db.flush()  # Get commit_id
    
    # 5. Upload objects to storage and create BlenderObject records
    for obj_data in data.objects:
        # Compute blob hash for deduplication
        blob_hash = obj_data.blob_hash or storage.compute_blob_hash(obj_data.json_data)
        
        # Upload JSON metadata
        json_path = storage.upload_object_json(
            project_id=project_id,
            object_id=uuid4(),  # Or get from obj_data if provided
            commit_hash=commit_hash,
            json_data=obj_data.json_data
        )
        
        # Upload mesh if provided
        mesh_path = None
        if obj_data.mesh_data:
            mesh_path = storage.upload_object_mesh(
                project_id=project_id,
                object_id=uuid4(),
                commit_hash=commit_hash,
                mesh_data=obj_data.mesh_data
            )
        
        # Create BlenderObject record with storage paths
        blender_obj = BlenderObject(
            commit_id=new_commit.commit_id,
            object_name=obj_data.object_name,
            object_type=obj_data.object_type,
            json_data_path=json_path,
            mesh_data_path=mesh_path,
            blob_hash=blob_hash
        )
        db.add(blender_obj)
    
    # 6. Optionally upload full snapshot
    if data.include_snapshot and 'snapshot_file' in request.files:
        snapshot_data = await request.files['snapshot_file'].read()
        snapshot_path = storage.upload_snapshot(
            project_id=project_id,
            commit_hash=commit_hash,
            timestamp=datetime.utcnow(),
            blend_data=snapshot_data
        )
    
    # 7. Update branch HEAD
    branch.head_commit_id = new_commit.commit_id
    
    # 8. Commit transaction
    await db.commit()
    await db.refresh(new_commit)
    
    return new_commit
```

### Step 3: Update get_commit_objects Endpoint

**Current implementation should work, but enhance with size info:**

```python
@router.get("/{project_id}/commits/{commit_id}/objects", response_model=List[BlenderObjectResponse])
async def get_commit_objects(
    project_id: UUID,
    commit_id: UUID,
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),  # ✅ NEW
):
    """
    Get all Blender objects in a commit with storage info.
    """
    result = await db.execute(
        select(BlenderObject).where(BlenderObject.commit_id == commit_id)
    )
    objects = result.scalars().all()
    
    # Enhance response with storage info
    enhanced_objects = []
    for obj in objects:
        response = {
            "object_id": obj.object_id,
            "object_name": obj.object_name,
            "object_type": obj.object_type,
            "json_data_path": obj.json_data_path,
            "mesh_data_path": obj.mesh_data_path,
            "blob_hash": obj.blob_hash,
            "created_at": obj.created_at,
            # ✅ Add storage info
            "json_size": storage.get_object_size(obj.json_data_path),
            "mesh_size": storage.get_object_size(obj.mesh_data_path) if obj.mesh_data_path else None,
        }
        enhanced_objects.append(response)
    
    return enhanced_objects
```

### Step 4: Add Merge Detection

When merging branches, check for conflicts using storage:

```python
@router.post("/{project_id}/branches/{target_branch_id}/merge/{source_branch_id}")
async def merge_branches(
    project_id: UUID,
    target_branch_id: UUID,
    source_branch_id: UUID,
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
):
    """
    Merge source branch into target branch.
    
    Uses stored object hashes to detect conflicts.
    """
    
    # Get latest commits from both branches
    source_commit = await db.get(Commit, source_branch.head_commit_id)
    target_commit = await db.get(Commit, target_branch.head_commit_id)
    
    # Get objects from both branches
    source_objects = await db.execute(
        select(BlenderObject).where(BlenderObject.commit_id == source_commit.commit_id)
    )
    target_objects = await db.execute(
        select(BlenderObject).where(BlenderObject.commit_id == target_commit.commit_id)
    )
    
    # Compare blob hashes to find conflicts
    source_hashes = {obj.object_name: obj.blob_hash for obj in source_objects}
    target_hashes = {obj.object_name: obj.blob_hash for obj in target_objects}
    
    conflicts = []
    for obj_name, source_hash in source_hashes.items():
        if obj_name in target_hashes:
            if source_hash != target_hashes[obj_name]:
                # Conflict: same object modified differently
                conflicts.append({
                    "object_name": obj_name,
                    "source_hash": source_hash,
                    "target_hash": target_hashes[obj_name]
                })
    
    if conflicts:
        # Create MergeConflict records
        for conflict in conflicts:
            db.add(MergeConflict(
                project_id=project_id,
                source_commit_id=source_commit.commit_id,
                target_branch_id=target_branch_id,
                object_name=conflict["object_name"],
                conflict_type="MODIFY_MODIFY"
            ))
    
    # ... rest of merge logic
```

## Migration Checklist

- [ ] Update `CommitCreateRequest` schema to accept `json_data` and `mesh_data`
- [ ] Add `StorageService` dependency to `create_commit` endpoint
- [ ] Implement object upload in `create_commit` before creating DB records
- [ ] Update `get_commit_objects` to include storage metadata
- [ ] Add `storage` router to `main.py` imports
- [ ] Update `BlenderObjectCreate` schema documentation
- [ ] Add tests for storage integration
- [ ] Update Blender addon to send raw data instead of paths
- [ ] Test with MinIO running locally
- [ ] Deploy MinIO to production environment

## Error Handling

Add proper error handling for storage operations:

```python
try:
    json_path = storage.upload_object_json(...)
except S3Error as e:
    # Rollback: delete previously uploaded objects
    for uploaded_path in uploaded_paths:
        try:
            storage.delete_object(uploaded_path)
        except:
            pass  # Log but continue cleanup
    
    # Rollback transaction
    await db.rollback()
    
    raise HTTPException(
        status_code=500,
        detail=f"Failed to upload object data: {str(e)}"
    )
except Exception as e:
    await db.rollback()
    logger.error(f"Unexpected error during commit: {e}")
    raise HTTPException(status_code=500, detail="Internal server error")
```

## Testing

Unit test example:

```python
@pytest.mark.asyncio
async def test_create_commit_with_storage():
    """Test creating commit with file uploads"""
    
    # Mock storage service
    mock_storage = Mock(spec=StorageService)
    mock_storage.upload_object_json.return_value = "path/to/json"
    mock_storage.upload_object_mesh.return_value = "path/to/mesh"
    
    # Create test data
    project_id = uuid4()
    data = CommitCreateRequest(
        branch_id=uuid4(),
        author_id=uuid4(),
        commit_message="Test commit",
        objects=[
            BlenderObjectCreate(
                object_name="Cube",
                object_type="MESH",
                json_data={"name": "Cube"},
                mesh_data=b"mesh_bytes"
            )
        ]
    )
    
    # Call endpoint
    response = await create_commit(
        project_id=project_id,
        data=data,
        db=mock_db,
        storage=mock_storage,
        current_user=test_user
    )
    
    # Verify storage was called
    mock_storage.upload_object_json.assert_called_once()
    mock_storage.upload_object_mesh.assert_called_once()
    
    # Verify DB record created
    assert response.commit_hash is not None
```

## References

- [Storage System Documentation](../STORAGE.md)
- [StorageService API](./storage_service.py)
- [Storage Routes](../routers/storage.py)
- [Integration Examples](./examples.py)

---

**Last Updated**: December 2025
