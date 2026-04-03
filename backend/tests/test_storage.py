"""
Storage Service Tests

Unit tests for the storage service layer, utilities, and API endpoints.
"""

import pytest
import json
from uuid import uuid4
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from minio.error import S3Error

from storage.storage_service import StorageService, MAX_PRESIGNED_URL_HOURS
from storage.storage_utils import StorageUtils


# ============== StorageUtils Tests ==============

class TestStorageUtils:
    """Tests for StorageUtils class"""
    
    def test_compute_content_hash_from_dict(self):
        """Test computing hash from dictionary"""
        data = {"name": "Cube", "type": "MESH"}
        hash1 = StorageUtils.compute_content_hash(data)
        hash2 = StorageUtils.compute_content_hash(data)
        
        # Same data should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex is 64 chars
    
    def test_compute_content_hash_from_bytes(self):
        """Test computing hash from bytes"""
        data = b"binary mesh data"
        hash1 = StorageUtils.compute_content_hash(data)
        hash2 = StorageUtils.compute_content_hash(data)
        
        assert hash1 == hash2
        assert len(hash1) == 64
    
    def test_compute_commit_hash(self):
        """Test commit hash generation"""
        project_id = str(uuid4())
        branch_id = str(uuid4())
        author_id = str(uuid4())
        message = "Test commit"
        timestamp = "2025-12-04T10:30:00"
        
        hash1 = StorageUtils.compute_commit_hash(
            project_id, branch_id, author_id, message, timestamp
        )
        
        # Different inputs should produce different hash
        hash2 = StorageUtils.compute_commit_hash(
            project_id, branch_id, author_id, "Different message", timestamp
        )
        
        assert hash1 != hash2
        assert len(hash1) == 64
    
    def test_validate_object_type_valid(self):
        """Test validation of valid Blender object types"""
        valid_types = ["MESH", "CAMERA", "LIGHT", "ARMATURE", "EMPTY"]
        
        for obj_type in valid_types:
            assert StorageUtils.validate_object_type(obj_type) is True
            assert StorageUtils.validate_object_type(obj_type.lower()) is True
    
    def test_validate_object_type_invalid(self):
        """Test validation of invalid object types"""
        invalid_types = ["INVALID", "UNKNOWN", "BLAH", ""]
        
        for obj_type in invalid_types:
            assert StorageUtils.validate_object_type(obj_type) is False
    
    def test_parse_storage_path_object(self):
        """Test parsing object storage path"""
        path = "projects/123/objects/456/abc123def456.json"
        parsed = StorageUtils.parse_storage_path(path)
        
        assert parsed["type"] == "object"
        assert parsed["project_id"] == "123"
        assert parsed["object_id"] == "456"
        assert parsed["commit_hash"] == "abc123def456"
    
    def test_parse_storage_path_snapshot(self):
        """Test parsing snapshot storage path"""
        path = "projects/123/versions/2025-12-04_abc123.blend"
        parsed = StorageUtils.parse_storage_path(path)
        
        assert parsed["type"] == "snapshot"
        assert parsed["project_id"] == "123"
        assert parsed["filename"] == "2025-12-04_abc123.blend"
    
    def test_parse_storage_path_dedup(self):
        """Test parsing dedup storage path"""
        path = "projects/dedup/abc123def456.json"
        parsed = StorageUtils.parse_storage_path(path)
        
        assert parsed["type"] == "dedup"
        assert parsed["blob_hash"] == "abc123def456"
    
    def test_format_file_size(self):
        """Test file size formatting"""
        assert StorageUtils.format_file_size(0) == "0.00 B"
        assert StorageUtils.format_file_size(1024) == "1.00 KB"
        assert StorageUtils.format_file_size(1048576) == "1.00 MB"
        assert StorageUtils.format_file_size(1073741824) == "1.00 GB"
    
    def test_validate_json_data_valid(self):
        """Test validation of valid JSON data"""
        data = {
            "object_name": "Cube",
            "object_type": "MESH",
            "vertices": []
        }
        
        is_valid, error = StorageUtils.validate_json_data(data)
        assert is_valid is True
        assert error is None
    
    def test_validate_json_data_missing_field(self):
        """Test validation with missing required field"""
        data = {
            "object_name": "Cube"
            # Missing object_type
        }
        
        is_valid, error = StorageUtils.validate_json_data(data)
        assert is_valid is False
        assert "object_type" in error
    
    def test_validate_json_data_invalid_type(self):
        """Test validation with invalid object type"""
        data = {
            "object_name": "Cube",
            "object_type": "INVALID"
        }
        
        is_valid, error = StorageUtils.validate_json_data(data)
        assert is_valid is False
        assert "Invalid object_type" in error
    
    def test_create_metadata(self):
        """Test metadata creation"""
        metadata = StorageUtils.create_metadata(
            "Cube",
            "MESH",
            custom_field="value",
            another_field=123
        )
        
        assert metadata["object_name"] == "Cube"
        assert metadata["object_type"] == "MESH"
        assert metadata["metadata"]["custom_field"] == "value"
        assert metadata["metadata"]["another_field"] == 123



# ============== Integration Tests ==============

class TestStorageServiceIntegration:
    """Integration tests for StorageService"""
    
    @pytest.mark.skipif(True, reason="Requires MinIO running")
    def test_upload_and_download_object(self):
        """Test uploading and downloading an object"""
        # This would require MinIO to be running
        pass
    
    @pytest.mark.skipif(True, reason="Requires MinIO running")
    def test_deduplication_in_practice(self):
        """Test deduplication with actual uploads"""
        # This would require MinIO to be running
        pass


