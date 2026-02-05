"""
Quick script to list files in S3 bucket and download with signed URLs
"""

from minio import Minio
from minio.error import S3Error
from datetime import timedelta

print("=" * 70)
print("S3 File Browser & Downloader")
print("=" * 70)
print()

# Get credentials
endpoint = input("S3 Endpoint: ").strip()
access_key = input("Access Key: ").strip()
secret_key = input("Secret Key: ").strip()
bucket_name = input("Bucket Name (default: blender-vcs-prod): ").strip() or "blender-vcs-prod"

use_secure = input("Use HTTPS? (y/n, default: y): ").strip().lower()
secure = use_secure != 'n'

print()
print("Connecting and listing files...")
print()

try:
    client = Minio(
        endpoint=endpoint.replace("https://", "").replace("http://", ""),
        access_key=access_key,
        secret_key=secret_key,
        secure=secure
    )
    
    if not client.bucket_exists(bucket_name):
        print(f"❌ Bucket '{bucket_name}' does not exist!")
        exit(1)
    
    print(f"✓ Bucket '{bucket_name}' found!")
    print()
    
    # Store objects in a list
    file_list = []
    print("Files in bucket:")
    print("-" * 70)
    
    objects = client.list_objects(bucket_name, recursive=True)
    
    for obj in objects:
        file_list.append(obj)
        idx = len(file_list)
        size_mb = obj.size / (1024 * 1024)
        print(f"{idx}. {obj.object_name}")
        print(f"   Size: {size_mb:.2f} MB ({obj.size:,} bytes)")
        print(f"   Modified: {obj.last_modified}")
        print()
    
    if len(file_list) == 0:
        print("No files found in bucket.")
        exit(0)
    
    print(f"Total files: {len(file_list)}")
    print("=" * 70)
    print()
    
    # Interactive selection loop
    while True:
        choice = input(f"Enter file number (1-{len(file_list)}) to download, or 'q' to quit: ").strip().lower()
        
        if choice == 'q':
            print("Goodbye!")
            break
        
        try:
            file_num = int(choice)
            if file_num < 1 or file_num > len(file_list):
                print(f"❌ Please enter a number between 1 and {len(file_list)}")
                continue
            
            selected_file = file_list[file_num - 1]
            
            print()
            print("=" * 70)
            print(f"Selected: {selected_file.object_name}")
            print("=" * 70)
            print()
            
            # Generate presigned URL (valid for 1 hour)
            print("Generating download link (valid for 1 hour)...")
            url = client.presigned_get_object(
                bucket_name,
                selected_file.object_name,
                expires=timedelta(hours=1)
            )
            
            print()
            print("✓ Download link generated!")
            print()
            print("Copy this URL to download the file:")
            print("-" * 70)
            print(url)
            print("-" * 70)
            print()
            print("You can:")
            print("  • Copy and paste this URL into your browser")
            print("  • Use curl: curl -o filename.blend \"<URL>\"")
            print("  • Use wget: wget -O filename.blend \"<URL>\"")
            print()
            
            # Ask if they want to download directly
            download_now = input("Download file now? (y/n): ").strip().lower()
            if download_now == 'y':
                filename = selected_file.object_name.split('/')[-1]
                local_path = input(f"Save as (default: {filename}): ").strip() or filename
                
                print(f"Downloading to {local_path}...")
                client.fget_object(bucket_name, selected_file.object_name, local_path)
                
                print(f"✓ Downloaded successfully to {local_path}")
                print()
        
        except ValueError:
            print("❌ Please enter a valid number")
        except S3Error as e:
            print(f"❌ S3 Error: {e.code} - {e.message}")
        except Exception as e:
            print(f"❌ Error: {str(e)}")
        
        print()
        
except S3Error as e:
    print(f"❌ S3 Error: {e.code} - {e.message}")
except Exception as e:
    print(f"❌ Error: {str(e)}")
