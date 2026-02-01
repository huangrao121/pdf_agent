"""
Integration tests for anchor creation endpoint.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from fastapi import FastAPI
from dotenv import load_dotenv

from pdf_ai_agent.config.database.models.model_user import UserModel, WorkspaceModel
from pdf_ai_agent.config.database.models.model_document import (
    DocsModel,
    DocPageModel,
    AnchorModel,
    ChunksModel,
    NoteModel,
    DocStatus,
)


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
async def test_doc_ready(db_session, test_user, test_workspace):
    """Create a test document with READY status."""
    doc = DocsModel(
        workspace_id=test_workspace.workspace_id,
        owner_user_id=test_user.user_id,
        filename="test.pdf",
        storage_uri="file:///tmp/test.pdf",
        file_type="application/pdf",
        file_size=1000,
        file_sha256="abc123",
        title="Test Document",
        status=DocStatus.READY,
        num_pages=15,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


@pytest.fixture
async def test_doc_uploaded(db_session, test_user, test_workspace):
    """Create a test document with UPLOADED status."""
    doc = DocsModel(
        workspace_id=test_workspace.workspace_id,
        owner_user_id=test_user.user_id,
        filename="test_uploaded.pdf",
        storage_uri="file:///tmp/test_uploaded.pdf",
        file_type="application/pdf",
        file_size=1000,
        file_sha256="def456",
        title="Test Document Uploaded",
        status=DocStatus.UPLOADED,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


@pytest.fixture
async def test_doc_page(db_session, test_doc_ready):
    """Create a test document page."""
    page = DocPageModel(
        doc_id=test_doc_ready.doc_id,
        page=12,
        width_pt=595.0,
        height_pt=842.0,
        rotation=0,
        text_layer_available=True,
    )
    db_session.add(page)
    await db_session.commit()
    await db_session.refresh(page)
    return page


@pytest.fixture
async def test_chunk(db_session, test_doc_ready):
    """Create a test chunk."""
    chunk = ChunksModel(
        doc_id=test_doc_ready.doc_id,
        chunk_index=0,
        page_start=12,
        page_end=12,
        text="Test chunk text",
        text_sha256="chunk_hash_123",
        token_count=10,
    )
    db_session.add(chunk)
    await db_session.commit()
    await db_session.refresh(chunk)
    return chunk


@pytest.fixture
async def test_note(db_session, test_user, test_workspace, test_doc_ready):
    """Create a test note."""
    note = NoteModel(
        workspace_id=test_workspace.workspace_id,
        doc_id=test_doc_ready.doc_id,
        owner_user_id=test_user.user_id,
        title="Test Note",
        markdown="Test note content",
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)
    return note


@pytest.fixture
async def test_app(db_session):
    """Create test app with overridden dependencies."""
    load_dotenv()
    app = FastAPI(title="PDF_Agent")

    # Override db session dependency
    from pdf_ai_agent.config.database.init_database import get_db_session

    async def override_get_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db_session

    # Register routers
    from pdf_ai_agent.api.routes.documents import router as documents_router

    app.include_router(documents_router)

    return app


@pytest.mark.asyncio
async def test_create_anchor_success(
    test_app, db_session, test_user, test_workspace, test_doc_ready, test_doc_page
):
    """Test successful anchor creation."""
    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_doc_ready.doc_id}/anchors?user_id={test_user.user_id}",
            json={
                "doc_id": test_doc_ready.doc_id,
                "page": 12,
                "quoted_text": "The model uses scaled dot-product attention.",
                "locator": {
                    "type": "pdf_quadpoints",
                    "coord_space": "pdf_points",
                    "page": 12,
                    "quads": [[72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]],
                },
            },
        )

        assert response.status_code == 201
        data = response.json()

        assert "anchor_id" in data
        assert isinstance(data["anchor_id"], int)

        # Verify anchor in database
        query = select(AnchorModel).where(AnchorModel.anchor_id == data["anchor_id"])
        result = await db_session.execute(query)
        anchor = result.scalar_one_or_none()

        assert anchor is not None
        assert anchor.doc_id == test_doc_ready.doc_id
        assert anchor.page == 12
        assert anchor.quoted_text == "The model uses scaled dot-product attention."
        assert anchor.locator["type"] == "pdf_quadpoints"


@pytest.mark.asyncio
async def test_create_anchor_idempotent(
    test_app, db_session, test_user, test_workspace, test_doc_ready, test_doc_page
):
    """Test anchor creation is idempotent."""
    transport = ASGITransport(app=test_app)

    request_data = {
        "doc_id": test_doc_ready.doc_id,
        "page": 12,
        "quoted_text": "The model uses scaled dot-product attention.",
        "locator": {
            "type": "pdf_quadpoints",
            "coord_space": "pdf_points",
            "page": 12,
            "quads": [[72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]],
        },
    }

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First request
        response1 = await client.post(
            f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_doc_ready.doc_id}/anchors?user_id={test_user.user_id}",
            json=request_data,
        )

        assert response1.status_code == 201
        data1 = response1.json()
        anchor_id_1 = data1["anchor_id"]

        # Second request (same data)
        response2 = await client.post(
            f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_doc_ready.doc_id}/anchors?user_id={test_user.user_id}",
            json=request_data,
        )

        assert response2.status_code == 201
        data2 = response2.json()
        anchor_id_2 = data2["anchor_id"]

        # Should return same anchor
        assert anchor_id_1 == anchor_id_2


@pytest.mark.asyncio
async def test_create_anchor_doc_not_ready(
    test_app, db_session, test_user, test_workspace, test_doc_uploaded
):
    """Test anchor creation fails when document is not READY."""
    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_doc_uploaded.doc_id}/anchors?user_id={test_user.user_id}",
            json={
                "doc_id": test_doc_uploaded.doc_id,
                "page": 12,
                "quoted_text": "The model uses scaled dot-product attention.",
                "locator": {
                    "type": "pdf_quadpoints",
                    "coord_space": "pdf_points",
                    "page": 12,
                    "quads": [[72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]],
                },
            },
        )

        assert response.status_code == 409
        data = response.json()
        assert data["detail"] == "DOC_NOT_READY"


@pytest.mark.asyncio
async def test_create_anchor_invalid_page(
    test_app, db_session, test_user, test_workspace, test_doc_ready, test_doc_page
):
    """Test anchor creation fails when page doesn't exist."""
    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Page 99 doesn't exist in doc_pages
        response = await client.post(
            f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_doc_ready.doc_id}/anchors?user_id={test_user.user_id}",
            json={
                "doc_id": test_doc_ready.doc_id,
                "page": 99,
                "quoted_text": "The model uses scaled dot-product attention.",
                "locator": {
                    "type": "pdf_quadpoints",
                    "coord_space": "pdf_points",
                    "page": 99,
                    "quads": [[72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]],
                },
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert data["detail"] == "INVALID_PAGE"


@pytest.mark.asyncio
async def test_create_anchor_page_mismatch(
    test_app, db_session, test_user, test_workspace, test_doc_ready, test_doc_page
):
    """Test anchor creation fails when body.page != locator.page."""
    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_doc_ready.doc_id}/anchors?user_id={test_user.user_id}",
            json={
                "doc_id": test_doc_ready.doc_id,
                "page": 12,
                "quoted_text": "The model uses scaled dot-product attention.",
                "locator": {
                    "type": "pdf_quadpoints",
                    "coord_space": "pdf_points",
                    "page": 13,  # Different from body page
                    "quads": [[72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]],
                },
            },
        )

        assert response.status_code == 422  # Pydantic validation error


