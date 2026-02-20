"""
Chat session routes.
"""

import logging
import json
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pdf_ai_agent.api.schemas.chat_schemas import (
    ChatContextSummary,
    ChatSessionContext,
    ChatSessionListItem,
    ChatDefaults,
    ChatSessionDetail,
    CreateChatSessionRequest,
    CreateChatSessionResponse,
    ChatErrorResponse,
    ChatSessionData,
    ListChatSessionsResponse,
    MessageContentItem,
    MessageItem,
    MessagePage,
    GetChatSessionResponse,
    AskMessageRequest,
    AskMessageResponse,
)
from pdf_ai_agent.api.services.chat_session_service import ChatSessionService
from pdf_ai_agent.config.database.init_database import get_db_session

router = APIRouter(prefix="/api/workspaces", tags=["Chat Sessions"])
logger = logging.getLogger(__name__)


def _format_sse_event(event: str, data: dict) -> str:
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


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
            "doc_anchor_ids": [],
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


@router.get(
    "/{workspace_id}/chat/sessions",
    response_model=ListChatSessionsResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ChatErrorResponse, "description": "Invalid request"},
        403: {"model": ChatErrorResponse, "description": "Forbidden - no access to workspace"},
        404: {"model": ChatErrorResponse, "description": "Workspace not found"},
        500: {"model": ChatErrorResponse, "description": "Internal server error"},
    },
)
async def list_chat_sessions(
    workspace_id: int = Path(..., description="Workspace ID", gt=0),
    user_id: int = Query(..., description="User ID (dev mode)"),
    mode: str | None = Query(None, description="Chat mode filter"),
    limit: int = Query(10, description="Number of items per page"),
    cursor: str | None = Query(None, description="Cursor for pagination"),
    chat_service: ChatSessionService = Depends(get_chat_session_service),
):
    """
    List chat sessions for a workspace.

    **Authentication (Dev Mode):**
    - Requires `user_id` in query parameter

    **Filters:**
    - mode: ask|assist|agent
    """
    try:
        sessions, next_cursor = await chat_service.list_sessions(
            workspace_id=workspace_id,
            user_id=user_id,
            mode=mode,
            limit=limit,
            cursor=cursor,
        )

        items: list[ChatSessionListItem] = []
        for session in sessions:
            context_payload = session.context_json or {}
            anchor_ids = context_payload.get("anchor_ids") or []
            doc_anchor_ids = context_payload.get("doc_anchor_ids") or []
            context_summary = ChatContextSummary(
                doc_id=context_payload.get("doc_id"),
                note_id=context_payload.get("note_id"),
                anchor_count=len(anchor_ids) + len(doc_anchor_ids),
            )

            items.append(
                ChatSessionListItem(
                    session_id=session.session_id,
                    workspace_id=session.workspace_id,
                    title=session.title,
                    mode=session.mode,
                    created_at=session.created_at,
                    updated_at=session.updated_at,
                    last_message_at=session.last_message_at,
                    message_count=session.message_count,
                    context_summary=context_summary,
                )
            )

        return ListChatSessionsResponse(chat_session_items=items, next_cursor=next_cursor)

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Unexpected error in list_chat_sessions: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="INTERNAL_ERROR: An unexpected error occurred",
        )


