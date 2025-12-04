# backend/storage/minio_client.py

from minio import Minio
from minio.error import S3Error

import datetime

client = Minio(
    endpoint=os.environ["S3_ENDPOINT"].replace("https://", "").replace("http://", ""),
    access_key=os.environ["S3_ACCESS_KEY"],
    secret_key=os.environ["S3_SECRET_KEY"],
    secure=os.environ.get("S3_SECURE", "true").lower() == "true",
    region=os.environ.get("S3_REGION"),
)

BUCKET_NAME = os.environ["S3_BUCKET"]

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


