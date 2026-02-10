"""
Integration tests for document upload endpoint.
"""
import io
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from pdf_ai_agent.config.database.models.model_user import UserModel, WorkspaceModel
from pdf_ai_agent.config.database.models.model_document import DocsModel


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


def create_pdf_file(content: bytes = b"Test PDF content") -> io.BytesIO:
    """Create a mock PDF file."""
    # Valid PDF starts with %PDF-
    pdf_content = b"%PDF-1.4\n" + content
    return io.BytesIO(pdf_content)


@pytest.mark.asyncio
async def test_upload_pdf_success(test_app, db_session, test_user, test_workspace):
    """Test successful PDF upload."""
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create PDF file
        pdf_file = create_pdf_file()
        
        # Upload
        response = await client.post(
            f"/api/workspaces/{test_workspace.workspace_id}/docs",
            files={"file": ("test.pdf", pdf_file, "application/pdf")},
            data={
                "user_id": str(test_user.user_id),
                "title": "Test Document",
                "description": "Test description"
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        
        assert "doc_id" in data
        assert data["filename"] == "test.pdf"
        assert data["status"] == "UPLOADED"
        
        # Verify document in database
        query = select(DocsModel).where(DocsModel.doc_id == data["doc_id"])
        result = await db_session.execute(query)
        doc = result.scalar_one_or_none()
        
        assert doc is not None
        assert doc.filename == "test.pdf"
        assert doc.workspace_id == test_workspace.workspace_id
        assert doc.owner_user_id == test_user.user_id
        assert doc.status.value == "uploaded"  # Compare enum value
        assert doc.file_sha256 is not None
        assert len(doc.file_sha256) == 64


@pytest.mark.asyncio
async def test_upload_pdf_duplicate(test_app, db_session, test_user, test_workspace):
    """Test duplicate PDF upload returns existing document."""
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create PDF file with specific content
        pdf_content = b"Unique content for dedup test"
        pdf_file1 = create_pdf_file(pdf_content)
        
        # First upload
        response1 = await client.post(
            f"/api/workspaces/{test_workspace.workspace_id}/docs",
            files={"file": ("test1.pdf", pdf_file1, "application/pdf")},
            data={"user_id": str(test_user.user_id)}
        )
        
        assert response1.status_code == 201
        doc_id1 = response1.json()["doc_id"]
        
        # Second upload with same content
        pdf_file2 = create_pdf_file(pdf_content)
        response2 = await client.post(
            f"/api/workspaces/{test_workspace.workspace_id}/docs",
            files={"file": ("test2.pdf", pdf_file2, "application/pdf")},
            data={"user_id": str(test_user.user_id)}
        )
        
        # Should return existing document
        assert response2.status_code in [200, 201]
        doc_id2 = response2.json()["doc_id"]
        
        # Should be same document
        assert doc_id1 == doc_id2


@pytest.mark.asyncio
async def test_upload_pdf_different_workspaces(test_app, db_session, test_user):
    """Test same file in different workspaces creates separate documents."""
    # Create two workspaces
    workspace1 = WorkspaceModel(
        name="Workspace 1",
        owner_user_id=test_user.user_id,
    )
    workspace2 = WorkspaceModel(
        name="Workspace 2",
        owner_user_id=test_user.user_id,
    )
    db_session.add_all([workspace1, workspace2])
    await db_session.commit()
    await db_session.refresh(workspace1)
    await db_session.refresh(workspace2)
    
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Same content
        pdf_content = b"Shared content"
        
        # Upload to workspace 1
        pdf_file1 = create_pdf_file(pdf_content)
        response1 = await client.post(
            f"/api/workspaces/{workspace1.workspace_id}/docs",
            files={"file": ("test.pdf", pdf_file1, "application/pdf")},
            data={"user_id": str(test_user.user_id)}
        )
        
        assert response1.status_code == 201
        doc_id1 = response1.json()["doc_id"]
        
        # Upload to workspace 2
        pdf_file2 = create_pdf_file(pdf_content)
        response2 = await client.post(
            f"/api/workspaces/{workspace2.workspace_id}/docs",
            files={"file": ("test.pdf", pdf_file2, "application/pdf")},
            data={"user_id": str(test_user.user_id)}
        )
        
        assert response2.status_code == 201
        doc_id2 = response2.json()["doc_id"]
        
        # Should be different documents
        assert doc_id1 != doc_id2


@pytest.mark.asyncio
async def test_upload_invalid_pdf(test_app, db_session, test_user, test_workspace):
    """Test upload of invalid PDF file."""
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Invalid file (not a PDF)
        invalid_file = io.BytesIO(b"Not a PDF file")
        
        response = await client.post(
            f"/api/workspaces/{test_workspace.workspace_id}/docs",
            files={"file": ("test.txt", invalid_file, "text/plain")},
            data={"user_id": str(test_user.user_id)}
        )
        
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_no_workspace_access(test_app, db_session, test_user):
    """Test upload without workspace access."""
    # Create another user
    other_user = UserModel(
        username="otheruser",
        email="other@example.com",
        is_active=True,
    )
    db_session.add(other_user)
    await db_session.commit()
    await db_session.refresh(other_user)
    
    # Create workspace owned by other user
    other_workspace = WorkspaceModel(
        name="Other Workspace",
        owner_user_id=other_user.user_id,
    )
    db_session.add(other_workspace)
    await db_session.commit()
    await db_session.refresh(other_workspace)
    
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        pdf_file = create_pdf_file()
        
        # Try to upload to other user's workspace
        response = await client.post(
            f"/api/workspaces/{other_workspace.workspace_id}/docs",
            files={"file": ("test.pdf", pdf_file, "application/pdf")},
            data={"user_id": str(test_user.user_id)}
        )
        
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_upload_empty_file(test_app, db_session, test_user, test_workspace):
    """Test upload of empty file."""
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Empty file
        empty_file = io.BytesIO(b"")
        
        response = await client.post(
            f"/api/workspaces/{test_workspace.workspace_id}/docs",
            files={"file": ("test.pdf", empty_file, "application/pdf")},
            data={"user_id": str(test_user.user_id)}
        )
        
        assert response.status_code == 400