# ============== Presigned URL Tests ==============

class TestPresignedURL:
    """Tests for presigned URL functionality"""
    
    def test_get_presigned_url_valid_expiry(self):
        """Test generating presigned URL with valid expiry time"""
        from datetime import timedelta
        
        mock_client = Mock()
        mock_client.presigned_get_object.return_value = "https://minio.example.com/bucket/path/to/file?signature=xyz"
        
        # Create storage without calling __init__
        storage = object.__new__(StorageService)
        storage.client = mock_client
        storage.bucket_name = "test-bucket"
        
        url = storage.get_presigned_url("projects/123/file.json", expires_hours=2)
        
        assert url == "https://minio.example.com/bucket/path/to/file?signature=xyz"
        mock_client.presigned_get_object.assert_called_once()
        call_args = mock_client.presigned_get_object.call_args
        assert call_args[1]["expires"] == timedelta(hours=2)
    
    def test_get_presigned_url_default_expiry(self):
        """Test generating presigned URL with default 1 hour expiry"""
        from datetime import timedelta
        
        mock_client = Mock()
        mock_client.presigned_get_object.return_value = "https://minio.example.com/bucket/path"
        
        # Create storage without calling __init__
        storage = object.__new__(StorageService)
        storage.client = mock_client
        storage.bucket_name = "test-bucket"
        
        url = storage.get_presigned_url("projects/123/file.json")
        
        # Verify it was called with 1 hour timedelta
        call_args = mock_client.presigned_get_object.call_args
        assert call_args[0][0] == "test-bucket"
        assert call_args[0][1] == "projects/123/file.json"
        assert call_args[1]["expires"] == timedelta(hours=1)
    
    def test_get_presigned_url_invalid_expiry_negative(self):
        """Test that negative expiry hours raises ValueError"""
        # Create storage without calling __init__
        storage = object.__new__(StorageService)
        storage.client = Mock()
        storage.bucket_name = "test-bucket"
        
        with pytest.raises(ValueError, match=f"expires_hours must be an integer between 1 and {MAX_PRESIGNED_URL_HOURS}"):
            storage.get_presigned_url("projects/123/file.json", expires_hours=-1)
    
    def test_get_presigned_url_invalid_expiry_zero(self):
        """Test that zero expiry hours raises ValueError"""
        # Create storage without calling __init__
        storage = object.__new__(StorageService)
        storage.client = Mock()
        storage.bucket_name = "test-bucket"
        
        with pytest.raises(ValueError, match=f"expires_hours must be an integer between 1 and {MAX_PRESIGNED_URL_HOURS}"):
            storage.get_presigned_url("projects/123/file.json", expires_hours=0)
    
    def test_get_presigned_url_invalid_expiry_too_large(self):
        """Test that expiry hours > MAX_PRESIGNED_URL_HOURS raises ValueError"""
        # Create storage without calling __init__
        storage = object.__new__(StorageService)
        storage.client = Mock()
        storage.bucket_name = "test-bucket"
        
        with pytest.raises(ValueError, match=f"expires_hours must be an integer between 1 and {MAX_PRESIGNED_URL_HOURS}"):
            storage.get_presigned_url("projects/123/file.json", expires_hours=MAX_PRESIGNED_URL_HOURS + 1)
    
    def test_get_presigned_url_invalid_expiry_non_integer(self):
        """Test that non-integer expiry hours raises ValueError"""
        # Create storage without calling __init__
        storage = object.__new__(StorageService)
        storage.client = Mock()
        storage.bucket_name = "test-bucket"
        
        with pytest.raises(ValueError, match=f"expires_hours must be an integer between 1 and {MAX_PRESIGNED_URL_HOURS}"):
            storage.get_presigned_url("projects/123/file.json", expires_hours=1.5)
    
    def test_get_presigned_url_s3_error(self):
        """Test that S3Error is properly raised"""
        mock_client = Mock()
        mock_client.presigned_get_object.side_effect = S3Error(
            "NoSuchKey", "Object not found", "resource", "request_id", "host_id", "response"
        )
        
        # Create storage without calling __init__
        storage = object.__new__(StorageService)
        storage.client = mock_client
        storage.bucket_name = "test-bucket"
        
        with pytest.raises(S3Error):
            storage.get_presigned_url("projects/123/nonexistent.json")


# ============== Schema Validation Tests ==============

class TestStorageSchemas:
    """Tests for storage-related Pydantic schemas"""
    
    def test_storage_object_info_schema(self):
        """Test StorageObjectInfo schema validation"""
        from schemas import StorageObjectInfo
        
        info = StorageObjectInfo(
            name="cube.json",
            size=2048,
            etag="abc123",
            last_modified=datetime.now()
        )
        
        assert info.name == "cube.json"
        assert info.size == 2048
    
    def test_project_storage_stats_schema(self):
        """Test ProjectStorageStats schema validation"""
        from schemas import ProjectStorageStats
        
        project_id = uuid4()
        stats = ProjectStorageStats(
            project_id=project_id,
            total_bytes=1048576,
            objects_bytes=819200,
            versions_bytes=229376,
            total_mb=1.0
        )
        
        assert stats.project_id == project_id
        assert stats.total_mb == 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
