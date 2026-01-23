# PDF Upload API Documentation

## Endpoint: Upload PDF Document

**POST** `/api/workspaces/{workspace_id}/docs`

Upload a PDF document to a workspace with deduplication, validation, and async processing.

### Authentication

**Dev Mode:** Provide `user_id` in form data
**Production:** JWT token authentication (not implemented in MVP)

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| workspace_id | integer | Yes | ID of the workspace to upload to (must be > 0) |

### Form Data Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| file | file | Yes | PDF file to upload (Content-Type: application/pdf) |
| user_id | integer | Yes | User ID (dev mode authentication) |
| title | string | No | Document title (defaults to filename) |
| description | string | No | Document description |

### Request Example

```bash
curl -X POST "http://localhost:8000/api/workspaces/1/docs" \
  -F "file=@paper.pdf" \
  -F "user_id=123" \
  -F "title=Research Paper" \
  -F "description=Important research findings"
```

### Response

#### Success (201 Created)

```json
{
  "doc_id": 456,
  "filename": "paper.pdf",
  "status": "UPLOADED"
}
```

#### Document Already Exists (201 Created)

When a document with the same SHA-256 hash already exists in the workspace, returns the existing document:

```json
{
  "doc_id": 456,
  "filename": "original_name.pdf",
  "status": "UPLOADED"
}
```

### Error Responses

#### 400 Bad Request - Invalid File

```json
{
  "status": "error",
  "error": {
    "error_code": "INVALID_FILE",
    "message": "Invalid PDF file: missing PDF magic bytes"
  }
}
```

**Causes:**
- File is not a valid PDF (missing `%PDF-` magic bytes)
- File is empty (size = 0)
- No file provided

#### 403 Forbidden - No Workspace Access

```json
{
  "status": "error",
  "error": {
    "error_code": "FORBIDDEN",
    "message": "Access denied to workspace"
  }
}
```

**Cause:** User does not have access to the specified workspace

#### 413 Payload Too Large

```json
{
  "status": "error",
  "error": {
    "error_code": "FILE_TOO_LARGE",
    "message": "File too large (max 104857600 bytes)"
  }
}
```

**Cause:** File size exceeds 100MB limit

#### 500 Internal Server Error

```json
{
  "status": "error",
  "error": {
    "error_code": "STORAGE_WRITE_FAILED",
    "message": "Document upload failed: <details>"
  }
}
```

**Causes:**
- Storage write failure
- Database write failure
- Job queue failure

### Features

#### 1. PDF Validation

- **Magic Bytes Check**: Validates file starts with `%PDF-`
- **Size Check**: File must be > 0 bytes and < 100MB
- **Content-Type**: Weak signal, magic bytes are authoritative

#### 2. Deduplication

- **Hash-Based**: Uses SHA-256 of file content
- **Workspace-Scoped**: Same file can exist in different workspaces
- **Idempotent**: Uploading same file returns existing document

#### 3. Streaming Processing

- **Memory Efficient**: Uses 8MB chunks for reading/hashing
- **Large File Support**: Can handle files up to 100MB without OOM
- **Consistent Hashing**: Same file produces same SHA-256 regardless of chunk size

#### 4. Async Processing

- **Background Jobs**: Enqueues `DOC_PARSE_METADATA` job after upload
- **Status Tracking**: Document status progresses from UPLOADED → READY/FAILED
- **Non-Blocking**: Upload returns immediately, parsing happens asynchronously

### Storage

- **Type**: Local disk storage (MVP)
- **Location**: `/tmp/pdf_storage` (configurable via `STORAGE_BASE_PATH` env var)
- **Structure**: `workspace_id/doc_id_filename.pdf`
- **URI Format**: `local://workspace_id/doc_id_filename.pdf`

### Database Schema

#### docs table updates
- `num_pages`: INT NULL - total page count (populated by DOC_PARSE_METADATA job)
- `status`: ENUM('uploaded', 'processing', 'ready', 'failed')

#### doc_pages table (new)
```sql
CREATE TABLE doc_page (
  id BIGSERIAL PRIMARY KEY,
  doc_id INT NOT NULL REFERENCES doc(doc_id) ON DELETE CASCADE,
  page INT NOT NULL,
  width_pt FLOAT NOT NULL,
  height_pt FLOAT NOT NULL,
  rotation INT NOT NULL DEFAULT 0,
  text_layer_available BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (doc_id, page)
);
```

### Security Considerations

1. **File Validation**: Magic bytes check prevents non-PDF uploads
2. **Size Limits**: 100MB max prevents DoS attacks
3. **Workspace Authorization**: User must have access to workspace
4. **No Path Traversal**: Storage paths are generated server-side
5. **SHA-256 Integrity**: Ensures file integrity and enables dedup

### Performance Characteristics

- **Upload Speed**: ~50-100 MB/s (depends on disk I/O)
- **Memory Usage**: O(chunk_size) = 8MB constant, not O(file_size)
- **Database Queries**: 3 queries per upload (workspace check, dedup check, insert)
- **Storage Operations**: 1 streaming write per upload

### Future Enhancements

- JWT token authentication
- S3/cloud storage support
- Progressive upload with progress reporting
- Multi-tenant permissions (role-based access)
- Thumbnail generation
- OCR for scanned PDFs
- Full-text search indexing