@router.get(
    "/{workspace_id}/chat/sessions/{session_id}",
    response_model=GetChatSessionResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ChatErrorResponse, "description": "Invalid request"},
        403: {"model": ChatErrorResponse, "description": "Forbidden - no access to workspace"},
        404: {"model": ChatErrorResponse, "description": "Session not found"},
        500: {"model": ChatErrorResponse, "description": "Internal server error"},
    },
)
async def get_chat_session(
    workspace_id: int = Path(..., description="Workspace ID", gt=0),
    session_id: int = Path(..., description="Session ID", gt=0),
    user_id: int = Query(..., description="User ID (dev mode)"),
    limit: int = Query(3, description="Number of messages per page"),
    cursor: str | None = Query(None, description="Cursor for pagination"),
    order: str | None = Query(None, description="Order: asc or desc"),
    chat_service: ChatSessionService = Depends(get_chat_session_service),
):
    """
    Get chat session details with messages.

    **Authentication (Dev Mode):**
    - Requires `user_id` in query parameter
    """
    try:
        session_model, messages, next_cursor = await chat_service.get_session_messages(
            workspace_id=workspace_id,
            session_id=session_id,
            user_id=user_id,
            limit=limit,
            cursor=cursor,
            order=order,
        )

        context_payload = session_model.context_json or {
            "note_id": None,
            "anchor_ids": [],
            "doc_id": None,
            "doc_anchor_ids": [],
        }
        defaults_payload = session_model.defaults_json or {
            "model": "gpt-4.1-mini",
            "temperature": 0.2,
            "top_p": 1.0,
            "system_prompt": None,
            "retrieval": {"enabled": True, "top_k": 8, "rerank": False},
        }

        session_detail = ChatSessionDetail(
            id=session_model.session_id,
            workspace_id=session_model.workspace_id,
            title=session_model.title,
            mode=session_model.mode,
            context=ChatSessionContext(**context_payload),
            defaults=ChatDefaults(**defaults_payload),
            created_by=session_model.owner_user_id,
            created_at=session_model.created_at,
            updated_at=session_model.updated_at,
            last_message_at=session_model.last_message_at,
            message_count=session_model.message_count,
        )

        message_items: list[MessageItem] = []
        for message in messages:
            content = [MessageContentItem(type="text", text=message.content)]
            citations = message.citation or []
            message_items.append(
                MessageItem(
                    id=message.message_id,
                    role=message.role,
                    content=content,
                    citations=citations,
                    created_at=message.created_at,
                )
            )

        return GetChatSessionResponse(
            session=session_detail,
            messages=MessagePage(items=message_items, next_cursor=next_cursor),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Unexpected error in get_chat_session: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="INTERNAL_ERROR: An unexpected error occurred",
        )


@router.post(
    "/{workspace_id}/chat/sessions/{session_id}/message:ask",
    response_model=AskMessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ChatErrorResponse, "description": "Invalid request"},
        401: {"model": ChatErrorResponse, "description": "Unauthorized"},
        403: {"model": ChatErrorResponse, "description": "Forbidden - no access to workspace"},
        404: {"model": ChatErrorResponse, "description": "Session not found"},
        409: {"model": ChatErrorResponse, "description": "client_request_id already used"},
        500: {"model": ChatErrorResponse, "description": "Internal server error"},
    },
)
async def ask_message(
    request: AskMessageRequest,
    workspace_id: int = Path(..., description="Workspace ID", gt=0),
    session_id: int = Path(..., description="Session ID", gt=0),
    user_id: int = Query(..., description="User ID (dev mode)"),
    stream: bool = Query(True, description="Stream response via SSE"),
    chat_service: ChatSessionService = Depends(get_chat_session_service),
):
    """
    Send a message to a chat session in ask mode.

    **Authentication (Dev Mode):**
    - Requires `user_id` in query parameter
    """
    try:
        input_items = [item.model_dump() for item in request.input]
        context = request.context.model_dump() if request.context else None
        overrides = request.overrides.model_dump(exclude_none=True) if request.overrides else None

        user_message, assistant_message = await chat_service.send_ask_message(
            workspace_id=workspace_id,
            session_id=session_id,
            user_id=user_id,
            client_request_id=request.client_request_id,
            input_items=input_items,
            context=context,
            overrides=overrides,
        )

        user_message_item = MessageItem(
            id=user_message.message_id,
            role=user_message.role,
            content=[MessageContentItem(type="text", text=user_message.content)],
            citations=None,
            usage=None,
            created_at=user_message.created_at,
        )
        assistant_usage = (assistant_message.context or {}).get("usage")
        assistant_message_item = MessageItem(
            id=assistant_message.message_id,
            role=assistant_message.role,
            content=[MessageContentItem(type="text", text=assistant_message.content)],
            citations=assistant_message.citation or [],
            usage=assistant_usage,
            created_at=assistant_message.created_at,
        )

        if not stream:
            return AskMessageResponse(
                user_message=user_message_item,
                assistant_message=assistant_message_item,
            )

        async def event_stream():
            yield _format_sse_event(
                "message.created",
                {"user_message_id": user_message.message_id},
            )
            text = assistant_message.content or ""
            chunk_size = 50
            for start in range(0, len(text), chunk_size):
                yield _format_sse_event(
                    "assistant.delta",
                    {"text": text[start : start + chunk_size]},
                )
            yield _format_sse_event(
                "assistant.completed",
                {
                    "assistant_message_id": assistant_message.message_id,
                    "citations": assistant_message.citation or [],
                    "usage": assistant_usage or {},
                },
            )

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Unexpected error in ask_message: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="INTERNAL_ERROR: An unexpected error occurred",
        )
