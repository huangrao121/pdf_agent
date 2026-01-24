"""
Integration tests for document metadata endpoint.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from datetime import datetime

from fastapi import FastAPI
from contextlib import asynccontextmanager

from pdf_ai_agent.config.database.models.model_user import UserModel, WorkspaceModel
from pdf_ai_agent.config.database.models.model_document import DocsModel, DocStatus
from pdf_ai_agent.api.routes.documents import router as documents_router


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
async def test_document(db_session, test_workspace, test_user):
    """Create a test document."""
    doc = DocsModel(
        workspace_id=test_workspace.workspace_id,
        owner_user_id=test_user.user_id,
        filename="test.pdf",
        storage_uri="file:///tmp/test.pdf",
        file_type="application/pdf",
        file_size=2345678,
        file_sha256="a" * 64,
        title="Test Document",
        author="Test Author",
        description="Test Description",
        language="en",
        status=DocStatus.READY,
        num_pages=15,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


@pytest.fixture
async def test_app(db_session):
    """Create test app with overridden dependencies."""
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from pdf_ai_agent.config.database.init_database import get_database_config, init_database, close_engine

        config = get_database_config()
        await init_database(config)
        yield
        await close_engine()

    app = FastAPI(title="PDF_Agent", lifespan=lifespan)
    app.include_router(documents_router)
    
    # Override db session dependency
    from pdf_ai_agent.config.database.init_database import get_db_session
    
    async def override_get_db_session():
        yield db_session
    
    app.dependency_overrides[get_db_session] = override_get_db_session
    
    return app

class TestDocumentMetadataAPI:
    """Tests for document metadata API."""
    @pytest.mark.asyncio
    async def test_get_document_metadata_success(self, test_app, db_session, test_user, test_workspace, test_document):
        """Test getting document metadata successfully."""
        transport = ASGITransport(app=test_app)
        
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_document.doc_id}/metadata",
                params={"user_id": test_user.user_id}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify all fields
            assert data["doc_id"] == test_document.doc_id
            assert data["filename"] == "test.pdf"
            assert data["file_type"] == "application/pdf"
            assert data["file_size"] == 2345678
            assert data["file_sha256"] == "a" * 64
            assert data["title"] == "Test Document"
            assert data["author"] == "Test Author"
            assert data["description"] == "Test Description"
            assert data["language"] == "en"
            assert data["status"] == "READY"
            assert data["error_message"] is None
            assert data["num_pages"] == 15
            assert "created_at" in data
            assert "updated_at" in data
            
            # Verify ETag header is present
            assert "etag" in response.headers


    @pytest.mark.asyncio
    async def test_get_document_metadata_with_etag(self, test_app, db_session, test_user, test_workspace, test_document):
        """Test ETag support with If-None-Match."""
        transport = ASGITransport(app=test_app)
        
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # First request to get ETag
            response1 = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_document.doc_id}/metadata",
                params={"user_id": test_user.user_id}
            )
            
            assert response1.status_code == 200
            etag = response1.headers.get("etag")
            assert etag is not None
            
            # Second request with If-None-Match header
            response2 = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_document.doc_id}/metadata",
                params={"user_id": test_user.user_id},
                headers={"If-None-Match": etag}
            )
            
            # Should return 304 Not Modified
            assert response2.status_code == 304
            assert response2.headers.get("etag") == etag


    @pytest.mark.asyncio
    async def test_get_document_metadata_not_found(self, test_app, db_session, test_user, test_workspace):
        """Test getting metadata for non-existent document."""
        transport = ASGITransport(app=test_app)
        
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/99999/metadata",
                params={"user_id": test_user.user_id}
            )
            
            assert response.status_code == 404


    @pytest.mark.asyncio
    async def test_get_document_metadata_forbidden(self, test_app, db_session, test_user, test_document):
        """Test getting metadata without workspace access."""
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
            # Try to get document metadata from other user's workspace
            response = await client.get(
                f"/api/workspaces/{other_workspace.workspace_id}/docs/{test_document.doc_id}/metadata",
                params={"user_id": test_user.user_id}
            )
            
            assert response.status_code == 403


    @pytest.mark.asyncio
    async def test_get_document_metadata_different_workspace(self, test_app, db_session, test_user, test_workspace, test_document):
        """Test that document can't be accessed from different workspace."""
        # Create another workspace for the same user
        other_workspace = WorkspaceModel(
            name="Other Workspace",
            owner_user_id=test_user.user_id,
        )
        db_session.add(other_workspace)
        await db_session.commit()
        await db_session.refresh(other_workspace)
        
        transport = ASGITransport(app=test_app)
        
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Try to access document using wrong workspace_id
            response = await client.get(
                f"/api/workspaces/{other_workspace.workspace_id}/docs/{test_document.doc_id}/metadata",
                params={"user_id": test_user.user_id}
            )
            
            # Should return 404 (not 403) to not leak info about doc existence
            assert response.status_code == 404


    @pytest.mark.asyncio
    async def test_get_document_metadata_with_null_fields(self, test_app, db_session, test_user, test_workspace):
        """Test document metadata with null optional fields."""
        # Create document with minimal fields
        doc = DocsModel(
            workspace_id=test_workspace.workspace_id,
            owner_user_id=test_user.user_id,
            filename="minimal.pdf",
            storage_uri="file:///tmp/minimal.pdf",
            file_type="application/pdf",
            file_size=1000,
            file_sha256="b" * 64,
            status=DocStatus.UPLOADED,
        )
        db_session.add(doc)
        await db_session.commit()
        await db_session.refresh(doc)
        
        transport = ASGITransport(app=test_app)
        
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/{doc.doc_id}/metadata",
                params={"user_id": test_user.user_id}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify null fields
            assert data["title"] is None
            assert data["author"] is None
            assert data["description"] is None
            assert data["language"] is None
            assert data["num_pages"] is None
            assert data["error_message"] is None


    @pytest.mark.asyncio
    async def test_get_document_metadata_failed_status(self, test_app, db_session, test_user, test_workspace):
        """Test document metadata with FAILED status and error message."""
        doc = DocsModel(
            workspace_id=test_workspace.workspace_id,
            owner_user_id=test_user.user_id,
            filename="failed.pdf",
            storage_uri="file:///tmp/failed.pdf",
            file_type="application/pdf",
            file_size=5000,
            file_sha256="c" * 64,
            status=DocStatus.FAILED,
            error_message="Failed to parse PDF",
        )
        db_session.add(doc)
        await db_session.commit()
        await db_session.refresh(doc)
        
        transport = ASGITransport(app=test_app)
        
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/{doc.doc_id}/metadata",
                params={"user_id": test_user.user_id}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] == "FAILED"
            assert data["error_message"] == "Failed to parse PDF"


    @pytest.mark.asyncio
    async def test_get_document_metadata_etag_changes_on_update(self, test_app, db_session, test_user, test_workspace, test_document):
        """Test that ETag changes when document metadata is updated."""
        transport = ASGITransport(app=test_app)
        
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Get initial ETag
            response1 = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_document.doc_id}/metadata",
                params={"user_id": test_user.user_id}
            )
            
            assert response1.status_code == 200
            etag1 = response1.headers.get("etag")
            
            # Update document (change num_pages)
            test_document.num_pages = 20
            await db_session.commit()
            await db_session.refresh(test_document)
            
            # Get new ETag
            response2 = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_document.doc_id}/metadata",
                params={"user_id": test_user.user_id}
            )
            
            assert response2.status_code == 200
            etag2 = response2.headers.get("etag")
            
            # ETags should be different
            assert etag1 != etag2
            
            # Using old ETag should return 200 (not 304)
            response3 = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_document.doc_id}/metadata",
                params={"user_id": test_user.user_id},
                headers={"If-None-Match": etag1}
            )
            
            assert response3.status_code == 200
