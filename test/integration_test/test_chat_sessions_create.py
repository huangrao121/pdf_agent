"""Integration tests for chat session creation endpoint."""
import pytest
from contextlib import asynccontextmanager
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from pdf_ai_agent.api.routes.chat_sessions import router as chat_sessions_router
from pdf_ai_agent.config.database.models.model_user import UserModel, WorkspaceModel
from pdf_ai_agent.config.database.models.model_document import DocsModel, NoteModel, AnchorModel


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
async def test_doc(db_session, test_workspace, test_user):
    doc = DocsModel(
        workspace_id=test_workspace.workspace_id,
        owner_user_id=test_user.user_id,
        filename="test.pdf",
        storage_uri="file:///tmp/test.pdf",
        file_type="application/pdf",
        file_size=2345678,
        file_sha256="a" * 64,
        title="Test Document",
        status="ready",
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


@pytest.fixture
async def test_note(db_session, test_workspace, test_user):
    note = NoteModel(
        workspace_id=test_workspace.workspace_id,
        doc_id=None,
        owner_user_id=test_user.user_id,
        title="Test Note",
        markdown="Sample",
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)
    return note


@pytest.fixture
async def test_anchor(db_session, test_workspace, test_user, test_doc, test_note):
    anchor = AnchorModel(
        created_by_user_id=test_user.user_id,
        note_id=test_note.note_id,
        doc_id=test_doc.doc_id,
        chunk_id=None,
        workspace_id=test_workspace.workspace_id,
        page=1,
        quoted_text="quote",
        locator={"type": "pdf_quadpoints"},
        locator_hash="hash_anchor_int_1",
    )
    db_session.add(anchor)
    await db_session.commit()
    await db_session.refresh(anchor)
    return anchor


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


class TestChatSessionCreateAPI:
    @pytest.mark.asyncio
    async def test_create_chat_session_success(self, test_app, test_user, test_workspace, test_doc, test_note, test_anchor):
        transport = ASGITransport(app=test_app)
        payload = {
            "title": "New chat",
            "mode": "assist",
            "context": {
                "note_id": test_note.note_id,
                "anchor_ids": [test_anchor.anchor_id],
                "doc_id": test_doc.doc_id,
            },
            "defaults": {
                "model": "gpt-4.1-mini",
                "temperature": 0.2,
                "top_p": 1.0,
                "retrieval": {"enabled": True, "top_k": 8, "rerank": False},
            },
        }

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/workspaces/{test_workspace.workspace_id}/chat/sessions",
                params={"user_id": test_user.user_id},
                json=payload,
            )

        assert response.status_code == 201
        data = response.json()["session"]
        assert data["workspace_id"] == test_workspace.workspace_id
        assert data["mode"] == "assist"
        assert data["context"]["note_id"] == test_note.note_id
        assert data["context"]["anchor_ids"] == [test_anchor.anchor_id]
        assert data["defaults"]["model"] == "gpt-4.1-mini"

    @pytest.mark.asyncio
    async def test_create_chat_session_forbidden(self, test_app, db_session, test_user):
        other_user = UserModel(
            username="other",
            email="other@example.com",
            is_active=True,
        )
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        other_workspace = WorkspaceModel(
            name="Other Workspace",
            owner_user_id=other_user.user_id,
        )
        db_session.add(other_workspace)
        await db_session.commit()
        await db_session.refresh(other_workspace)

        transport = ASGITransport(app=test_app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/workspaces/{other_workspace.workspace_id}/chat/sessions",
                params={"user_id": test_user.user_id},
                json={"mode": "ask"},
            )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_chat_session_doc_not_found(self, test_app, test_user, test_workspace):
        transport = ASGITransport(app=test_app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/workspaces/{test_workspace.workspace_id}/chat/sessions",
                params={"user_id": test_user.user_id},
                json={"mode": "ask", "context": {"doc_id": 99999}},
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_chat_session_anchor_invalid(self, test_app, test_user, test_workspace):
        transport = ASGITransport(app=test_app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/workspaces/{test_workspace.workspace_id}/chat/sessions",
                params={"user_id": test_user.user_id},
                json={"mode": "ask", "context": {"anchor_ids": [99999]}},
            )

        assert response.status_code == 422