@pytest.mark.asyncio
async def test_create_anchor_with_chunk(
    test_app,
    db_session,
    test_user,
    test_workspace,
    test_doc_ready,
    test_doc_page,
    test_chunk,
):
    """Test anchor creation with valid chunk_id."""
    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_doc_ready.doc_id}/anchors?user_id={test_user.user_id}",
            json={
                "chunk_id": test_chunk.chunk_id,
                "doc_id": test_doc_ready.doc_id,
                "page": 12,
                "quoted_text": "The model uses scaled dot-product attention.",
                "locator": {
                    "type": "pdf_quadpoints",
                    "coord_space": "pdf_points",
                    "page": 12,
                    "quads": [[72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]],
                },
            },
        )

        assert response.status_code == 201
        data = response.json()

        # Verify anchor has chunk_id
        query = select(AnchorModel).where(AnchorModel.anchor_id == data["anchor_id"])
        result = await db_session.execute(query)
        anchor = result.scalar_one_or_none()

        assert anchor.chunk_id == test_chunk.chunk_id


@pytest.mark.asyncio
async def test_create_anchor_chunk_mismatch(
    test_app, db_session, test_user, test_workspace, test_doc_ready, test_doc_page
):
    """Test anchor creation fails when chunk_id doesn't belong to doc."""
    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Use a non-existent chunk_id
        response = await client.post(
            f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_doc_ready.doc_id}/anchors?user_id={test_user.user_id}",
            json={
                "chunk_id": 99999,  # Non-existent chunk
                "doc_id": test_doc_ready.doc_id,
                "page": 12,
                "quoted_text": "The model uses scaled dot-product attention.",
                "locator": {
                    "type": "pdf_quadpoints",
                    "coord_space": "pdf_points",
                    "page": 12,
                    "quads": [[72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]],
                },
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert data["detail"] == "CHUNK_DOC_MISMATCH"


@pytest.mark.asyncio
async def test_create_anchor_forbidden_workspace(
    test_app, db_session, test_doc_ready, test_doc_page
):
    """Test anchor creation fails when user doesn't have access to workspace."""
    # Create a different user
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
        # Try to create anchor with different user
        response = await client.post(
            f"/api/workspaces/{test_doc_ready.workspace_id}/docs/{test_doc_ready.doc_id}/anchors?user_id={other_user.user_id}",
            json={
                "doc_id": test_doc_ready.doc_id,
                "page": 12,
                "quoted_text": "The model uses scaled dot-product attention.",
                "locator": {
                    "type": "pdf_quadpoints",
                    "coord_space": "pdf_points",
                    "page": 12,
                    "quads": [[72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]],
                },
            },
        )

        assert response.status_code == 403
        data = response.json()
        assert data["detail"] == "FORBIDDEN_WORKSPACE"


@pytest.mark.asyncio
async def test_create_anchor_doc_not_found(
    test_app, db_session, test_user, test_workspace
):
    """Test anchor creation fails when document doesn't exist."""
    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/workspaces/{test_workspace.workspace_id}/docs/99999/anchors?user_id={test_user.user_id}",
            json={
                "doc_id": 99999,
                "page": 12,
                "quoted_text": "The model uses scaled dot-product attention.",
                "locator": {
                    "type": "pdf_quadpoints",
                    "coord_space": "pdf_points",
                    "page": 12,
                    "quads": [[72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]],
                },
            },
        )

        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "DOC_NOT_FOUND"
