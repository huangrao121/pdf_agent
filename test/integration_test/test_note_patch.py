"""
Integration tests for patch note endpoint.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from fastapi import FastAPI
from dotenv import load_dotenv
from pdf_ai_agent.config.database.models.model_user import UserModel, WorkspaceModel
from pdf_ai_agent.config.database.models.model_document import NoteModel


@pytest.fixture
async def test_user(db_session):
    """Create a test user."""
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
    """Create another user."""
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
    """Create a test workspace."""
    workspace = WorkspaceModel(
        name="Test Workspace",
        owner_user_id=test_user.user_id,
    )
    db_session.add(workspace)
    await db_session.commit()
    await db_session.refresh(workspace)
    return workspace


@pytest.fixture
async def other_workspace(db_session, test_user):
    """Create another workspace owned by test_user."""
    workspace = WorkspaceModel(
        name="Other Workspace",
        owner_user_id=test_user.user_id,
    )
    db_session.add(workspace)
    await db_session.commit()
    await db_session.refresh(workspace)
    return workspace


@pytest.fixture
async def test_note(db_session, test_user, test_workspace):
    """Create a test note."""
    note = NoteModel(
        workspace_id=test_workspace.workspace_id,
        doc_id=None,
        owner_user_id=test_user.user_id,
        title="Original Title",
        markdown="Original content",
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)
    return note


@pytest.fixture
async def test_app(db_session):
    """Create test app with overridden dependencies."""
    from pdf_ai_agent.api.routes.notes import router as notes_router
    from pdf_ai_agent.config.database.init_database import get_db_session
    load_dotenv()

    app = FastAPI(title="PDF_Agent_integration_test")
    app.include_router(notes_router)

    async def override_get_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db_session

    return app


@pytest.mark.asyncio
async def test_patch_note_title_only(test_app, db_session, test_user, test_workspace, test_note):
    """Test patching title only updates title and preserves markdown."""
    transport = ASGITransport(app=test_app)
    original_version = test_note.version

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/api/workspaces/{test_workspace.workspace_id}/notes/{test_note.note_id}",
            params={"user_id": test_user.user_id},
            json={"title": "  New Title  "},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["note_id"] == test_note.note_id
        assert data["version"] == original_version + 1
        assert "update_at" in data

        note_query = select(NoteModel).where(NoteModel.note_id == test_note.note_id)
        result = await db_session.execute(note_query)
        note = result.scalar_one()

        assert note.title == "New Title"
        assert note.markdown == "Original content"


@pytest.mark.asyncio
async def test_patch_note_content_only(test_app, db_session, test_user, test_workspace, test_note):
    """Test patching content only updates markdown and preserves title."""
    transport = ASGITransport(app=test_app)
    original_title = test_note.title
    original_version = test_note.version

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/api/workspaces/{test_workspace.workspace_id}/notes/{test_note.note_id}",
            params={"user_id": test_user.user_id},
            json={"content_markdown": "  Updated content  "},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == original_version + 1

        note_query = select(NoteModel).where(NoteModel.note_id == test_note.note_id)
        result = await db_session.execute(note_query)
        note = result.scalar_one()

        assert note.title == original_title
        assert note.markdown == "Updated content"


@pytest.mark.asyncio
async def test_patch_note_both_fields(test_app, db_session, test_user, test_workspace, test_note):
    """Test patching both title and markdown."""
    transport = ASGITransport(app=test_app)
    original_version = test_note.version

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/api/workspaces/{test_workspace.workspace_id}/notes/{test_note.note_id}",
            params={"user_id": test_user.user_id},
            json={
                "title": "Updated Title",
                "content_markdown": "Updated markdown",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == original_version + 1

        note_query = select(NoteModel).where(NoteModel.note_id == test_note.note_id)
        result = await db_session.execute(note_query)
        note = result.scalar_one()

        assert note.title == "Updated Title"
        assert note.markdown == "Updated markdown"


@pytest.mark.asyncio
async def test_patch_note_empty_body(test_app, test_user, test_workspace, test_note):
    """Test patching with empty body returns 400."""
    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/api/workspaces/{test_workspace.workspace_id}/notes/{test_note.note_id}",
            params={"user_id": test_user.user_id},
            json={},
        )

        assert response.status_code == 400


@pytest.mark.asyncio
async def test_patch_note_non_member(test_app, other_user, test_workspace, test_note):
    """Test patching note without membership returns 403."""
    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/api/workspaces/{test_workspace.workspace_id}/notes/{test_note.note_id}",
            params={"user_id": other_user.user_id},
            json={"title": "New Title"},
        )

        assert response.status_code == 403


@pytest.mark.asyncio
async def test_patch_note_cross_workspace_not_found(
    test_app, test_user, test_workspace, other_workspace, test_note
):
    """Test patching note with wrong workspace returns 404."""
    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/api/workspaces/{other_workspace.workspace_id}/notes/{test_note.note_id}",
            params={"user_id": test_user.user_id},
            json={"title": "New Title"},
        )

        assert response.status_code == 404
