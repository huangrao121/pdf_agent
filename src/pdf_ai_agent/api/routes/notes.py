"""
Note routes for note creation and management.
"""

import logging
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Query,
    status,
)
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from pdf_ai_agent.config.database.init_database import get_db_session
from pdf_ai_agent.api.services.note_service import NoteService
from pdf_ai_agent.api.schemas.note_schemas import (
    CreateNoteRequest,
    CreateNoteResponse,
    NoteErrorResponse,
    NoteListItem,
    ListNotesResponse,
)

router = APIRouter(prefix="/api/workspaces", tags=["Notes"])
logger = logging.getLogger(__name__)


def get_note_service(
    session: AsyncSession = Depends(get_db_session),
) -> NoteService:
    """Get NoteService instance."""
    return NoteService(db_session=session)


@router.post(
    "/{workspace_id}/notes",
    response_model=CreateNoteResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": NoteErrorResponse, "description": "Invalid request - content_markdown is empty"},
        403: {"model": NoteErrorResponse, "description": "Forbidden - no access to workspace"},
        404: {"model": NoteErrorResponse, "description": "Document not found"},
        409: {"model": NoteErrorResponse, "description": "Document and workspace mismatch"},
        500: {"model": NoteErrorResponse, "description": "Internal server error"},
    },
)
async def create_note(
    request: CreateNoteRequest,
    workspace_id: int = Path(..., description="Workspace ID", gt=0),
    user_id: int = Query(..., description="User ID (dev mode)"),
    note_service: NoteService = Depends(get_note_service),
):
    """
    Create a new markdown note in a workspace.

    **Authentication (Dev Mode):**
    - Requires `user_id` in query parameter
    - Production mode would use JWT token authentication

    **Note Types:**
    - **Workspace-level note**: If `doc_id` is not provided
    - **Doc-scoped note**: If `doc_id` is provided

    **Validation:**
    - User must have access to the workspace (member+)
    - `content_markdown` is required and cannot be blank after trim
    - If `doc_id` provided, document must exist and belong to the workspace
    - Title is auto-generated if not provided (from first H1 heading or "Untitled Note")

    **Returns:**
    - 201: Note created successfully
    - 400: content_markdown is empty (INVALID_ARGUMENT)
    - 403: No permission to access workspace (FORBIDDEN)
    - 404: Document not found (DOC_NOT_FOUND)
    - 409: Document and workspace mismatch (DOC_WORKSPACE_MISMATCH)
    - 500: Server error
    """
    try:
        # Create note
        note = await note_service.create_note(
            workspace_id=workspace_id,
            user_id=user_id,
            content_markdown=request.content_markdown,
            doc_id=request.doc_id,
            title=request.title,
        )

        return CreateNoteResponse(note_id=note.note_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in create_note: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="INTERNAL_ERROR: An unexpected error occurred"
        )


@router.get(
    "/{workspace_id}/notes",
    response_model=ListNotesResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": NoteErrorResponse, "description": "Invalid cursor"},
        403: {"model": NoteErrorResponse, "description": "Forbidden - no access to workspace"},
        404: {"model": NoteErrorResponse, "description": "Document not found (if doc_id provided)"},
        409: {"model": NoteErrorResponse, "description": "Document workspace mismatch"},
        500: {"model": NoteErrorResponse, "description": "Internal server error"},
    },
)
async def list_notes(
    workspace_id: int = Path(..., description="Workspace ID", gt=0),
    user_id: int = Query(..., description="User ID (dev mode)"),
    doc_id: Optional[int] = Query(None, description="Document ID to filter notes (optional)"),
    limit: int = Query(20, ge=1, le=100, description="Number of items per page"),
    cursor: Optional[str] = Query(None, description="Cursor for pagination"),
    note_service: NoteService = Depends(get_note_service),
):
    """
    List notes in a workspace with cursor-based pagination.

    **Authentication (Dev Mode):**
    - Requires `user_id` in query parameter
    - Production mode would use JWT token authentication

    **Filtering:**
    - If `doc_id` is provided, returns only notes associated with that document
    - If `doc_id` is not provided, returns all notes in the workspace

    **Pagination:**
    - Uses cursor-based pagination for stable results
    - Default limit: 20, max limit: 100
    - Cursor is opaque base64url-encoded JSON
    - Returns `next_cursor` in response if there are more results

    **Sorting:**
    - Sorted by created_at DESC, note_id DESC (stable ordering)

    **Response:**
    - Does not include markdown_content, anchors, or chunks
    - Only returns note metadata for list display

    **Returns:**
    - 200: List of notes with optional next_cursor
    - 400: Invalid cursor
    - 403: No access to workspace
    - 404: Document not found (if doc_id provided)
    - 409: Document doesn't belong to workspace
    - 500: Server error
    """
    try:
        # List notes
        notes, next_cursor = await note_service.list_notes(
            workspace_id=workspace_id,
            user_id=user_id,
            doc_id=doc_id,
            limit=limit,
            cursor=cursor,
        )

        # Convert to response format
        items = [
            NoteListItem(
                note_id=note.note_id,
                workspace_id=note.workspace_id,
                doc_id=note.doc_id,
                title=note.title,
                version=note.version,
                owner_user_id=note.owner_user_id,
                created_at=note.created_at,
                updated_at=note.updated_at,
            )
            for note in notes
        ]

        return ListNotesResponse(notes=items, next_cursor=next_cursor)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in list_notes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="INTERNAL_ERROR: An unexpected error occurred"
        )
