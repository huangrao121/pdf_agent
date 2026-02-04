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
from sqlalchemy.ext.asyncio import AsyncSession

from pdf_ai_agent.config.database.init_database import get_db_session
from pdf_ai_agent.api.services.note_service import NoteService
from pdf_ai_agent.api.schemas.note_schemas import (
    CreateNoteRequest,
    CreateNoteResponse,
    NoteErrorResponse,
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
