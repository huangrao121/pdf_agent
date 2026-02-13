"""Unit tests for get chat session service."""
from datetime import datetime

import pytest
from fastapi import HTTPException

from pdf_ai_agent.api.services.chat_session_service import ChatSessionService
from pdf_ai_agent.config.database.models.model_user import UserModel, WorkspaceModel
from pdf_ai_agent.config.database.models.model_document import ChatSessionModel, MessageModel


@pytest.fixture
async def test_user(db_session):
    user = UserModel(
        username="testuser",
        email="test@example.com",
        full_name="Test User",
        is_active=True,
        email_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_workspace(db_session, test_user):
    workspace = WorkspaceModel(
        name="Test Workspace",
        owner_user_id=test_user.user_id,
    )
    db_session.add(workspace)
    await db_session.commit()
    await db_session.refresh(workspace)
    return workspace


async def create_session(db_session, workspace_id, user_id, updated_at):
    session = ChatSessionModel(
        workspace_id=workspace_id,
        owner_user_id=user_id,
        title="Session",
        mode="ask",
        context_json={"note_id": None, "anchor_ids": [], "doc_id": None, "doc_anchor_ids": []},
        defaults_json={"model": "gpt-4.1-mini", "temperature": 0.2, "top_p": 1.0, "retrieval": {"enabled": True, "top_k": 8, "rerank": False}},
        message_count=2,
        last_message_at=updated_at,
        created_at=updated_at,
        updated_at=updated_at,
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


async def create_message(db_session, session_id, workspace_id, user_id, role, content, created_at):
    message = MessageModel(
        session_id=session_id,
        workspace_id=workspace_id,
        sender_user_id=user_id,
        content=content,
        role=role,
        citation=[{"anchor_id": 1}],
        context=None,
        created_at=created_at,
    )
    db_session.add(message)
    await db_session.commit()
    await db_session.refresh(message)
    return message


class TestChatSessionGetService:
    @pytest.mark.asyncio
    async def test_get_session_invalid_order(self, db_session, test_user, test_workspace):
        service = ChatSessionService(db_session=db_session)
        session = await create_session(db_session, test_workspace.workspace_id, test_user.user_id, datetime(2026, 2, 1, 10, 0, 0))

        with pytest.raises(HTTPException) as exc_info:
            await service.get_session_messages(
                workspace_id=test_workspace.workspace_id,
                session_id=session.session_id,
                user_id=test_user.user_id,
                limit=3,
                cursor=None,
                order="invalid",
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_get_session_invalid_limit(self, db_session, test_user, test_workspace):
        service = ChatSessionService(db_session=db_session)
        session = await create_session(db_session, test_workspace.workspace_id, test_user.user_id, datetime(2026, 2, 1, 10, 0, 0))

        with pytest.raises(HTTPException) as exc_info:
            await service.get_session_messages(
                workspace_id=test_workspace.workspace_id,
                session_id=session.session_id,
                user_id=test_user.user_id,
                limit=11,
                cursor=None,
                order="desc",
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_get_session_invalid_cursor(self, db_session, test_user, test_workspace):
        service = ChatSessionService(db_session=db_session)
        session = await create_session(db_session, test_workspace.workspace_id, test_user.user_id, datetime(2026, 2, 1, 10, 0, 0))

        with pytest.raises(HTTPException) as exc_info:
            await service.get_session_messages(
                workspace_id=test_workspace.workspace_id,
                session_id=session.session_id,
                user_id=test_user.user_id,
                limit=3,
                cursor="invalid",
                order="desc",
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_get_session_pagination_desc(self, db_session, test_user, test_workspace):
        service = ChatSessionService(db_session=db_session)
        session = await create_session(db_session, test_workspace.workspace_id, test_user.user_id, datetime(2026, 2, 3, 10, 0, 0))

        m1 = await create_message(
            db_session,
            session.session_id,
            test_workspace.workspace_id,
            test_user.user_id,
            "user",
            "first",
            datetime(2026, 2, 1, 10, 0, 0),
        )
        m2 = await create_message(
            db_session,
            session.session_id,
            test_workspace.workspace_id,
            test_user.user_id,
            "assistant",
            "second",
            datetime(2026, 2, 2, 10, 0, 0),
        )

        _, messages, next_cursor = await service.get_session_messages(
            workspace_id=test_workspace.workspace_id,
            session_id=session.session_id,
            user_id=test_user.user_id,
            limit=1,
            cursor=None,
            order="desc",
        )

        assert [m.message_id for m in messages] == [m2.message_id]
        assert next_cursor is not None

        _, messages_page2, next_cursor2 = await service.get_session_messages(
            workspace_id=test_workspace.workspace_id,
            session_id=session.session_id,
            user_id=test_user.user_id,
            limit=1,
            cursor=next_cursor,
            order="desc",
        )

        assert [m.message_id for m in messages_page2] == [m1.message_id]
        assert next_cursor2 is None
