"""Integration tests for chat session list endpoint."""
from contextlib import asynccontextmanager
from datetime import datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from pdf_ai_agent.api.routes.chat_sessions import router as chat_sessions_router
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


class TestChatSessionListAPI:
    @pytest.mark.asyncio
    async def test_list_sessions_forbidden(self, test_app, test_user, other_workspace):
        transport = ASGITransport(app=test_app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/workspaces/{other_workspace.workspace_id}/chat/sessions",
                params={"user_id": test_user.user_id},
            )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list_sessions_only_returns_own(self, test_app, db_session, test_user, other_user, test_workspace):
        await create_session(
            db_session,
            test_workspace.workspace_id,
            test_user.user_id,
            "Mine",
            "ask",
            datetime(2026, 2, 2, 10, 0, 0),
        )
        await create_session(
            db_session,
            test_workspace.workspace_id,
            other_user.user_id,
            "Theirs",
            "assist",
            datetime(2026, 2, 3, 10, 0, 0),
        )

        transport = ASGITransport(app=test_app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/chat/sessions",
                params={"user_id": test_user.user_id},
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["chat_session_items"]) == 1
        assert data["chat_session_items"][0]["title"] == "Mine"

    @pytest.mark.asyncio
    async def test_list_sessions_mode_filter_and_cursor(self, test_app, db_session, test_user, test_workspace):
        s1 = await create_session(
            db_session,
            test_workspace.workspace_id,
            test_user.user_id,
            "Ask A",
            "ask",
            datetime(2026, 2, 1, 10, 0, 0),
        )
        s2 = await create_session(
            db_session,
            test_workspace.workspace_id,
            test_user.user_id,
            "Ask B",
            "ask",
            datetime(2026, 2, 2, 10, 0, 0),
        )
        await create_session(
            db_session,
            test_workspace.workspace_id,
            test_user.user_id,
            "Assist",
            "assist",
            datetime(2026, 2, 3, 10, 0, 0),
        )

        transport = ASGITransport(app=test_app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/chat/sessions",
                params={"user_id": test_user.user_id, "mode": "ask", "limit": 1},
            )

            assert response.status_code == 200
            payload = response.json()
            assert len(payload["chat_session_items"]) == 1
            assert payload["chat_session_items"][0]["session_id"] == s2.session_id
            assert "update_at" in payload["chat_session_items"][0]
            next_cursor = payload["next_cursor"]

            response_page2 = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/chat/sessions",
                params={"user_id": test_user.user_id, "mode": "ask", "limit": 1, "cursor": next_cursor},
            )

            assert response_page2.status_code == 200
            payload_page2 = response_page2.json()
            assert len(payload_page2["chat_session_items"]) == 1
            assert payload_page2["chat_session_items"][0]["session_id"] == s1.session_id
            assert payload_page2["next_cursor"] is None
