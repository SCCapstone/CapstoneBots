from fastapi import APIRouter, HTTPException, Query
from datetime import timedelta
from typing import List, Dict, Any
import os

from minio import Minio
from minio.error import S3Error

router = APIRouter(
    prefix="/download",
    tags=["downloads"],
)

def get_minio_client() -> Minio:
    # 👇 matches your Railway env names
    endpoint = os.getenv("S3_ENDPOINT", "s3.us-east-1.amazonaws.com").strip()
    access_key = os.getenv("S3_ACCESS_KEY", "").strip()
    secret_key = os.getenv("S3_SECRET_KEY", "").strip()
    secure_str = os.getenv("S3_SECURE", "true").strip().lower()
    print("DEBUG S3 env:", endpoint, bool(access_key), bool(secret_key))
    
    if not endpoint or not access_key or not secret_key:
        raise RuntimeError("S3_ENDPOINT, S3_ACCESS_KEY, and S3_SECRET_KEY must be set")

    endpoint = endpoint.replace("https://", "").replace("http://", "")
    secure = secure_str not in ("0", "false", "no", "n")

    return Minio(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
        region=os.getenv("S3_REGION", "us-east-1"),
    )

def get_bucket_name() -> str:
    return os.getenv("S3_BUCKET", "blender-vcs-prod")


@router.get("/files")
async def list_files(prefix: str = Query("", description="Optional prefix")):
    client = get_minio_client()
    bucket = get_bucket_name()

    try:
        if not client.bucket_exists(bucket):
            raise HTTPException(status_code=404, detail=f"Bucket '{bucket}' not found")

        objects = client.list_objects(bucket, prefix=prefix, recursive=True)
        files: List[Dict[str, Any]] = []
        for obj in objects:
            files.append({
                "path": obj.object_name,
                "size": obj.size,
                "size_mb": round(obj.size / (1024 * 1024), 2),
                "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
                "etag": obj.etag,
            })

        return {"files": files, "total": len(files)}
    except S3Error as e:
        raise HTTPException(status_code=500, detail=f"S3 Error: {e.message}")


@router.get("/signed-url/{file_path:path}")
async def get_signed_url(file_path: str, expires_hours: int = 1):
    client = get_minio_client()
    bucket = get_bucket_name()

    try:
        # optional existence check
        try:
            client.stat_object(bucket, file_path)
        except S3Error as e:
            if e.code == "NoSuchKey":
                raise HTTPException(status_code=404, detail="File not found")
            raise

        url = client.presigned_get_object(
            bucket,
            file_path,
            expires=timedelta(hours=expires_hours),
        )
        return {"url": url, "expires_in_hours": expires_hours}
    except S3Error as e:
        raise HTTPException(status_code=500, detail=f"S3 Error: {e.message}")
