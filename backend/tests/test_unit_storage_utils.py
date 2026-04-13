"""
Extended Unit Tests for Storage Utilities (backend/storage/storage_utils.py)

Covers edge cases and boundary conditions not in the existing test_storage.py.
"""

import os
import pytest
import json

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests")

from storage.storage_utils import StorageUtils


# ============== Content Hashing Edge Cases ==============

class TestContentHashEdgeCases:
    """Edge-case tests for compute_content_hash."""

    def test_empty_dict(self):
        """Hashing an empty dict should succeed and be consistent."""
        h1 = StorageUtils.compute_content_hash({})
        h2 = StorageUtils.compute_content_hash({})
        assert h1 == h2
        assert len(h1) == 64

    def test_empty_bytes(self):
        """Hashing empty bytes should succeed."""
        h = StorageUtils.compute_content_hash(b"")
        assert len(h) == 64

    def test_dict_key_order_irrelevant(self):
        """Dicts with same keys in different insert order produce same hash (sort_keys)."""
        d1 = {"b": 2, "a": 1}
        d2 = {"a": 1, "b": 2}
        assert StorageUtils.compute_content_hash(d1) == StorageUtils.compute_content_hash(d2)

    def test_different_content_different_hash(self):
        """Different data produces different hashes."""
        h1 = StorageUtils.compute_content_hash({"a": 1})
        h2 = StorageUtils.compute_content_hash({"a": 2})
        assert h1 != h2

    def test_nested_dict(self):
        """Nested dicts hash consistently."""
        data = {"outer": {"inner": [1, 2, 3]}}
        h1 = StorageUtils.compute_content_hash(data)
        h2 = StorageUtils.compute_content_hash(data)
        assert h1 == h2

    def test_single_byte(self):
        """Single byte hashes correctly."""
        h = StorageUtils.compute_content_hash(b"\x00")
        assert len(h) == 64


# ============== Commit Hash ==============

class TestCommitHash:
    """Tests for compute_commit_hash."""

    def test_same_inputs_same_hash(self):
        h1 = StorageUtils.compute_commit_hash("p", "a", "msg", "ts")
        h2 = StorageUtils.compute_commit_hash("p", "a", "msg", "ts")
        assert h1 == h2

    def test_different_message_different_hash(self):
        h1 = StorageUtils.compute_commit_hash("p", "a", "msg1", "ts")
        h2 = StorageUtils.compute_commit_hash("p", "a", "msg2", "ts")
        assert h1 != h2

    def test_empty_message(self):
        """Empty commit message still produces a valid hash."""
        h = StorageUtils.compute_commit_hash("p", "a", "", "ts")
        assert len(h) == 64

    def test_empty_all_fields(self):
        """All empty strings still produce a valid 64-char hash."""
        h = StorageUtils.compute_commit_hash("", "", "", "")
        assert len(h) == 64


# ============== Object Type Validation ==============

class TestObjectTypeValidation:
    """Tests for validate_object_type."""

    def test_all_valid_types(self):
        """Each known Blender object type is accepted."""
        valid = [
            "MESH", "CURVE", "SURFACE", "META", "FONT",
            "ARMATURE", "LATTICE", "EMPTY",
            "LIGHT", "LIGHT_PROBE", "CAMERA",
            "SPEAKER", "GREASEPENCIL", "COLLECTION",
        ]
        for t in valid:
            assert StorageUtils.validate_object_type(t) is True, f"{t} should be valid"

    def test_case_insensitive(self):
        """Lowercase and mixed case are accepted."""
        assert StorageUtils.validate_object_type("mesh") is True
        assert StorageUtils.validate_object_type("Mesh") is True
        assert StorageUtils.validate_object_type("mEsH") is True

    def test_invalid_types(self):
        assert StorageUtils.validate_object_type("INVALID") is False
        assert StorageUtils.validate_object_type("BLAH") is False
        assert StorageUtils.validate_object_type("CUBE") is False  # not a type name

    def test_empty_string_invalid(self):
        assert StorageUtils.validate_object_type("") is False

    def test_whitespace_invalid(self):
        assert StorageUtils.validate_object_type("  MESH  ") is False


# ============== Parse Storage Path ==============

