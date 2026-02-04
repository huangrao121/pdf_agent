"""
Integration tests for note list endpoint.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from datetime import datetime

from pdf_ai_agent.config.database.models.model_user import UserModel, WorkspaceModel
from pdf_ai_agent.config.database.models.model_document import DocsModel, NoteModel


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
async def test_doc(db_session, test_user, test_workspace):
    """Create a test document."""
    doc = DocsModel(
        workspace_id=test_workspace.workspace_id,
        owner_user_id=test_user.user_id,
        filename="test.pdf",
        storage_uri="file:///tmp/test.pdf",
        file_type="application/pdf",
        file_size=1024,
        file_sha256="a" * 64,
        title="Test Document",
        status="ready",
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


@pytest.fixture
async def test_app(db_session):
    """Create test app with overridden dependencies."""
    from main import create_app
    
    app = create_app()
    
    # Override db session dependency
    from pdf_ai_agent.config.database.init_database import get_db_session
    
    async def override_get_db_session():
        yield db_session
    
    app.dependency_overrides[get_db_session] = override_get_db_session
    
    return app


@pytest.mark.asyncio
async def test_list_notes_with_cursor(test_app, db_session, test_user, test_workspace):
    """Test listing notes with cursor-based pagination."""
    from datetime import datetime, timedelta
    
    # Create multiple notes with manually set timestamps
    base_time = datetime.now()
    notes = []
    for i in range(5):
        note = NoteModel(
            workspace_id=test_workspace.workspace_id,
            owner_user_id=test_user.user_id,
            title=f"Note {i}",
            markdown=f"# Note {i}\n\nContent {i}",
            created_at=base_time - timedelta(seconds=i),  # Manually set to ensure ordering
            updated_at=base_time - timedelta(seconds=i),
        )
        db_session.add(note)
        notes.append(note)
    
    await db_session.commit()
    for note in notes:
        await db_session.refresh(note)
    
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Get first page (limit 2)
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/notes",
            params={"user_id": test_user.user_id, "limit": 2}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["notes"]) == 2
        assert data["next_cursor"] is not None
        
        # Get second page
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/notes",
            params={
                "user_id": test_user.user_id,
                "limit": 2,
                "cursor": data["next_cursor"]
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["notes"]) == 2
        assert data["next_cursor"] is not None
        
        # Get third page
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/notes",
            params={
                "user_id": test_user.user_id,
                "limit": 2,
                "cursor": data["next_cursor"]
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["notes"]) == 1
        assert data["next_cursor"] is None  # No more pages


@pytest.mark.asyncio
async def test_list_notes_doc_scoped(test_app, db_session, test_user, test_workspace, test_doc):
    """Test listing notes filtered by doc_id."""
    # Create workspace-level note
    workspace_note = NoteModel(
        workspace_id=test_workspace.workspace_id,
        owner_user_id=test_user.user_id,
        title="Workspace Note",
        markdown="# Workspace Note",
        doc_id=None,
    )
    db_session.add(workspace_note)
    
    # Create doc-scoped note
    doc_note = NoteModel(
        workspace_id=test_workspace.workspace_id,
        owner_user_id=test_user.user_id,
        title="Doc Note",
        markdown="# Doc Note",
        doc_id=test_doc.doc_id,
    )
    db_session.add(doc_note)
    
    await db_session.commit()
    
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # List all notes (no filter)
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/notes",
            params={"user_id": test_user.user_id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["notes"]) == 2
        
        # List doc-scoped notes only
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/notes",
            params={"user_id": test_user.user_id, "doc_id": test_doc.doc_id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["notes"]) == 1
        assert data["notes"][0]["doc_id"] == test_doc.doc_id
        assert data["notes"][0]["title"] == "Doc Note"


@pytest.mark.asyncio
async def test_non_member_access(test_app, db_session, test_workspace):
    """Test that non-member cannot list notes."""
    # Create another user who is not a member
    other_user = UserModel(
        username="otheruser",
        email="other@example.com",
        full_name="Other User",
        is_active=True,
        email_verified=True,
    )
    db_session.add(other_user)
    await db_session.commit()
    await db_session.refresh(other_user)
    
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/notes",
            params={"user_id": other_user.user_id}
        )
        
        assert response.status_code == 403
        data = response.json()
        assert "FORBIDDEN_WORKSPACE" in data["detail"]


@pytest.mark.asyncio
async def test_invalid_doc_id(test_app, db_session, test_user, test_workspace):
    """Test listing notes with non-existent doc_id."""
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/notes",
            params={"user_id": test_user.user_id, "doc_id": 99999}
        )
        
        assert response.status_code == 404
        data = response.json()
        assert "DOC_NOT_FOUND" in data["detail"]


@pytest.mark.asyncio
async def test_doc_workspace_mismatch(test_app, db_session, test_user, test_workspace, test_doc):
    """Test listing notes when doc doesn't belong to workspace."""
    # Create another workspace
    other_workspace = WorkspaceModel(
        name="Other Workspace",
        owner_user_id=test_user.user_id,
    )
    db_session.add(other_workspace)
    await db_session.commit()
    await db_session.refresh(other_workspace)
    
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/workspaces/{other_workspace.workspace_id}/notes",
            params={"user_id": test_user.user_id, "doc_id": test_doc.doc_id}
        )
        
        assert response.status_code == 409
        data = response.json()
        assert "DOC_WORKSPACE_MISMATCH" in data["detail"]


