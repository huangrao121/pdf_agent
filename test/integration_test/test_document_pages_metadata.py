"""
Integration tests for document pages metadata endpoint.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from fastapi import FastAPI
from contextlib import asynccontextmanager

from pdf_ai_agent.config.database.models.model_user import UserModel, WorkspaceModel
from pdf_ai_agent.config.database.models.model_document import (
    DocsModel,
    DocPageModel,
    DocStatus,
)
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
async def test_document_ready(db_session, test_workspace, test_user):
    """Create a test document in READY status."""
    doc = DocsModel(
        workspace_id=test_workspace.workspace_id,
        owner_user_id=test_user.user_id,
        filename="test.pdf",
        storage_uri="file:///tmp/test.pdf",
        file_type="application/pdf",
        file_size=2345678,
        file_sha256="a" * 64,
        title="Test Document",
        status=DocStatus.READY,
        num_pages=3,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


@pytest.fixture
async def test_document_uploaded(db_session, test_workspace, test_user):
    """Create a test document in UPLOADED status (not ready)."""
    doc = DocsModel(
        workspace_id=test_workspace.workspace_id,
        owner_user_id=test_user.user_id,
        filename="uploading.pdf",
        storage_uri="file:///tmp/uploading.pdf",
        file_type="application/pdf",
        file_size=1000000,
        file_sha256="b" * 64,
        title="Uploading Document",
        status=DocStatus.UPLOADED,
        num_pages=None,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


@pytest.fixture
async def test_pages(db_session, test_document_ready):
    """Create test pages for the document."""
    pages = [
        DocPageModel(
            doc_id=test_document_ready.doc_id,
            page=1,
            width_pt=595.0,
            height_pt=842.0,
            rotation=0,
            text_layer_available=True,
        ),
        DocPageModel(
            doc_id=test_document_ready.doc_id,
            page=2,
            width_pt=595.0,
            height_pt=842.0,
            rotation=90,
            text_layer_available=True,
        ),
        DocPageModel(
            doc_id=test_document_ready.doc_id,
            page=3,
            width_pt=612.0,
            height_pt=792.0,
            rotation=0,
            text_layer_available=False,
        ),
    ]
    for page in pages:
        db_session.add(page)
    await db_session.commit()
    for page in pages:
        await db_session.refresh(page)
    return pages


@pytest.fixture
async def test_app(db_session):
    """Create test app with overridden dependencies."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from pdf_ai_agent.config.database.init_database import (
            get_database_config,
            init_database,
            close_engine,
        )

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


class TestDocumentPagesMetadataAPI:
    """Tests for document pages metadata API."""

    @pytest.mark.asyncio
    async def test_get_pages_metadata_success(
        self,
        test_app,
        db_session,
        test_user,
        test_workspace,
        test_document_ready,
        test_pages,
    ):
        """Test getting pages metadata successfully."""
        transport = ASGITransport(app=test_app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_document_ready.doc_id}/pages",
                params={"user_id": test_user.user_id},
            )

            assert response.status_code == 200
            data = response.json()

            # Verify response structure
            assert data["doc_id"] == test_document_ready.doc_id
            assert "pages" in data
            assert len(data["pages"]) == 3

            # Verify page 1
            page1 = data["pages"][0]
            assert page1["page"] == 1
            assert page1["width_pt"] == 595.0
            assert page1["height_pt"] == 842.0
            assert page1["rotation"] == 0
            assert page1["text_layer_available"] is True

            # Verify page 2 (with rotation)
            page2 = data["pages"][1]
            assert page2["page"] == 2
            assert page2["rotation"] == 90

            # Verify page 3 (no text layer)
            page3 = data["pages"][2]
            assert page3["page"] == 3
            assert page3["width_pt"] == 612.0
            assert page3["height_pt"] == 792.0
            assert page3["text_layer_available"] is False

    @pytest.mark.asyncio
    async def test_get_pages_metadata_not_ready(
        self, test_app, db_session, test_user, test_workspace, test_document_uploaded
    ):
        """Test getting pages metadata when document is not READY."""
        transport = ASGITransport(app=test_app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_document_uploaded.doc_id}/pages",
                params={"user_id": test_user.user_id},
            )

            # Should return 409 Conflict
            assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_get_pages_metadata_not_found(
        self, test_app, db_session, test_user, test_workspace
    ):
        """Test getting pages metadata for non-existent document."""
        transport = ASGITransport(app=test_app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/99999/pages",
                params={"user_id": test_user.user_id},
            )

            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_pages_metadata_forbidden(
        self, test_app, db_session, test_user, test_document_ready
    ):
        """Test getting pages metadata without workspace access."""
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
            # Try to get pages metadata from other user's workspace
            response = await client.get(
                f"/api/workspaces/{other_workspace.workspace_id}/docs/{test_document_ready.doc_id}/pages",
                params={"user_id": test_user.user_id},
            )

            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_pages_metadata_different_workspace(
        self,
        test_app,
        db_session,
        test_user,
        test_workspace,
        test_document_ready,
        test_pages,
    ):
        """Test that pages metadata can't be accessed from different workspace."""
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
            # Try to access pages using wrong workspace_id
            response = await client.get(
                f"/api/workspaces/{other_workspace.workspace_id}/docs/{test_document_ready.doc_id}/pages",
                params={"user_id": test_user.user_id},
            )

            # Should return 404 to not leak info about doc existence
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_pages_metadata_empty_pages(
        self, test_app, db_session, test_user, test_workspace, test_document_ready
    ):
        """Test getting pages metadata when no pages exist yet."""
        # Don't create pages for this test
        transport = ASGITransport(app=test_app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_document_ready.doc_id}/pages",
                params={"user_id": test_user.user_id},
            )

            assert response.status_code == 200
            data = response.json()

            # Should return empty pages array
            assert data["doc_id"] == test_document_ready.doc_id
            assert data["pages"] == []

    @pytest.mark.asyncio
    async def test_get_pages_metadata_ordering(
        self,
        test_app,
        db_session,
        test_user,
        test_workspace,
        test_document_ready,
    ):
        """Test that pages are returned in correct order."""
        # Create pages in non-sequential order
        pages = [
            DocPageModel(
                doc_id=test_document_ready.doc_id,
                page=3,
                width_pt=595.0,
                height_pt=842.0,
                rotation=0,
                text_layer_available=True,
            ),
            DocPageModel(
                doc_id=test_document_ready.doc_id,
                page=1,
                width_pt=595.0,
                height_pt=842.0,
                rotation=0,
                text_layer_available=True,
            ),
            DocPageModel(
                doc_id=test_document_ready.doc_id,
                page=2,
                width_pt=595.0,
                height_pt=842.0,
                rotation=0,
                text_layer_available=True,
            ),
        ]
        for page in pages:
            db_session.add(page)
        await db_session.commit()

        transport = ASGITransport(app=test_app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_document_ready.doc_id}/pages",
                params={"user_id": test_user.user_id},
            )

            assert response.status_code == 200
            data = response.json()

            # Verify pages are ordered by page number
            assert len(data["pages"]) == 3
            assert data["pages"][0]["page"] == 1
            assert data["pages"][1]["page"] == 2
            assert data["pages"][2]["page"] == 3
