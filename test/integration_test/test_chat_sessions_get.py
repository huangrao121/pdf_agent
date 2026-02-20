"""Integration tests for get chat session endpoint."""
from contextlib import asynccontextmanager
from datetime import datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from pdf_ai_agent.api.routes.chat_sessions import router as chat_sessions_router
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


@pytest.fixture
async def other_workspace(db_session, other_user):
    workspace = WorkspaceModel(
        name="Other Workspace",
        owner_user_id=other_user.user_id,
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
        mode="assist",
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


async def create_message(db_session, session_id, workspace_id, user_id, role, content, created_at, citation=None):
    message = MessageModel(
        session_id=session_id,
        workspace_id=workspace_id,
        sender_user_id=user_id,
        content=content,
        role=role,
        citation=citation,
        context=None,
        created_at=created_at,
    )
    db_session.add(message)
    await db_session.commit()
    await db_session.refresh(message)
    return message


@pytest.fixture
async def test_app(db_session):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from pdf_ai_agent.config.database.init_database import get_database_config, init_database, close_engine

        config = get_database_config()
        await init_database(config)
        yield
        await close_engine()

    app = FastAPI(title="PDF_Agent", lifespan=lifespan)
    app.include_router(chat_sessions_router)

    from pdf_ai_agent.config.database.init_database import get_db_session

    async def override_get_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    return app


class TestChatSessionGetAPI:
    @pytest.mark.asyncio
    async def test_get_session_forbidden(self, test_app, db_session, test_user, other_workspace):
        session = await create_session(
            db_session,
            other_workspace.workspace_id,
            other_workspace.owner_user_id,
            datetime(2026, 2, 1, 10, 0, 0),
        )
        transport = ASGITransport(app=test_app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/workspaces/{other_workspace.workspace_id}/chat/sessions/{session.session_id}",
                params={"user_id": test_user.user_id},
            )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_session_with_messages_and_citations(self, test_app, db_session, test_user, test_workspace):
        session = await create_session(db_session, test_workspace.workspace_id, test_user.user_id, datetime(2026, 2, 3, 10, 0, 0))
        citation = [{"anchor_id": 123, "doc_id": 456, "page": 12}]
        m1 = await create_message(
            db_session,
            session.session_id,
            test_workspace.workspace_id,
            test_user.user_id,
            "user",
            "first",
            datetime(2026, 2, 1, 10, 0, 0),
            citation=None,
        )
        m2 = await create_message(
            db_session,
            session.session_id,
            test_workspace.workspace_id,
            test_user.user_id,
            "assistant",
            "second",
            datetime(2026, 2, 2, 10, 0, 0),
            citation=citation,
        )

        transport = ASGITransport(app=test_app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/chat/sessions/{session.session_id}",
                params={"user_id": test_user.user_id, "order": "desc", "limit": 1},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["session"]["id"] == session.session_id
        assert payload["session"]["message_count"] == 2
        assert payload["messages"]["items"][0]["id"] == m2.message_id
        assert payload["messages"]["items"][0]["citations"] == citation

        next_cursor = payload["messages"]["next_cursor"]
        assert next_cursor is not None

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response_page2 = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/chat/sessions/{session.session_id}",
                params={"user_id": test_user.user_id, "order": "desc", "limit": 1, "cursor": next_cursor},
            )

        assert response_page2.status_code == 200
        payload_page2 = response_page2.json()
        assert payload_page2["messages"]["items"][0]["id"] == m1.message_id
        assert payload_page2["messages"]["next_cursor"] is None
