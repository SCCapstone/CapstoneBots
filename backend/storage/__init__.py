"""
Storage module for handling all file operations with MinIO object storage.

Provides two interfaces:
1. StorageService: Modern async-ready service for new code
2. minio_client: Legacy functions for backward compatibility

Also includes utilities:
- StorageUtils: Path parsing, hashing, validation
- DeduplicationManager: Content deduplication tracking
- VersioningHelper: Version tag creation and parsing
"""

from .storage_service import StorageService, get_storage_service
from .minio_client import upload_file, download_file, upload_version, upload_bytes, download_bytes
from .storage_utils import StorageUtils, DeduplicationManager, VersioningHelper, StorageCompression

__all__ = [
    # Service and dependency injection
    "StorageService",
    "get_storage_service",
    # Legacy functions
    "upload_file",
    "download_file",
    "upload_version",
    "upload_bytes",
    "download_bytes",
    # Utilities
    "StorageUtils",
    "DeduplicationManager",
    "VersioningHelper",
    "StorageCompression",
]

