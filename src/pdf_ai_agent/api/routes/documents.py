"""
Document routes for PDF upload and management.
"""
import logging
import hashlib
from typing import Optional
from fastapi import (
    APIRouter, 
    Depends, 
    File, 
    Form, 
    UploadFile, 
    HTTPException,
    Path,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from pdf_ai_agent.config.database.init_database import get_db_session
from pdf_ai_agent.api.services.document_service import DocumentService
from pdf_ai_agent.api.schemas.document_schemas import (
    DocUploadResponse,
    DocStatusEnum,
    DocErrorResponse,
    DocListResponse,
    DocListItem,
    DocMetadataResponse,
)
from pdf_ai_agent.storage.local_storage import LocalStorageService, get_storage_service
from pdf_ai_agent.jobs.job_queue import JobQueueService, get_job_queue_service

router = APIRouter(prefix="/api/workspaces", tags=["Documents"])
logger = logging.getLogger(__name__)


def compute_etag(status: str, num_pages: Optional[int], updated_at: str) -> str:
    """
    Compute ETag for document metadata.
    
    Args:
        status: Document status
        num_pages: Number of pages (can be None)
        updated_at: Updated timestamp in ISO format
    
    Returns:
        ETag value (SHA256 hash)
    """
    # Combine the values into a string
    etag_input = f"{status}|{num_pages}|{updated_at}"
    # Compute SHA256 hash
    etag_hash = hashlib.sha256(etag_input.encode('utf-8')).hexdigest()
    return etag_hash


# Status mapping constant
DOC_STATUS_MAP = {
    "uploaded": DocStatusEnum.UPLOADED,
    "processing": DocStatusEnum.PROCESSING,
    "ready": DocStatusEnum.READY,
    "failed": DocStatusEnum.FAILED,
}


def get_document_service(
    session: AsyncSession = Depends(get_db_session),
    storage_service: LocalStorageService = Depends(get_storage_service),
    job_queue_service: JobQueueService = Depends(get_job_queue_service),
) -> DocumentService:
    """Get DocumentService instance."""
    return DocumentService(
        db_session=session,
        storage_service=storage_service,
        job_queue_service=job_queue_service
    )

@router.post(
    "/{workspace_id}/docs",
    response_model=DocUploadResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {
            "model": DocErrorResponse,
            "description": "Invalid file or not a PDF"
        },
        403: {
            "model": DocErrorResponse,
            "description": "Forbidden - no access to workspace"
        },
        413: {
            "model": DocErrorResponse,
            "description": "File too large (max 100MB)"
        },
        500: {
            "model": DocErrorResponse,
            "description": "Internal server error"
        },
    }
)
async def upload_document(
    workspace_id: int = Path(..., description="Workspace ID", gt=0),
    file: UploadFile = File(..., description="PDF file to upload"),
    user_id: int = Form(..., description="User ID (dev mode)"),
    title: Optional[str] = Form(None, description="Document title"),
    description: Optional[str] = Form(None, description="Document description"),
    doc_service: DocumentService = Depends(get_document_service),
):
    """
    Upload a PDF document to a workspace.
    
    **Authentication (Dev Mode):**
    - Requires `user_id` in form data
    - Production mode would use JWT token authentication
    
    **Validation:**
    - File must be a valid PDF (magic bytes check)
    - File size must be > 0 and < 100MB
    - User must have access to the workspace
    
    **Idempotency:**
    - Duplicate files (same SHA256) in the same workspace return existing document
    
    **Processing:**
    - File is stored in local disk storage
    - DOC_PARSE_METADATA job is enqueued for async processing
    - Returns immediately with UPLOADED status
    
    **Returns:**
    - 201: Document created successfully
    - 200: Document already exists (deduplication)
    - 400: Invalid file or validation error
    - 403: No access to workspace
    - 413: File too large
    - 500: Server error
    """
    try:
        # Validate file is provided
        if not file:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No file provided"
            )
        
        # Validate content type (weak signal)
        if file.content_type and file.content_type != "application/pdf":
            logger.warning(
                f"Content-Type is {file.content_type}, expected application/pdf. "
                "Continuing with magic bytes validation."
            )
        
        # Upload document
        doc = await doc_service.upload_document(
            file_obj=file.file,
            filename=file.filename or "document.pdf",
            workspace_id=workspace_id,
            user_id=user_id,
            title=title,
            description=description,
        )
        
        # Get status value (doc.status is an enum in DB)
        status_value = doc.status.value if hasattr(doc.status, 'value') else doc.status
        
        return DocUploadResponse(
            doc_id=doc.doc_id,
            filename=doc.filename,
            status=DOC_STATUS_MAP.get(status_value, DocStatusEnum.UPLOADED)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in upload_document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )


