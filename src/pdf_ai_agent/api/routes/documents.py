"""
Document routes for PDF upload and management.
"""
import logging
from typing import Optional
from fastapi import (
    APIRouter, 
    Depends, 
    File, 
    Form, 
    UploadFile, 
    HTTPException,
    Path,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from pdf_ai_agent.config.database.init_database import get_db_session
from pdf_ai_agent.api.services.document_service import DocumentService
from pdf_ai_agent.api.schemas.document_schemas import (
    DocUploadResponse,
    DocStatusEnum,
    DocErrorResponse,
)
from pdf_ai_agent.storage.local_storage import LocalStorageService, get_storage_service
from pdf_ai_agent.jobs.job_queue import JobQueueService, get_job_queue_service

router = APIRouter(prefix="/api/workspaces", tags=["Documents"])
logger = logging.getLogger(__name__)


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
