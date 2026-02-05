# Blender File Download Scripts

This directory contains two scripts for downloading Blender files from your S3/MinIO storage.

## Files Created

1. **`download_blend_file.py`** - Simple interactive CLI script
2. **`download_api.py`** - REST API with endpoints for frontend integration
3. **`download_requirements.txt`** - Python dependencies

## Installation

```powershell
pip install -r download_requirements.txt
```

## Option 1: Simple CLI Script

### Usage

Run the interactive script:

```powershell
python download_blend_file.py
```

You'll be prompted for:
- **S3 Endpoint**: Your S3 endpoint (e.g., `s3.amazonaws.com` or production URL)
- **Access Key**: Your S3 access key
- **Secret Key**: Your S3 secret key  
- **Bucket Name**: Default is `blender-vcs-prod`
- **Object Path**: From your database, e.g., `784b71e4-3ade-4a42-8e30-d1d5d449b365_20251205_194615/Untitled.blend`
- **Local Path**: Where to save the file (default: `Untitled.blend`)

### Example

```
S3 Endpoint: your-production-endpoint.com
Access Key: your-access-key
Secret Key: your-secret-key
Bucket Name: blender-vcs-prod
Object Path: 784b71e4-3ade-4a42-8e30-d1d5d449b365_20251205_194615/Untitled.blend
Local download path: MyFile.blend
```

## Option 2: REST API (For Frontend Integration)

### Start the API Server

```powershell
python download_api.py
```

Or with uvicorn:

```powershell
uvicorn download_api:app --reload --port 8001
```

The API will be available at `http://localhost:8001`

### API Documentation

Once running, visit:
- **Swagger UI**: http://localhost:8001/docs
- **ReDoc**: http://localhost:8001/redoc

### Endpoints

#### 1. Download by Path (Recommended)

**POST** `/api/download/by-path`

**Request Body:**
```json
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
```

**Response:** File download (binary)

#### 2. Test Download (Query Parameters)

**GET** `/api/download/test?endpoint=xxx&access_key=yyy&secret_key=zzz&object_path=path/to/file.blend`

Good for quick testing in a browser.

#### 3. Get Object Info

**GET** `/api/info/object?endpoint=xxx&access_key=yyy&secret_key=zzz&object_path=path/to/file.blend`

Returns metadata without downloading:
```json
{
  "object_path": "784b71e4-3ade-4a42-8e30-d1d5d449b365_20251205_194615/Untitled.blend",
  "size": 1048576,
  "size_mb": 1.0,
  "content_type": "application/octet-stream",
  "last_modified": "2025-12-05T19:46:15.949527",
  "etag": "...",
  "metadata": {}
}
```

## Frontend Integration Example

### JavaScript/TypeScript Fetch

```typescript
async function downloadBlendFile(objectPath: string) {
  const response = await fetch('http://localhost:8001/api/download/by-path', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      s3_path: objectPath,
      s3_config: {
        endpoint: process.env.NEXT_PUBLIC_S3_ENDPOINT,
        access_key: process.env.NEXT_PUBLIC_S3_ACCESS_KEY,
        secret_key: process.env.NEXT_PUBLIC_S3_SECRET_KEY,
        bucket_name: "blender-vcs-prod",
        secure: true
      }
    })
  });

  if (!response.ok) {
    throw new Error('Download failed');
  }

  // Get the blob
  const blob = await response.blob();
  
  // Create download link
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'Untitled.blend';
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

// Usage
downloadBlendFile('784b71e4-3ade-4a42-8e30-d1d5d449b365_20251205_194615/Untitled.blend');
```

### React Component Example

```tsx
import { useState } from 'react';

export function DownloadButton({ objectPath }: { objectPath: string }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDownload = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch('http://localhost:8001/api/download/by-path', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          s3_path: objectPath,
          s3_config: {
            endpoint: process.env.NEXT_PUBLIC_S3_ENDPOINT!,
            access_key: process.env.NEXT_PUBLIC_S3_ACCESS_KEY!,
            secret_key: process.env.NEXT_PUBLIC_S3_SECRET_KEY!,
            bucket_name: "blender-vcs-prod",
            secure: true
          }
        })
      });

      if (!response.ok) {
        throw new Error('Download failed');
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = objectPath.split('/').pop() || 'file.blend';
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Download failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <button onClick={handleDownload} disabled={loading}>
        {loading ? 'Downloading...' : 'Download Blend File'}
      </button>
      {error && <p style={{ color: 'red' }}>{error}</p>}
    </div>
  );
}
```

## Configuration

### For Production

Update your S3 configuration in the frontend `.env` file:

```env
NEXT_PUBLIC_S3_ENDPOINT=your-production-endpoint.com
NEXT_PUBLIC_S3_ACCESS_KEY=your-access-key
NEXT_PUBLIC_S3_SECRET_KEY=your-secret-key
NEXT_PUBLIC_S3_BUCKET=blender-vcs-prod
```

### Security Notes

⚠️ **Important**: Never expose S3 credentials in frontend code in production!

For production, you should:
1. Store credentials securely on your backend
2. Create a backend endpoint that handles S3 operations
3. Frontend calls your backend, backend calls S3
4. Use temporary credentials or pre-signed URLs when possible

## Testing with Your Database Record

Based on your database record:

```sql
object_id: 892a069d-defe-471d-bec6-280e6a9b4378
object_name: Untitled.blend
json_data_path: s3://blender-vcs-prod/784b71e4-3ade-4a42-8e30-d1d5d449b365_20251205_194615/Untitled.blend
```

Extract the path after `s3://blender-vcs-prod/`:
```
784b71e4-3ade-4a42-8e30-d1d5d449b365_20251205_194615/Untitled.blend
```

Use this as your `object_path` or `s3_path` parameter.

## Troubleshooting

### Connection Errors
- Verify S3 endpoint is correct (no `https://` or `http://` prefix needed in CLI script)
- Check if secure/insecure connection setting matches your S3 setup
- Ensure your credentials have read permissions

### Bucket Not Found
- Verify bucket name is exactly `blender-vcs-prod`
- Check if bucket exists in your S3 storage

### Object Not Found
- Verify the object path matches exactly what's in your database
- Check the `json_data_path` field and extract the path after the bucket name

### CORS Errors (API)
- In production, update the `allow_origins` in `download_api.py` to your frontend URL
- Make sure API server is running and accessible

## Next Steps

1. Install dependencies: `pip install -r download_requirements.txt`
2. Test with CLI script first: `python download_blend_file.py`
3. Once working, start API server: `python download_api.py`
4. Integrate with your frontend using the examples above
