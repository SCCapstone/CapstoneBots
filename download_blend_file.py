"""
Simple script to download a Blender file from S3/MinIO storage.

This script connects to your S3-compatible storage (MinIO) and downloads
a specific Blender file based on the object path stored in your database.

Usage:
    python download_blend_file.py
    
You'll be prompted to enter:
    - S3 Endpoint (e.g., s3.amazonaws.com or localhost:9000)
    - S3 Access Key
    - S3 Secret Key
    - S3 Bucket Name
    - Object Path (the S3 path from your database)
    - Local Download Path (where to save the file)
"""

import os
import sys
from minio import Minio
from minio.error import S3Error


def download_blend_file():
    """Download a Blender file from S3/MinIO storage"""
    
    print("=" * 70)
    print("Blender File Downloader - S3/MinIO")
    print("=" * 70)
    print()
    
    # Get S3 credentials and configuration
    print("Enter your S3/MinIO configuration:")
    print("-" * 70)
    
    endpoint = input("S3 Endpoint (e.g., s3.amazonaws.com or localhost:9000): ").strip()
    access_key = input("Access Key: ").strip()
    secret_key = input("Secret Key: ").strip()
    bucket_name = input("Bucket Name (default: blender-vcs-prod): ").strip() or "blender-vcs-prod"
    
    # Determine if using secure connection
    secure = True
    if "localhost" in endpoint or "127.0.0.1" in endpoint:
        use_secure = input("Use HTTPS? (y/n, default: n): ").strip().lower()
        secure = use_secure == 'y'
    
    print()
    print("Enter the file details:")
    print("-" * 70)
    
    # Get object path from database
    object_path = input("Object Path from database (e.g., 784b71e4-3ade-4a42-8e30-d1d5d449b365_20251205_194615/Untitled.blend): ").strip()
    
    # Get local download path
    default_filename = object_path.split('/')[-1] if '/' in object_path else 'downloaded_file.blend'
    local_path = input(f"Local download path (default: {default_filename}): ").strip() or default_filename
    
    print()
    print("=" * 70)
    print("Starting download...")
    print("=" * 70)
    print()
    
    try:
        # Initialize MinIO client
        print(f"Connecting to {endpoint}...")
        client = Minio(
            endpoint=endpoint.replace("https://", "").replace("http://", ""),
            access_key=access_key,
            secret_key=secret_key,
            secure=secure
        )
        
        # Check if bucket exists
        print(f"Checking bucket '{bucket_name}'...")
        if not client.bucket_exists(bucket_name):
            print(f"❌ ERROR: Bucket '{bucket_name}' does not exist!")
            return False
        
        print(f"✓ Bucket found")
        
        # Download the file
        print(f"Downloading '{object_path}' to '{local_path}'...")
        client.fget_object(bucket_name, object_path, local_path)
        
        # Get file size
        file_size = os.path.getsize(local_path)
        file_size_mb = file_size / (1024 * 1024)
        
        print()
        print("=" * 70)
        print("✓ Download successful!")
        print("=" * 70)
        print(f"File: {local_path}")
        print(f"Size: {file_size_mb:.2f} MB ({file_size:,} bytes)")
        print()
        
        return True
        
    except S3Error as e:
        print()
        print("=" * 70)
        print("❌ S3 Error occurred:")
        print("=" * 70)
        print(f"Code: {e.code}")
        print(f"Message: {e.message}")
        print()
        return False
        
    except Exception as e:
        print()
        print("=" * 70)
        print("❌ Error occurred:")
        print("=" * 70)
        print(f"{type(e).__name__}: {str(e)}")
        print()
        return False


def main():
    """Main entry point"""
    try:
        success = download_blend_file()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nDownload cancelled by user.")
        sys.exit(1)


if __name__ == "__main__":
    main()