@pytest.mark.asyncio
async def test_pagination_stable_across_inserts(test_app, db_session, test_user, test_workspace):
    """Test that pagination remains stable when new notes are inserted."""
    from datetime import datetime, timedelta
    
    # Create initial notes with manually set timestamps
    base_time = datetime.now()
    for i in range(3):
        note = NoteModel(
            workspace_id=test_workspace.workspace_id,
            owner_user_id=test_user.user_id,
            title=f"Note {i}",
            markdown=f"Content {i}",
            created_at=base_time - timedelta(seconds=i),
            updated_at=base_time - timedelta(seconds=i),
        )
        db_session.add(note)
    
    await db_session.commit()
    
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Get first page
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/notes",
            params={"user_id": test_user.user_id, "limit": 2}
        )
        
        assert response.status_code == 200
        data = response.json()
        first_page_ids = [note["note_id"] for note in data["notes"]]
        next_cursor = data["next_cursor"]
        
        # Insert a new note (should not affect cursor-based pagination)
        new_note = NoteModel(
            workspace_id=test_workspace.workspace_id,
            owner_user_id=test_user.user_id,
            title="New Note",
            markdown="New content",
        )
        db_session.add(new_note)
        await db_session.commit()
        
        # Get second page using cursor
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/notes",
            params={
                "user_id": test_user.user_id,
                "limit": 2,
                "cursor": next_cursor
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        second_page_ids = [note["note_id"] for note in data["notes"]]
        
        # Verify no overlap between pages
        assert set(first_page_ids).isdisjoint(set(second_page_ids))
        
        # Verify second page has the remaining original note
        assert len(second_page_ids) == 1


@pytest.mark.asyncio
async def test_response_excludes_markdown_content(test_app, db_session, test_user, test_workspace):
    """Test that response doesn't include markdown content."""
    note = NoteModel(
        workspace_id=test_workspace.workspace_id,
        owner_user_id=test_user.user_id,
        title="Test Note",
        markdown="# Test\n\nThis is secret content that should not be returned",
    )
    db_session.add(note)
    await db_session.commit()
    
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/notes",
            params={"user_id": test_user.user_id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["notes"]) == 1
        
        note_data = data["notes"][0]
        # Verify expected fields are present
        assert "note_id" in note_data
        assert "title" in note_data
        assert "workspace_id" in note_data
        assert "doc_id" in note_data
        assert "version" in note_data
        assert "owner_user_id" in note_data
        assert "created_at" in note_data
        assert "updated_at" in note_data
        
        # Verify markdown content is NOT present
        assert "markdown" not in note_data
        assert "content" not in note_data
        assert "content_markdown" not in note_data


@pytest.mark.asyncio
async def test_invalid_cursor(test_app, db_session, test_user, test_workspace):
    """Test that invalid cursor returns 400."""
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/notes",
            params={"user_id": test_user.user_id, "cursor": "invalid_cursor_!@#$"}
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "INVALID_CURSOR" in data["detail"]


@pytest.mark.asyncio
async def test_limit_validation(test_app, db_session, test_user, test_workspace):
    """Test that limit is validated by FastAPI."""
    # Create a note
    note = NoteModel(
        workspace_id=test_workspace.workspace_id,
        owner_user_id=test_user.user_id,
        title="Test Note",
        markdown="Content",
    )
    db_session.add(note)
    await db_session.commit()
    
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test limit=0 (should fail validation)
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/notes",
            params={"user_id": test_user.user_id, "limit": 0}
        )
        assert response.status_code == 422  # Validation error
        
        # Test limit=101 (should fail validation)
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/notes",
            params={"user_id": test_user.user_id, "limit": 101}
        )
        assert response.status_code == 422  # Validation error
        
        # Test limit=1 (should succeed)
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/notes",
            params={"user_id": test_user.user_id, "limit": 1}
        )
        assert response.status_code == 200
        
        # Test limit=100 (should succeed)
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/notes",
            params={"user_id": test_user.user_id, "limit": 100}
        )
        assert response.status_code == 200
