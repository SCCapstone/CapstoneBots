"""
Legacy MinIO client module - maintained for backward compatibility.
New code should use storage_service.py instead.
"""

import os
import io
from datetime import datetime
from minio import Minio
from minio.error import S3Error

# Initialize client with environment variables
client = Minio(
    endpoint=os.environ.get("S3_ENDPOINT", "localhost:9000").replace("https://", "").replace("http://", ""),
    access_key=os.environ.get("S3_ACCESS_KEY", "minioadmin"),
    secret_key=os.environ.get("S3_SECRET_KEY", "minioadmin"),
    secure=os.environ.get("S3_SECURE", "true").lower() == "true",
    region=os.environ.get("S3_REGION", "us-east-1"),
)

BUCKET_NAME = os.environ.get("S3_BUCKET", "capstonebots")


def upload_file(local_path: str, object_name: str):
    """
    Upload a local file to MinIO.
    
    Args:
        local_path: Path to local file
        object_name: Object name in bucket
    """
    try:
        client.fput_object(BUCKET_NAME, object_name, local_path)
        print(f"Uploaded {local_path} as {object_name}")
    except S3Error as e:
        print(f"Error uploading file: {e}")
        raise


def download_file(object_name: str, local_path: str):
    """
    Download a file from MinIO to local filesystem.
    
    Args:
        object_name: Object name in bucket
        local_path: Local destination path
    """
    try:
        client.fget_object(BUCKET_NAME, object_name, local_path)
        print(f"Downloaded {object_name} to {local_path}")
    except S3Error as e:
        print(f"Error downloading file: {e}")
        raise


def upload_version(local_path: str, project_name: str) -> str:
    """
    Upload a .blend file with a timestamped version name.
    
    Args:
        local_path: Path to .blend file
        project_name: Project identifier
        
    Returns:
        str: Object name in storage
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    object_name = f"projects/{project_name}/versions/{timestamp}.blend"
    upload_file(local_path, object_name)
    return object_name


def upload_bytes(data: bytes, object_name: str, content_type: str = "application/octet-stream"):
    """
    Upload raw bytes to MinIO.
    
    Args:
        data: Bytes to upload
        object_name: Object name in bucket
        content_type: MIME type
    """
    try:
        client.put_object(
            BUCKET_NAME,
            object_name,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type
        )
        print(f"Uploaded {len(data)} bytes as {object_name}")
    except S3Error as e:
        print(f"Error uploading bytes: {e}")
        raise


def download_bytes(object_name: str) -> bytes:
    """
    Download file from MinIO as bytes.
    
    Args:
        object_name: Object name in bucket
        
    Returns:
        bytes: File content
    """
    try:
        response = client.get_object(BUCKET_NAME, object_name)
        data = response.read()
        print(f"Downloaded {len(data)} bytes from {object_name}")
        return data
    except S3Error as e:
        print(f"Error downloading bytes: {e}")
        raise


