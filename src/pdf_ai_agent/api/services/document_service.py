"""
Document service for handling PDF upload and management.
"""

import logging
import json
import base64
from typing import BinaryIO, Tuple, Optional, List, Dict, Any, AsyncIterator
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
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

    def __init__(
        self,
        db_session: AsyncSession,
        storage_service: LocalStorageService,
        job_queue_service: JobQueueService,
    ):
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
        self, workspace_id: int, user_id: int
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
            WorkspaceModel.owner_user_id == user_id,
        )
        result = await self.db_session.execute(query)
        workspace = result.scalar_one_or_none()

        return workspace is not None

    async def _check_duplicate_by_sha256(
        self, workspace_id: int, file_sha256: str
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
            DocsModel.workspace_id == workspace_id, DocsModel.file_sha256 == file_sha256
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
                    detail="Access denied to workspace",
                )

            # 2. Validate PDF magic bytes
            if not self._validate_pdf_magic_bytes(file_obj):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid PDF file: missing PDF magic bytes",
                )

            # 3. Compute SHA-256 and file size (streaming)
            file_sha256, file_size = self.storage_service.compute_sha256_streaming(
                file_obj
            )

            # 4. Validate file size
            if file_size == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty"
                )

            if file_size > self.MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"File too large (max {self.MAX_FILE_SIZE} bytes)",
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
                filename=filename,
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
                    payload={"filename": filename},
                )
            except Exception as e:
                # If job enqueue fails, still return success but log error
                # The document is already saved
                logger.error(
                    f"Failed to enqueue parse job for doc_id={doc.doc_id}: {e}"
                )
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
                detail=f"Document upload failed: {str(e)}",
            )

    @staticmethod
    def encode_cursor(doc_id: int, created_at: datetime) -> str:
        """
        Encode cursor for pagination.

        Args:
            doc_id: Document ID
            created_at: Created timestamp

        Returns:
            Base64url encoded JSON cursor
        """
        cursor_data = {"doc_id": doc_id, "created_at": created_at.isoformat()}
        cursor_json = json.dumps(cursor_data, separators=(",", ":"))
        cursor_bytes = cursor_json.encode("utf-8")
        # Use urlsafe_b64encode and strip padding
        encoded = base64.urlsafe_b64encode(cursor_bytes).decode("utf-8").rstrip("=")
        return encoded

    @staticmethod
    def decode_cursor(cursor: str) -> Tuple[int, datetime]:
        """
        Decode cursor for pagination.

        Args:
            cursor: Base64url encoded cursor

        Returns:
            Tuple of (doc_id, created_at)

        Raises:
            HTTPException: If cursor is invalid
        """
        try:
            # Add padding if needed
            padding = 4 - (len(cursor) % 4)
            if padding != 4:
                cursor += "=" * padding

            cursor_bytes = base64.urlsafe_b64decode(cursor.encode("utf-8"))
            cursor_json = cursor_bytes.decode("utf-8")
            cursor_data = json.loads(cursor_json)

            # Validate required fields
            if "doc_id" not in cursor_data or "created_at" not in cursor_data:
                raise ValueError("Missing required fields in cursor")

            doc_id = int(cursor_data["doc_id"])
            created_at = datetime.fromisoformat(cursor_data["created_at"])

            return doc_id, created_at

        except (ValueError, KeyError, json.JSONDecodeError) as e:
            logger.warning(f"Invalid cursor: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid cursor: INVALID_CURSOR",
            )

    async def list_documents(
        self,
        workspace_id: int,
        user_id: int,
        limit: int = 20,
        cursor: Optional[str] = None,
    ) -> Tuple[List[DocsModel], Optional[str]]:
        """
        List documents in a workspace with cursor-based pagination.

        Args:
            workspace_id: Workspace ID
            user_id: User ID
            limit: Number of items per page (1-100, validated by FastAPI)
            cursor: Optional cursor for pagination

        Returns:
            Tuple of (documents list, next_cursor)

        Raises:
            HTTPException: If validation fails or access denied
        """
        # 1. Check workspace access
        has_access = await self._check_workspace_membership(workspace_id, user_id)
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN_WORKSPACE"
            )

        # 2. Build query with stable ordering
        query = select(DocsModel).where(DocsModel.workspace_id == workspace_id)

        # 3. Apply cursor filter if provided
        if cursor:
            cursor_doc_id, cursor_created_at = self.decode_cursor(cursor)
            # WHERE (created_at < cursor_created_at) OR (created_at = cursor_created_at AND id < cursor_doc_id)
            query = query.where(
                or_(
                    DocsModel.created_at < cursor_created_at,
                    and_(
                        DocsModel.created_at == cursor_created_at,
                        DocsModel.doc_id < cursor_doc_id,
                    ),
                )
            )

        # 4. Apply ordering and limit
        query = query.order_by(
            DocsModel.created_at.desc(), DocsModel.doc_id.desc()
        ).limit(
            limit + 1
        )  # Fetch one extra to check if there's a next page

        # 5. Execute query
        result = await self.db_session.execute(query)
        documents = list(result.scalars().all())

        # 6. Determine if there's a next page
        next_cursor = None
        if len(documents) > limit:
            # There's a next page
            documents = documents[:limit]
            last_doc = documents[-1]
            next_cursor = self.encode_cursor(last_doc.doc_id, last_doc.created_at)

        return documents, next_cursor

    async def get_document_metadata(
        self, workspace_id: int, doc_id: int, user_id: int
    ) -> DocsModel:
        """
        Get document metadata by ID.

        Args:
            workspace_id: Workspace ID
            doc_id: Document ID
            user_id: User ID

        Returns:
            Document model

        Raises:
            HTTPException: If validation fails or access denied
        """
        # 1. Check workspace access
        has_access = await self._check_workspace_membership(workspace_id, user_id)
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN_WORKSPACE"
            )

        # 2. Query document with workspace condition
        # This ensures we can't access a doc from a different workspace
        query = select(DocsModel).where(
            and_(DocsModel.doc_id == doc_id, DocsModel.workspace_id == workspace_id)
        )

        result = await self.db_session.execute(query)
        doc = result.scalar_one_or_none()

        # 3. Return 404 if not found (don't distinguish between "not exists" vs "different workspace")
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="DOC_NOT_FOUND"
            )

        return doc

    async def stream_document_file(
        self,
        workspace_id: int,
        doc_id: int,
        user_id: int,
        range_header: Optional[str] = None,
        chunk_size: int = 512 * 1024,  # 512KB chunks
    ) -> Tuple[DocsModel, Optional[Tuple[int, int]], int]:
        """
        Get document and prepare for streaming with range support.

        Args:
            workspace_id: Workspace ID
            doc_id: Document ID
            user_id: User ID
            range_header: Optional HTTP Range header value
            chunk_size: Chunk size for streaming (default 512KB)

        Returns:
            Tuple of (document, range_tuple, file_size)
            - document: Document model
            - range_tuple: (start, end) if range requested, None otherwise
            - file_size: Total file size in bytes

        Raises:
            HTTPException: If validation fails or access denied
        """
        # 1. Check workspace access
        has_access = await self._check_workspace_membership(workspace_id, user_id)
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN_WORKSPACE"
            )

        # 2. Query document with workspace condition
        query = select(DocsModel).where(
            and_(DocsModel.doc_id == doc_id, DocsModel.workspace_id == workspace_id)
        )

        result = await self.db_session.execute(query)
        doc = result.scalar_one_or_none()

        # 3. Return 404 if not found
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="DOC_NOT_FOUND"
            )

        # 4. Check document status - must be READY
        if doc.status != DocStatus.READY:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="DOC_NOT_READY"
            )

        # 5. Get file size
        try:
            file_size = self.storage_service.get_file_size(doc.storage_uri)
        except FileNotFoundError:
            logger.error(f"File not found in storage: {doc.storage_uri}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="STORAGE_READ_FAILED",
            )
        except Exception as e:
            logger.error(f"Failed to get file size: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="STORAGE_READ_FAILED",
            )

        # 6. Parse range header if provided
        range_tuple = None
        if range_header:
            range_tuple = self.storage_service.parse_range_header(
                range_header, file_size
            )
            # If range parsing failed, it's an invalid range
            # We'll handle this in the route to return 416

        return doc, range_tuple, file_size

    async def get_file_stream(
        self,
        storage_uri: str,
        start: int,
        end: int,
        chunk_size: int = 512 * 1024,  # 512KB chunks
    ) -> AsyncIterator[bytes]:
        """
        Get async iterator for streaming file content.

        Args:
            storage_uri: Storage URI
            start: Start byte position (inclusive)
            end: End byte position (inclusive)
            chunk_size: Chunk size for streaming

        Yields:
            Chunks of file data

        Raises:
            HTTPException: If file read fails
        """
        try:
            async for chunk in self.storage_service.stream_file_range(
                storage_uri, start, end, chunk_size
            ):
                yield chunk
        except FileNotFoundError:
            logger.error(f"File not found in storage: {storage_uri}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="STORAGE_READ_FAILED",
            )
        except Exception as e:
            logger.error(f"Failed to stream file: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="STORAGE_READ_FAILED",
            )
