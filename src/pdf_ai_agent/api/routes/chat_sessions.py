"""
Chat session routes.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from pdf_ai_agent.api.schemas.chat_schemas import (
    ChatSessionContext,
    ChatDefaults,
    CreateChatSessionRequest,
    CreateChatSessionResponse,
    ChatErrorResponse,
    ChatSessionData,
)
from pdf_ai_agent.api.services.chat_session_service import ChatSessionService
from pdf_ai_agent.config.database.init_database import get_db_session

router = APIRouter(prefix="/api/workspaces", tags=["Chat Sessions"])
logger = logging.getLogger(__name__)


def get_chat_session_service(
    session: AsyncSession = Depends(get_db_session),
) -> ChatSessionService:
    """Get ChatSessionService instance."""
    return ChatSessionService(db_session=session)


@router.post(
    "/{workspace_id}/chat/sessions",
    response_model=CreateChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ChatErrorResponse, "description": "Invalid request"},
        403: {"model": ChatErrorResponse, "description": "Forbidden - no access to workspace"},
        404: {"model": ChatErrorResponse, "description": "Workspace/note/doc not found"},
        409: {"model": ChatErrorResponse, "description": "client_request_id already used"},
        422: {"model": ChatErrorResponse, "description": "Anchor validation failed"},
        500: {"model": ChatErrorResponse, "description": "Internal server error"},
    },
)
async def create_chat_session(
    request: CreateChatSessionRequest,
    workspace_id: int = Path(..., description="Workspace ID", gt=0),
    user_id: int = Query(..., description="User ID (dev mode)"),
    chat_service: ChatSessionService = Depends(get_chat_session_service),
):
    """
    Create a new chat session in a workspace.

    **Authentication (Dev Mode):**
    - Requires `user_id` in query parameter

    **Validation:**
    - User must have access to workspace (member+)
    - mode must be ask|assist|agent
    - defaults must be within allowed ranges
    - context note/doc/anchor ownership is enforced
    """
    try:
        session_model = await chat_service.create_session(
            workspace_id=workspace_id,
            user_id=user_id,
            title=request.title,
            mode=request.mode.value if request.mode else None,
            context=request.context.model_dump() if request.context else None,
            defaults=request.defaults.model_dump() if request.defaults else None,
            client_request_id=request.client_request_id,
        )

        context_payload = session_model.context_json or {
            "note_id": None,
            "anchor_ids": [],
            "doc_id": None,
        }
        defaults_payload = session_model.defaults_json or {
            "model": "gpt-4.1-mini",
            "temperature": 0.2,
            "top_p": 1.0,
            "system_prompt": None,
            "retrieval": {"enabled": True, "top_k": 8, "rerank": False},
        }

        session_data = ChatSessionData(
            id=session_model.session_id,
            workspace_id=session_model.workspace_id,
            title=session_model.title,
            mode=session_model.mode,
            context=ChatSessionContext(**context_payload),
            defaults=ChatDefaults(**defaults_payload),
            created_at=session_model.created_at,
            updated_at=session_model.updated_at,
        )

        return CreateChatSessionResponse(session=session_data)

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Unexpected error in create_chat_session: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="INTERNAL_ERROR: An unexpected error occurred",
        )
