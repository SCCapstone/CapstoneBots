"""
FastAPI endpoint for downloading Blender files from S3 storage.

This provides a REST API endpoint that your frontend can call to download
Blender files stored in your S3/MinIO storage.

Usage:
    uvicorn download_api:app --reload --port 8001
    
Endpoints:
    GET  /api/download/object/{object_id}
    GET  /api/download/preview - Test endpoint with query parameters
    POST /api/download/by-path - Download using S3 path directly
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os
import io
from minio import Minio
from minio.error import S3Error
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Blender File Download API",
    description="API for downloading Blender files from S3 storage",
    version="1.0.0"
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class S3Config(BaseModel):
    """S3 configuration model"""
    endpoint: str
    access_key: str
    secret_key: str
    bucket_name: str = "blender-vcs-prod"
    secure: bool = True


class DownloadRequest(BaseModel):
    """Request model for downloading by S3 path"""
    s3_path: str  # e.g., "784b71e4-3ade-4a42-8e30-d1d5d449b365_20251205_194615/Untitled.blend"
    s3_config: S3Config


def get_minio_client(config: S3Config) -> Minio:
    """Create and return a MinIO client"""
    endpoint = config.endpoint.replace("https://", "").replace("http://", "")
    
    client = Minio(
        endpoint=endpoint,
        access_key=config.access_key,
        secret_key=config.secret_key,
        secure=config.secure
    )
    
    return client


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Blender File Download API",
        "version": "1.0.0",
        "endpoints": {
            "download_by_path": "POST /api/download/by-path",
            "health": "GET /health"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.post("/api/download/by-path")
async def download_by_path(request: DownloadRequest):
    """
    Download a Blender file using its S3 path.
    
    Args:
        request: DownloadRequest containing S3 path and configuration
        
    Returns:
        StreamingResponse with the file content
        
    Example request:
        POST /api/download/by-path
        {
            "s3_path": "784b71e4-3ade-4a42-8e30-d1d5d449b365_20251205_194615/Untitled.blend",
            "s3_config": {
                "endpoint": "your-s3-endpoint.com",
                "access_key": "your-access-key",
                "secret_key": "your-secret-key",
                "bucket_name": "blender-vcs-prod",
                "secure": true
            }
        }
    """
    try:
        logger.info(f"Attempting to download: {request.s3_path}")
        
        # Create MinIO client
        client = get_minio_client(request.s3_config)
        
        # Check if bucket exists
        if not client.bucket_exists(request.s3_config.bucket_name):
            raise HTTPException(
                status_code=404,
                detail=f"Bucket '{request.s3_config.bucket_name}' not found"
            )
        
        # Get the object
        response = client.get_object(request.s3_config.bucket_name, request.s3_path)
        
        # Read the data
        file_data = response.read()
        response.close()
        response.release_conn()
        
        # Extract filename from path
        filename = request.s3_path.split('/')[-1]
        
        logger.info(f"Successfully downloaded {len(file_data)} bytes")
        
        # Return as streaming response
        return StreamingResponse(
            io.BytesIO(file_data),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Length": str(len(file_data))
            }
        )
        
    except S3Error as e:
        logger.error(f"S3 Error: {e.code} - {e.message}")
        raise HTTPException(
            status_code=500,
            detail=f"S3 Error: {e.message}"
        )
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error downloading file: {str(e)}"
        )


@app.get("/api/download/test")
async def test_download(
    endpoint: str = Query(..., description="S3 endpoint"),
    access_key: str = Query(..., description="S3 access key"),
    secret_key: str = Query(..., description="S3 secret key"),
    bucket_name: str = Query("blender-vcs-prod", description="S3 bucket name"),
    object_path: str = Query(..., description="Object path in S3"),
    secure: bool = Query(True, description="Use HTTPS")
):
    """
    Test endpoint for downloading with query parameters.
    
    Example:
        GET /api/download/test?endpoint=s3.example.com&access_key=xxx&secret_key=yyy&object_path=path/to/file.blend
    """
    try:
        # Create config from query params
        config = S3Config(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            bucket_name=bucket_name,
            secure=secure
        )
        
        # Create request
        request = DownloadRequest(
            s3_path=object_path,
            s3_config=config
        )
        
        # Use the main download function
        return await download_by_path(request)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/info/object")
async def get_object_info(
    endpoint: str = Query(...),
    access_key: str = Query(...),
    secret_key: str = Query(...),
    bucket_name: str = Query("blender-vcs-prod"),
    object_path: str = Query(...),
    secure: bool = Query(True)
):
    """
    Get information about an object without downloading it.
    
    Returns metadata like size, content type, last modified, etc.
    """
    try:
        config = S3Config(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            bucket_name=bucket_name,
            secure=secure
        )
        
        client = get_minio_client(config)
        
        # Get object stats
        stat = client.stat_object(bucket_name, object_path)
        
        return {
            "object_path": object_path,
            "size": stat.size,
            "size_mb": round(stat.size / (1024 * 1024), 2),
            "content_type": stat.content_type,
            "last_modified": stat.last_modified.isoformat(),
            "etag": stat.etag,
            "metadata": stat.metadata
        }
        
    except S3Error as e:
        raise HTTPException(
            status_code=404 if e.code == "NoSuchKey" else 500,
            detail=f"S3 Error: {e.message}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