@router.get(
    "/{workspace_id}/docs",
    response_model=DocListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {
            "model": DocErrorResponse,
            "description": "Invalid limit or cursor"
        },
        403: {
            "model": DocErrorResponse,
            "description": "Forbidden - no access to workspace"
        },
    }
)
async def list_documents(
    workspace_id: int = Path(..., description="Workspace ID", gt=0),
    user_id: int = Query(..., description="User ID (dev mode)"),
    limit: int = Query(20, ge=1, le=100, description="Number of items per page"),
    cursor: Optional[str] = Query(None, description="Cursor for pagination"),
    doc_service: DocumentService = Depends(get_document_service),
):
    """
    List documents in a workspace with cursor-based pagination.
    
    **Authentication (Dev Mode):**
    - Requires `user_id` in query parameter
    - Production mode would use JWT token authentication
    
    **Pagination:**
    - Uses cursor-based pagination for stable results
    - Default limit: 20, max limit: 100
    - Cursor is opaque base64url-encoded JSON
    
    **Sorting:**
    - Sorted by created_at DESC, doc_id DESC (stable ordering)
    
    **Returns:**
    - 200: List of documents with optional next_cursor
    - 400: Invalid limit or cursor
    - 403: No access to workspace
    """
    try:
        # List documents
        documents, next_cursor = await doc_service.list_documents(
            workspace_id=workspace_id,
            user_id=user_id,
            limit=limit,
            cursor=cursor
        )
        
        # Convert to response format
        items = []
        for doc in documents:
            # Get status value
            status_value = doc.status.value if hasattr(doc.status, 'value') else doc.status
            
            items.append(DocListItem(
                doc_id=doc.doc_id,
                filename=doc.filename,
                title=doc.title or doc.filename,
                status=status_value.upper(),
                file_size=doc.file_size,
                num_pages=doc.num_pages,
                created_at=doc.created_at
            ))
        
        return DocListResponse(
            items=items,
            next_cursor=next_cursor
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in list_documents: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )


@router.get(
    "/{workspace_id}/docs/{doc_id}/metadata",
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "model": DocMetadataResponse,
            "description": "Document metadata"
        },
        304: {
            "description": "Not Modified - content hasn't changed"
        },
        404: {
            "model": DocErrorResponse,
            "description": "Document not found in workspace"
        },
        403: {
            "model": DocErrorResponse,
            "description": "Forbidden - no access to workspace"
        },
        500: {
            "model": DocErrorResponse,
            "description": "Internal server error"
        },
    }
)
async def get_document_metadata(
    request: Request,
    workspace_id: int = Path(..., description="Workspace ID", gt=0),
    doc_id: int = Path(..., description="Document ID", gt=0),
    user_id: int = Query(..., description="User ID (dev mode)"),
    doc_service: DocumentService = Depends(get_document_service),
):
    """
    Get document metadata by ID.
    
    **Authentication (Dev Mode):**
    - Requires `user_id` in query parameter
    - Production mode would use JWT token authentication
    
    **Authorization:**
    - User must have access to the workspace
    - Document must exist in the specified workspace
    
    **ETag Support:**
    - Returns `ETag` header computed from status, num_pages, and updated_at
    - Supports `If-None-Match` header for conditional requests
    - Returns 304 Not Modified if content hasn't changed
    
    **Returns:**
    - 200: Document metadata with full details
    - 304: Not Modified (when ETag matches)
    - 403: No access to workspace
    - 404: Document not found in workspace
    - 500: Server error
    """
    try:
        # Get document metadata
        doc = await doc_service.get_document_metadata(
            workspace_id=workspace_id,
            doc_id=doc_id,
            user_id=user_id
        )
        
        # Get status value
        status_value = doc.status.value if hasattr(doc.status, 'value') else doc.status
        
        # Compute ETag
        etag_value = compute_etag(
            status=status_value,
            num_pages=doc.num_pages,
            updated_at=doc.updated_at.isoformat()
        )
        
        # Check If-None-Match header
        if_none_match = request.headers.get("If-None-Match")
        if if_none_match:
            # Remove quotes if present
            if_none_match = if_none_match.strip('"')
            if if_none_match == etag_value:
                # Return 304 Not Modified with ETag header
                return Response(
                    status_code=status.HTTP_304_NOT_MODIFIED,
                    headers={"ETag": f'"{etag_value}"'}
                )
        
        # Return document metadata with ETag header
        return Response(
            content=DocMetadataResponse(
                doc_id=doc.doc_id,
                filename=doc.filename,
                file_type=doc.file_type,
                file_size=doc.file_size,
                file_sha256=doc.file_sha256,
                title=doc.title,
                author=doc.author,
                description=doc.description,
                language=doc.language,
                status=status_value.upper(),
                error_message=doc.error_message,
                num_pages=doc.num_pages,
                created_at=doc.created_at,
                updated_at=doc.updated_at
            ).model_dump_json(),
            media_type="application/json",
            headers={"ETag": f'"{etag_value}"'}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_document_metadata: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DB_READ_FAILED"
        )