class TestParseStoragePath:
    """Tests for parse_storage_path."""

    def test_object_path(self):
        parsed = StorageUtils.parse_storage_path(
            "projects/123/objects/456/abc123.json"
        )
        assert parsed["type"] == "object"
        assert parsed["project_id"] == "123"
        assert parsed["object_id"] == "456"
        assert parsed["commit_hash"] == "abc123"

    def test_snapshot_path(self):
        parsed = StorageUtils.parse_storage_path(
            "projects/123/versions/2025-01-01_abc.blend"
        )
        assert parsed["type"] == "snapshot"
        assert parsed["project_id"] == "123"

    def test_dedup_path_global(self):
        parsed = StorageUtils.parse_storage_path("projects/dedup/abc.json")
        assert parsed["type"] == "dedup"
        assert parsed["blob_hash"] == "abc"

    def test_dedup_path_project_scoped(self):
        parsed = StorageUtils.parse_storage_path(
            "projects/123/dedup/hash456.json"
        )
        assert parsed["type"] == "dedup"
        assert parsed["project_id"] == "123"
        assert parsed["blob_hash"] == "hash456"

    def test_too_short_path_raises(self):
        with pytest.raises(ValueError, match="Invalid storage path"):
            StorageUtils.parse_storage_path("projects")

    def test_non_projects_prefix_returns_empty(self):
        """Paths not starting with 'projects' return empty dict."""
        parsed = StorageUtils.parse_storage_path("other/path/here")
        assert parsed == {}


# ============== Format File Size ==============

class TestFormatFileSize:
    """Tests for format_file_size."""

    def test_zero_bytes(self):
        assert StorageUtils.format_file_size(0) == "0.00 B"

    def test_bytes(self):
        assert StorageUtils.format_file_size(500) == "500.00 B"

    def test_kilobytes(self):
        assert StorageUtils.format_file_size(1024) == "1.00 KB"

    def test_megabytes(self):
        assert StorageUtils.format_file_size(1048576) == "1.00 MB"

    def test_gigabytes(self):
        assert StorageUtils.format_file_size(1073741824) == "1.00 GB"

    def test_terabytes(self):
        assert StorageUtils.format_file_size(1024 ** 4) == "1.00 TB"

    def test_fractional(self):
        """1536 bytes = 1.50 KB."""
        assert StorageUtils.format_file_size(1536) == "1.50 KB"

    def test_one_byte(self):
        assert StorageUtils.format_file_size(1) == "1.00 B"


# ============== Validate JSON Data ==============

class TestValidateJsonData:
    """Tests for validate_json_data."""

    def test_valid_minimal(self):
        data = {"object_name": "Cube", "object_type": "MESH"}
        ok, err = StorageUtils.validate_json_data(data)
        assert ok is True
        assert err is None

    def test_valid_with_extras(self):
        data = {
            "object_name": "Lamp1",
            "object_type": "LIGHT",
            "vertices": [],
            "intensity": 100,
        }
        ok, err = StorageUtils.validate_json_data(data)
        assert ok is True

    def test_missing_object_name(self):
        data = {"object_type": "MESH"}
        ok, err = StorageUtils.validate_json_data(data)
        assert ok is False
        assert "object_name" in err

    def test_missing_object_type(self):
        data = {"object_name": "Cube"}
        ok, err = StorageUtils.validate_json_data(data)
        assert ok is False
        assert "object_type" in err

    def test_empty_dict(self):
        ok, err = StorageUtils.validate_json_data({})
        assert ok is False

    def test_non_dict_input(self):
        ok, err = StorageUtils.validate_json_data("not a dict")
        assert ok is False
        assert "dictionary" in err

    def test_invalid_object_type(self):
        data = {"object_name": "Cube", "object_type": "BANANA"}
        ok, err = StorageUtils.validate_json_data(data)
        assert ok is False
        assert "Invalid object_type" in err

    def test_numeric_object_name_fails(self):
        data = {"object_name": 12345, "object_type": "MESH"}
        ok, err = StorageUtils.validate_json_data(data)
        assert ok is False
        assert "string" in err


# ============== Create Metadata ==============

class TestCreateMetadata:
    """Tests for create_metadata."""

    def test_basic(self):
        meta = StorageUtils.create_metadata("Cube", "MESH")
        assert meta["object_name"] == "Cube"
        assert meta["object_type"] == "MESH"
        assert meta["metadata"] == {}

    def test_with_kwargs(self):
        meta = StorageUtils.create_metadata("Cube", "MESH", author="alice", version=2)
        assert meta["metadata"]["author"] == "alice"
        assert meta["metadata"]["version"] == 2

    def test_all_types(self):
        """Object types other than MESH are accepted in metadata."""
        meta = StorageUtils.create_metadata("MyCamera", "CAMERA")
        assert meta["object_type"] == "CAMERA"
