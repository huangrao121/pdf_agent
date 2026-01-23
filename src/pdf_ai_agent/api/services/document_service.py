"""
Document service for handling PDF upload and management.
"""
import logging
from typing import BinaryIO, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from pdf_ai_agent.config.database.models.model_document import (
    DocsModel,
    DocStatus,
    JobTypeEnum,
)
from pdf_ai_agent.config.database.models.model_user import WorkspaceModel
from pdf_ai_agent.storage.local_storage import LocalStorageService
from pdf_ai_agent.jobs.job_queue import JobQueueService

logger = logging.getLogger(__name__)


class DocumentService:
    """Service for document operations."""
    
    # PDF magic bytes
    PDF_MAGIC_BYTES = b"%PDF-"
    
    # Maximum file size (100MB)
    MAX_FILE_SIZE = 100 * 1024 * 1024
    
    def __init__(self, db_session: AsyncSession, storage_service: LocalStorageService, job_queue_service: JobQueueService):
        """
        Initialize document service.
        
        Args:
            db_session: Database session
            storage_service: Storage service instance
            job_queue_service: Job queue service instance
        """
        self.db_session = db_session
        self.storage_service = storage_service
        self.job_queue_service = job_queue_service
    
    def _validate_pdf_magic_bytes(self, file_obj: BinaryIO) -> bool:
        """
        Validate PDF magic bytes.
        
        Args:
            file_obj: File object to validate
        
        Returns:
            True if valid PDF, False otherwise
        """
        # Read first 5 bytes
        file_obj.seek(0)
        magic = file_obj.read(5)
        file_obj.seek(0)
        
        return magic == self.PDF_MAGIC_BYTES
    
    async def _check_workspace_membership(
        self, 
        workspace_id: int, 
        user_id: int
    ) -> bool:
        """
        Check if user has access to workspace.
        
        Args:
            workspace_id: Workspace ID
            user_id: User ID
        
        Returns:
            True if user has access, False otherwise
        """
        query = select(WorkspaceModel).where(
            WorkspaceModel.workspace_id == workspace_id,
            WorkspaceModel.owner_user_id == user_id
        )
        result = await self.db_session.execute(query)
        workspace = result.scalar_one_or_none()
        
        return workspace is not None
    
    async def _check_duplicate_by_sha256(
        self,
        workspace_id: int,
        file_sha256: str
    ) -> Optional[DocsModel]:
        """
        Check if document with same SHA256 exists in workspace.
        
        Args:
            workspace_id: Workspace ID
            file_sha256: File SHA256 hash
        
        Returns:
            Existing document if found, None otherwise
        """
        query = select(DocsModel).where(
            DocsModel.workspace_id == workspace_id,
            DocsModel.file_sha256 == file_sha256
        )
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()
    
    async def upload_document(
        self,
        file_obj: BinaryIO,
        filename: str,
        workspace_id: int,
        user_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> DocsModel:
        """
        Upload a PDF document.
        
        Args:
            file_obj: File object
            filename: Original filename
            workspace_id: Workspace ID
            user_id: User ID
            title: Optional document title
            description: Optional document description
        
        Returns:
            Created or existing document
        
        Raises:
            HTTPException: If validation fails or upload fails
        """
        try:
            # 1. Validate workspace membership
            has_access = await self._check_workspace_membership(workspace_id, user_id)
            if not has_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to workspace"
                )
            
            # 2. Validate PDF magic bytes
            if not self._validate_pdf_magic_bytes(file_obj):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid PDF file: missing PDF magic bytes"
                )
            
            # 3. Compute SHA-256 and file size (streaming)
            file_sha256, file_size = self.storage_service.compute_sha256_streaming(
                file_obj
            )
            
            # 4. Validate file size
            if file_size == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File is empty"
                )
            
            if file_size > self.MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"File too large (max {self.MAX_FILE_SIZE} bytes)"
                )
            
            # 5. Check for duplicates (idempotency)
            existing_doc = await self._check_duplicate_by_sha256(
                workspace_id, file_sha256
            )
            if existing_doc:
                logger.info(
                    f"Document already exists: doc_id={existing_doc.doc_id}, "
                    f"sha256={file_sha256}"
                )
                return existing_doc
            
            # 6. Create document record first to get doc_id
            doc = DocsModel(
                workspace_id=workspace_id,
                owner_user_id=user_id,
                filename=filename,
                storage_uri="",  # Will be updated after storage write
                file_type="application/pdf",
                file_size=file_size,
                file_sha256=file_sha256,
                title=title or filename,
                description=description,
                status=DocStatus.UPLOADED,
            )
            
            self.db_session.add(doc)
            await self.db_session.flush()  # Get doc_id without committing
            
            # 7. Save file to storage (streaming)
            storage_uri = self.storage_service.save_file_streaming(
                file_obj=file_obj,
                workspace_id=workspace_id,
                doc_id=doc.doc_id,
                filename=filename
            )
            
            # 8. Update storage URI
            doc.storage_uri = storage_uri
            
            # 9. Commit document
            await self.db_session.commit()
            await self.db_session.refresh(doc)
            
            # 10. Enqueue parse metadata job
            try:
                await self.job_queue_service.enqueue_job(
                    session=self.db_session,
                    job_type=JobTypeEnum.DOC_PARSE_METADATA,
                    doc_id=doc.doc_id,
                    workspace_id=workspace_id,
                    payload={"filename": filename}
                )
            except Exception as e:
                # If job enqueue fails, still return success but log error
                # The document is already saved
                logger.error(f"Failed to enqueue parse job for doc_id={doc.doc_id}: {e}")
                # In strict mode, we could raise 500 here
                # For now, we allow the upload to succeed
            
            logger.info(
                f"Document uploaded successfully: doc_id={doc.doc_id}, "
                f"filename={filename}, size={file_size}"
            )
            
            return doc
            
        except HTTPException:
            await self.db_session.rollback()
            raise
        except Exception as e:
            await self.db_session.rollback()
            logger.error(f"Document upload failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Document upload failed: {str(e)}"
            )
