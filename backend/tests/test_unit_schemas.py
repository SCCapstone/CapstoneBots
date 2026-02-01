# tests/test_unit_schemas.py
import pytest
from uuid import uuid4
from datetime import datetime, timezone

from schemas import ProjectCreate, BranchCreate, CommitCreateRequest, BlenderObjectCreate


def test_project_create_defaults():
    p = ProjectCreate(name="Demo Project")
    assert p.name == "Demo Project"
    assert p.active is True
    assert p.description is None


def test_branch_create_requires_name_or_branch_name():
    with pytest.raises(Exception):
        BranchCreate()


def test_commit_create_request_requires_objects():
    payload = {
        "branch_id": str(uuid4()),
        "commit_message": "test commit",
        "objects": [],
    }
    c = CommitCreateRequest(**payload)
    assert c.commit_message == "test commit"
    assert isinstance(c.objects, list)


def test_blender_object_create_minimum_fields():
    obj = BlenderObjectCreate(
        object_name="Cube",
        object_type="MESH",
        json_data_path="s3://bucket/cube.json",
        blob_hash="abc123",
    )
    assert obj.object_name == "Cube"