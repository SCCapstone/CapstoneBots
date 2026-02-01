"""
Storage Service Tests

Unit tests for the storage service layer, utilities, and API endpoints.
"""

import pytest
import json
from uuid import uuid4
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from storage.storage_service import StorageService
from storage.storage_utils import StorageUtils, DeduplicationManager, VersioningHelper


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


# ============== DeduplicationManager Tests ==============

class TestDeduplicationManager:
    """Tests for DeduplicationManager class"""
    
    def setup_method(self):
        """Setup for each test"""
        self.mock_storage = Mock()
        self.dedup = DeduplicationManager(self.mock_storage)
    
    def test_should_store_separately_new_hash(self):
        """Test that new hashes should be stored"""
        hash1 = "abc123"
        assert self.dedup.should_store_separately(hash1) is True
    
    def test_should_store_separately_existing_hash(self):
        """Test that existing hashes shouldn't be stored again"""
        hash1 = "abc123"
        self.dedup.register_hash(hash1, "path/to/file")
        
        assert self.dedup.should_store_separately(hash1) is False
    
    def test_register_and_retrieve_hash(self):
        """Test registering and retrieving hash paths"""
        hash1 = "abc123"
        path = "projects/123/objects/456/hash.json"
        
        self.dedup.register_hash(hash1, path)
        retrieved_path = self.dedup.get_duplicate_path(hash1)
        
        assert retrieved_path == path
    
    def test_get_duplicate_path_not_found(self):
        """Test retrieving non-existent hash"""
        path = self.dedup.get_duplicate_path("nonexistent")
        assert path is None
    
    def test_calculate_savings(self):
        """Test savings calculation"""
        total = 1000
        actual = 600
        
        savings = self.dedup.calculate_savings(total, actual)
        
        assert savings["total_size"] == 1000
        assert savings["actual_stored"] == 600
        assert savings["bytes_saved"] == 400
        assert savings["percent_saved"] == 40.0
    
    def test_calculate_savings_no_duplicate(self):
        """Test savings when no deduplication occurred"""
        total = 1000
        actual = 1000
        
        savings = self.dedup.calculate_savings(total, actual)
        
        assert savings["bytes_saved"] == 0
        assert savings["percent_saved"] == 0.0


# ============== VersioningHelper Tests ==============

class TestVersioningHelper:
    """Tests for VersioningHelper class"""
    
    def test_create_version_tag(self):
        """Test version tag creation"""
        commit_hash = "abc123def456"
        timestamp = "2025-12-04T10-30-00"
        
        tag = VersioningHelper.create_version_tag(commit_hash, timestamp)
        
        assert "v_" in tag
        assert "abc123de" in tag  # First 8 chars of hash
        assert timestamp in tag
    
    def test_parse_version_tag(self):
        """Test version tag parsing"""
        tag = "v_2025-12-04T10-30-00_abc123de"
        parsed = VersioningHelper.parse_version_tag(tag)
        
        assert parsed["commit_hash_short"] == "abc123de"
        assert "2025-12-04" in parsed["timestamp"]
    
    def test_get_version_range(self):
        """Test version range creation"""
        start = "abc123def456"
        end = "xyz789uvwxyz"
        
        range_str = VersioningHelper.get_version_range(start, end)
        
        assert "abc123de" in range_str  # First 8 chars of start
        assert "xyz789uv" in range_str  # First 8 chars of end
        assert ".." in range_str


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
