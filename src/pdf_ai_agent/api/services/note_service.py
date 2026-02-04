"""
Note service for handling note creation and management.
"""

import logging
import re
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
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
