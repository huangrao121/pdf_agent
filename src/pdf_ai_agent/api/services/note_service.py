"""
Note service for handling note creation and management.
"""

import logging
import time
import json
import base64
from typing import Optional, List, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from fastapi import HTTPException, status

from pdf_ai_agent.config.database.models.model_document import (
    NoteModel,
    DocsModel,
)

from pdf_ai_agent.api.utilties.workspace_utils import check_workspace_membership

logger = logging.getLogger(__name__)


class NoteService:
    """Service for note operations."""

    def __init__(self, db_session: AsyncSession):
        """
        Initialize note service.

        Args:
            db_session: Database session
        """
        self.db_session = db_session


    async def _check_doc_exists(self, doc_id: int) -> Optional[DocsModel]:
        """
        Check if document exists.

        Args:
            doc_id: Document ID

        Returns:
            Document if exists, None otherwise
        """
        query = select(DocsModel).where(DocsModel.doc_id == doc_id)
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    def _clean_and_validate_markdown(markdown: str) -> str:
        """
        Clean and validate markdown content.

        Args:
            markdown: Raw markdown content

        Returns:
            Cleaned markdown content

        Raises:
            ValueError: If markdown is blank after trimming
        """
        cleaned = markdown.strip()
        if not cleaned:
            raise ValueError("Markdown content cannot be blank")
        return cleaned

    @staticmethod
    def _generate_title_from_markdown(markdown: str) -> str:
        """
        Generate title from markdown content.

        Tries to extract first H1 heading, falls back to "Untitled Note".

        Args:
            markdown: Markdown content

        Returns:
            Generated title
        """
        # Try to find first H1 heading (# Title)
        lines = markdown.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('# ') and len(line) > 2:
                # Extract title and limit to 255 chars
                title = line[2:].strip()
                if title:
                    return title[:255]
        
        # Fallback to "Untitled Note"
        return "Untitled Note"

    async def create_note(
        self,
        workspace_id: int,
        user_id: int,
        content_markdown: str,
        doc_id: Optional[int] = None,
        title: Optional[str] = None,
    ) -> NoteModel:
        """
        Create a new note.

        Args:
            workspace_id: Workspace ID
            user_id: User ID
            content_markdown: Markdown content
            doc_id: Optional document ID (for doc-scoped notes)
            title: Optional title (auto-generated if not provided)

        Returns:
            Created note model

        Raises:
            HTTPException: If validation fails or access denied
        """
        try:
            # 1. Validate workspace membership
            has_access = await check_workspace_membership(workspace_id, user_id, self.db_session)
            if not has_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="FORBIDDEN: No permission to access workspace"
                )

            # 2. Validate doc if provided
            if doc_id is not None:
                doc = await self._check_doc_exists(doc_id)
                if doc is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="DOC_NOT_FOUND: Document not found"
                    )
                
                # 3. Validate doc belongs to workspace
                if doc.workspace_id != workspace_id:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="DOC_WORKSPACE_MISMATCH: Document does not belong to workspace"
                    )

            # 4. Clean markdown (Pydantic already validated, but defensive programming)
            cleaned_markdown = content_markdown.strip()
            if not cleaned_markdown:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="INVALID_ARGUMENT: content_markdown is empty"
                )

            # 5. Generate title if not provided
            if not title or not title.strip():
                title = self._generate_title_from_markdown(cleaned_markdown)
            else:
                title = title.strip()[:255]  # Limit to 255 chars

            # 6. Create note
            note = NoteModel(
                workspace_id=workspace_id,
                doc_id=doc_id,
                owner_user_id=user_id,
                title=title,
                markdown=cleaned_markdown,
            )

            self.db_session.add(note)
            await self.db_session.commit()
            await self.db_session.refresh(note)

            logger.info(
                f"Note created successfully: note_id={note.note_id}, "
                f"workspace_id={workspace_id}, doc_id={doc_id}, user_id={user_id}"
            )

            return note

        except HTTPException:
            await self.db_session.rollback()
            raise
        except Exception as e:
            await self.db_session.rollback()
            logger.error(f"Note creation failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="INTERNAL_ERROR: An unexpected error occurred"
            )

    async def patch_note(
        self,
        workspace_id: int,
        note_id: int,
        user_id: int,
        title: Optional[str] = None,
        content_markdown: Optional[str] = None,
    ) -> NoteModel:
        """
        Partially update a note.

        Args:
            workspace_id: Workspace ID
            note_id: Note ID
            user_id: User ID
            title: Optional new title
            content_markdown: Optional new markdown content

        Returns:
            Updated note model

        Raises:
            HTTPException: If validation fails or access denied
        """
        start_time = time.monotonic()
        try:
            # 1. Check workspace access
            has_access = await check_workspace_membership(workspace_id, user_id, self.db_session)
            if not has_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="FORBIDDEN_WORKSPACE"
                )

            # 2. Validate request body
            if title is None and content_markdown is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="INVALID_REQUEST: body is empty"
                )

            # 3. Query note with workspace_id filter
            query = select(NoteModel).where(
                and_(
                    NoteModel.note_id == note_id,
                    NoteModel.workspace_id == workspace_id,
                )
            )
            result = await self.db_session.execute(query)
            note = result.scalar_one_or_none()

            if note is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="NOTE_NOT_FOUND"
                )

            fields_updated: list[str] = []

            # 4. Update title if provided
            if title is not None:
                cleaned_title = title.strip()
                if not cleaned_title:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="INVALID_ARGUMENT: title is empty"
                    )
                note.title = cleaned_title[:255]
                fields_updated.append("title")

            # 5. Update markdown if provided
            if content_markdown is not None:
                cleaned_markdown = content_markdown.strip()
                if not cleaned_markdown:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="INVALID_ARGUMENT: content_markdown is empty"
                    )
                note.markdown = cleaned_markdown
                fields_updated.append("content_markdown")

            # 6. Increment version
            note.version = (note.version or 0) + 1

            await self.db_session.commit()
            await self.db_session.refresh(note)

            latency_ms = int((time.monotonic() - start_time) * 1000)
            logger.info(
                "Note patched successfully: workspace_id=%s, note_id=%s, user_id=%s, "
                "fields_updated=%s, new_version=%s, latency_ms=%s",
                workspace_id,
                note_id,
                user_id,
                fields_updated,
                note.version,
                latency_ms,
            )

            return note

        except HTTPException:
            await self.db_session.rollback()
            raise
        except Exception as e:
            await self.db_session.rollback()
            logger.error(f"Patch note failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="DB_QUERY_FAILED"
            )

    @staticmethod
    def encode_cursor(note_id: int, created_at: datetime) -> str:
        """
        Encode cursor for pagination.

        Args:
            note_id: Note ID
            created_at: Created timestamp

        Returns:
            Base64url encoded JSON cursor
        """
        cursor_data = {"note_id": note_id, "created_at": created_at.isoformat()}
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
            Tuple of (note_id, created_at)

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
            if "note_id" not in cursor_data or "created_at" not in cursor_data:
                raise ValueError("Missing required fields in cursor")

            note_id = int(cursor_data["note_id"])
            created_at = datetime.fromisoformat(cursor_data["created_at"])

            return note_id, created_at

        except (ValueError, KeyError, json.JSONDecodeError) as e:
            logger.warning(f"Invalid cursor: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="INVALID_CURSOR"
            )

    async def list_notes(
        self,
        workspace_id: int,
        user_id: int,
        doc_id: Optional[int] = None,
        limit: int = 20,
        cursor: Optional[str] = None,
    ) -> Tuple[List[NoteModel], Optional[str]]:
        """
        List notes in a workspace with cursor-based pagination.

        Args:
            workspace_id: Workspace ID
            user_id: User ID
            doc_id: Optional document ID to filter notes
            limit: Number of items per page (1-100, validated by FastAPI)
            cursor: Optional cursor for pagination

        Returns:
            Tuple of (notes list, next_cursor)

        Raises:
            HTTPException: If validation fails or access denied
        """
        try:
            # 1. Check workspace access
            has_access = await check_workspace_membership(workspace_id, user_id, self.db_session)
            if not has_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="FORBIDDEN_WORKSPACE"
                )

            # 2. If doc_id is provided, validate it exists and belongs to workspace
            if doc_id is not None:
                doc = await self._check_doc_exists(doc_id)
                if doc is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="DOC_NOT_FOUND"
                    )
                
                if doc.workspace_id != workspace_id:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="DOC_WORKSPACE_MISMATCH"
                    )

            # 3. Clamp limit to max 100
            limit = min(limit, 100)

            # 4. Build query with stable ordering
            query = select(NoteModel).where(NoteModel.workspace_id == workspace_id)

            # 5. Apply doc_id filter if provided
            if doc_id is not None:
                query = query.where(NoteModel.doc_id == doc_id)

            # 6. Apply cursor filter if provided
            if cursor:
                cursor_note_id, cursor_created_at = self.decode_cursor(cursor)
                # WHERE (created_at < cursor_created_at) OR (created_at = cursor_created_at AND note_id < cursor_note_id)
                query = query.where(
                    or_(
                        NoteModel.created_at < cursor_created_at,
                        and_(
                            NoteModel.created_at == cursor_created_at,
                            NoteModel.note_id < cursor_note_id,
                        ),
                    )
                )

            # 7. Apply ordering and limit
            query = query.order_by(
                NoteModel.created_at.desc(), NoteModel.note_id.desc()
            ).limit(
                limit + 1
            )  # Fetch one extra to check if there's a next page

            # 8. Execute query
            result = await self.db_session.execute(query)
            notes = list(result.scalars().all())

            # 9. Check if there's a next page
            has_next_page = len(notes) > limit
            if has_next_page:
                notes = notes[:limit]  # Remove the extra item
                # Generate next cursor from last item
                last_note = notes[-1]
                next_cursor = self.encode_cursor(last_note.note_id, last_note.created_at)
            else:
                next_cursor = None

            return notes, next_cursor

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"List notes failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="DB_QUERY_FAILED"
            )

    async def get_note(
        self,
        workspace_id: int,
        note_id: int,
        user_id: int,
    ) -> Tuple[NoteModel, list]:
        """
        Get a note with its associated anchors.

        Args:
            workspace_id: Workspace ID
            note_id: Note ID
            user_id: User ID

        Returns:
            Tuple of (note model, list of anchor models sorted by created_at ASC)

        Raises:
            HTTPException: If validation fails or access denied
        """
        try:
            # 1. Check workspace access
            has_access = await check_workspace_membership(workspace_id, user_id, self.db_session)
            if not has_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="FORBIDDEN_WORKSPACE"
                )

            # 2. Query note with workspace_id filter
            query = select(NoteModel).where(
                and_(
                    NoteModel.note_id == note_id,
                    NoteModel.workspace_id == workspace_id,
                )
            )
            result = await self.db_session.execute(query)
            note = result.scalar_one_or_none()

            # 3. Return 404 if note not found or doesn't belong to workspace
            if note is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="NOTE_NOT_FOUND"
                )

            # 4. Import AnchorModel here to avoid circular imports
            from pdf_ai_agent.config.database.models.model_document import AnchorModel

            # 5. Query anchors for this note, sorted by created_at ASC
            anchor_query = select(AnchorModel).where(
                AnchorModel.note_id == note_id
            ).order_by(AnchorModel.created_at.asc())

            anchor_result = await self.db_session.execute(anchor_query)
            anchors = list(anchor_result.scalars().all())

            logger.info(
                f"Note retrieved successfully: note_id={note_id}, "
                f"workspace_id={workspace_id}, user_id={user_id}, "
                f"anchors_count={len(anchors)}"
            )

            return note, anchors

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Get note failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="DB_QUERY_FAILED"
            )
