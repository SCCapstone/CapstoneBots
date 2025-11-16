# backend/storage/minio_client.py

from minio import Minio
from minio.error import S3Error

import datetime

client = Minio(
    "localhost:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=False
)

BUCKET_NAME = "blender-vcs"

if not client.bucket_exists(BUCKET_NAME):
    client.make_bucket(BUCKET_NAME)

def upload_file(local_path: str, object_name: str):
    client.fput_object(BUCKET_NAME, object_name, local_path)
    print(f"Uploaded {local_path} as {object_name}")

def download_file(object_name: str, local_path: str):
    client.fget_object(BUCKET_NAME, object_name, local_path)
    print(f"Downloaded {object_name} to {local_path}")

def upload_version(local_path: str, project_name: str):
    """Uploads a .blend file with a timestamped version name"""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    object_name = f"projects/{project_name}/versions/{timestamp}.blend"
    upload_file(local_path, object_name)


