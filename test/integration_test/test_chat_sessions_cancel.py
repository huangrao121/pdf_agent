"""Integration tests for cancel streaming endpoint."""
import pytest
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from pdf_ai_agent.api.routes.chat_sessions import router as chat_sessions_router
from pdf_ai_agent.config.database.models.model_user import UserModel, WorkspaceModel
from pdf_ai_agent.config.database.models.model_document import ChatSessionModel, MessageModel, MessageStatusEnum


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


@pytest.fixture
async def test_session(db_session, test_workspace, test_user):
    session = ChatSessionModel(
        workspace_id=test_workspace.workspace_id,
        owner_user_id=test_user.user_id,
        title="Test Session",
        mode="ask",
        status="streaming",
        active_generation_id="gen_123",
        context_json={"note_id": None, "anchor_ids": [], "doc_id": None, "doc_anchor_ids": []},
        defaults_json={
            "model": "gpt-4.1-mini",
            "temperature": 0.2,
            "top_p": 1.0,
            "system_prompt": None,
            "retrieval": {"enabled": True, "top_k": 8, "rerank": False},
        },
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


@pytest.fixture
async def test_message(db_session, test_session):
    message = MessageModel(
        session_id=test_session.session_id,
        workspace_id=test_session.workspace_id,
        sender_user_id=None,
        content="Streaming...",
        role="assistant",
        status=MessageStatusEnum.STREAMING.value,
        generation_id="gen_123",
        started_at=datetime.now(timezone.utc),
        context={},
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


class TestChatSessionCancelAPI:
    @pytest.mark.asyncio
    async def test_cancel_message_success(self, test_app, test_user, test_workspace, test_session, test_message):
        transport = ASGITransport(app=test_app)
        payload = {
            "client_request_id": "req_cancel_1",
            "reason": "stop",
        }

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/workspaces/{test_workspace.workspace_id}/chat/sessions/{test_session.session_id}/message:cancel",
                params={"user_id": test_user.user_id, "message_id": test_message.message_id},
                json=payload,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["message_id"] == test_message.message_id
        assert data["status"] == MessageStatusEnum.CANCELLED.value
        assert data["cancelled_at"] is not None
        assert data["generation_id"] == "gen_123"
        assert data["applied_patch"] is False
