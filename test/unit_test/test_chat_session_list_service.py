"""Unit tests for chat session list service."""
from datetime import datetime

import pytest
from fastapi import HTTPException

from pdf_ai_agent.api.services.chat_session_service import ChatSessionService
from pdf_ai_agent.config.database.models.model_user import UserModel, WorkspaceModel
from pdf_ai_agent.config.database.models.model_document import ChatSessionModel


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
async def other_user(db_session):
    user = UserModel(
        username="otheruser",
        email="other@example.com",
        full_name="Other User",
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


async def create_session(db_session, workspace_id, user_id, title, mode, updated_at):
    session = ChatSessionModel(
        workspace_id=workspace_id,
        owner_user_id=user_id,
        title=title,
        mode=mode,
        context_json={"note_id": None, "anchor_ids": [], "doc_id": None, "doc_anchor_ids": []},
        defaults_json={"model": "gpt-4.1-mini", "temperature": 0.2, "top_p": 1.0, "retrieval": {"enabled": True, "top_k": 8, "rerank": False}},
        message_count=0,
        created_at=updated_at,
        updated_at=updated_at,
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


class TestChatSessionListService:
    @pytest.mark.asyncio
    async def test_list_sessions_invalid_mode(self, db_session, test_user, test_workspace):
        service = ChatSessionService(db_session=db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.list_sessions(
                workspace_id=test_workspace.workspace_id,
                user_id=test_user.user_id,
                mode="invalid",
                limit=10,
                cursor=None,
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_list_sessions_invalid_limit(self, db_session, test_user, test_workspace):
        service = ChatSessionService(db_session=db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.list_sessions(
                workspace_id=test_workspace.workspace_id,
                user_id=test_user.user_id,
                mode=None,
                limit=0,
                cursor=None,
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_list_sessions_invalid_cursor(self, db_session, test_user, test_workspace):
        service = ChatSessionService(db_session=db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.list_sessions(
                workspace_id=test_workspace.workspace_id,
                user_id=test_user.user_id,
                mode=None,
                limit=10,
                cursor="not-a-cursor",
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_list_sessions_pagination(self, db_session, test_user, test_workspace):
        service = ChatSessionService(db_session=db_session)

        session_a = await create_session(
            db_session,
            test_workspace.workspace_id,
            test_user.user_id,
            "Session A",
            "ask",
            datetime(2026, 2, 1, 10, 0, 0),
        )
        session_b = await create_session(
            db_session,
            test_workspace.workspace_id,
            test_user.user_id,
            "Session B",
            "ask",
            datetime(2026, 2, 2, 10, 0, 0),
        )
        session_c = await create_session(
            db_session,
            test_workspace.workspace_id,
            test_user.user_id,
            "Session C",
            "assist",
            datetime(2026, 2, 3, 10, 0, 0),
        )

        sessions, next_cursor = await service.list_sessions(
            workspace_id=test_workspace.workspace_id,
            user_id=test_user.user_id,
            mode=None,
            limit=2,
            cursor=None,
        )

        assert [s.session_id for s in sessions] == [session_c.session_id, session_b.session_id]
        assert next_cursor is not None

        sessions_page2, next_cursor2 = await service.list_sessions(
            workspace_id=test_workspace.workspace_id,
            user_id=test_user.user_id,
            mode=None,
            limit=2,
            cursor=next_cursor,
        )

        assert [s.session_id for s in sessions_page2] == [session_a.session_id]
        assert next_cursor2 is None
