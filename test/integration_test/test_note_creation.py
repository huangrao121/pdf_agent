"""
Integration tests for note creation endpoint.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

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
async def test_create_workspace_level_note(test_app, db_session, test_user, test_workspace):
    """Test creating a workspace-level note."""
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/workspaces/{test_workspace.workspace_id}/notes",
            params={"user_id": test_user.user_id},
            json={
                "content_markdown": "# My Note\n\nThis is workspace-level note content."
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert "note_id" in data
        
        # Verify in database
        note_query = select(NoteModel).where(NoteModel.note_id == data["note_id"])
        result = await db_session.execute(note_query)
        note = result.scalar_one()
        
        assert note.workspace_id == test_workspace.workspace_id
        assert note.doc_id is None
        assert note.title == "My Note"


@pytest.mark.asyncio
async def test_create_doc_scoped_note(test_app, db_session, test_user, test_workspace, test_doc):
    """Test creating a doc-scoped note."""
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/workspaces/{test_workspace.workspace_id}/notes",
            params={"user_id": test_user.user_id},
            json={
                "doc_id": test_doc.doc_id,
                "title": "My Doc Note",
                "content_markdown": "This is doc-scoped note content."
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert "note_id" in data
        
        # Verify in database
        note_query = select(NoteModel).where(NoteModel.note_id == data["note_id"])
        result = await db_session.execute(note_query)
        note = result.scalar_one()
        
        assert note.workspace_id == test_workspace.workspace_id
        assert note.doc_id == test_doc.doc_id
        assert note.title == "My Doc Note"


@pytest.mark.asyncio
async def test_non_member_access(test_app, db_session, test_workspace):
    """Test that non-member cannot create note."""
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
        response = await client.post(
            f"/api/workspaces/{test_workspace.workspace_id}/notes",
            params={"user_id": other_user.user_id},
            json={
                "content_markdown": "Test content"
            }
        )
        
        assert response.status_code == 403
        data = response.json()
        assert data["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_invalid_doc_id(test_app, db_session, test_user, test_workspace):
    """Test creating note with non-existent doc_id."""
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/workspaces/{test_workspace.workspace_id}/notes",
            params={"user_id": test_user.user_id},
            json={
                "doc_id": 99999,
                "content_markdown": "Test content"
            }
        )
        
        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "DOC_NOT_FOUND"


@pytest.mark.asyncio
async def test_doc_workspace_mismatch(test_app, db_session, test_user, test_workspace, test_doc):
    """Test creating note when doc doesn't belong to workspace."""
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
        response = await client.post(
            f"/api/workspaces/{other_workspace.workspace_id}/notes",
            params={"user_id": test_user.user_id},
            json={
                "doc_id": test_doc.doc_id,  # Doc belongs to test_workspace
                "content_markdown": "Test content"
            }
        )
        
        assert response.status_code == 409
        data = response.json()
        assert data["error"]["code"] == "DOC_WORKSPACE_MISMATCH"


@pytest.mark.asyncio
async def test_blank_markdown(test_app, db_session, test_user, test_workspace):
    """Test rejection of blank markdown content."""
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/workspaces/{test_workspace.workspace_id}/notes",
            params={"user_id": test_user.user_id},
            json={
                "content_markdown": "   \n  \n  "
            }
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == "INVALID_ARGUMENT"


@pytest.mark.asyncio
async def test_title_auto_generated_persisted(test_app, db_session, test_user, test_workspace):
    """Test that auto-generated title is persisted in DB."""
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/workspaces/{test_workspace.workspace_id}/notes",
            params={"user_id": test_user.user_id},
            json={
                "content_markdown": "# Auto Generated Title\n\nNote content here."
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        
        # Verify in database
        note_query = select(NoteModel).where(NoteModel.note_id == data["note_id"])
        result = await db_session.execute(note_query)
        note = result.scalar_one()
        
        assert note.title == "Auto Generated Title"
        assert note.markdown == "# Auto Generated Title\n\nNote content here."
