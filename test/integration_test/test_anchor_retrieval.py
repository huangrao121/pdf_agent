"""
Integration tests for anchor retrieval (GET) endpoint.
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
async def test_user_2(db_session):
    """Create a second test user for permission tests."""
    user = UserModel(
        username="testuser2",
        email="test2@example.com",
        full_name="Test User 2",
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
async def test_workspace_2(db_session, test_user_2):
    """Create a second test workspace for isolation tests."""
    workspace = WorkspaceModel(
        name="Test Workspace 2",
        owner_user_id=test_user_2.user_id,
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
async def test_doc_2(db_session, test_user_2, test_workspace_2):
    """Create a second test document in different workspace."""
    doc = DocsModel(
        workspace_id=test_workspace_2.workspace_id,
        owner_user_id=test_user_2.user_id,
        filename="test2.pdf",
        storage_uri="file:///tmp/test2.pdf",
        file_type="application/pdf",
        file_size=1000,
        file_sha256="def456",
        title="Test Document 2",
        status=DocStatus.READY,
        num_pages=10,
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
        page=32,
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
async def test_anchor(db_session, test_user, test_workspace, test_doc_ready, test_doc_page):
    """Create a test anchor."""
    anchor = AnchorModel(
        doc_id=test_doc_ready.doc_id,
        workspace_id=test_workspace.workspace_id,
        created_by_user_id=test_user.user_id,
        page=32,
        quoted_text="this is text",
        locator={
            "type": "pdf_quadpoints",
            "coord_space": "pdf_points",
            "page": 32,
            "quads": [[72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]],
        },
        locator_hash="test_hash_123",
        chunk_id=None,
        note_id=None,
    )
    db_session.add(anchor)
    await db_session.commit()
    await db_session.refresh(anchor)
    return anchor


@pytest.fixture
async def test_anchor_2(db_session, test_user_2, test_workspace_2, test_doc_2):
    """Create a test anchor in different workspace."""
    # Create page first
    page = DocPageModel(
        doc_id=test_doc_2.doc_id,
        page=5,
        width_pt=595.0,
        height_pt=842.0,
        rotation=0,
        text_layer_available=True,
    )
    db_session.add(page)
    await db_session.commit()
    
    anchor = AnchorModel(
        doc_id=test_doc_2.doc_id,
        workspace_id=test_workspace_2.workspace_id,
        created_by_user_id=test_user_2.user_id,
        page=5,
        quoted_text="other text",
        locator={
            "type": "pdf_quadpoints",
            "coord_space": "pdf_points",
            "page": 5,
            "quads": [[100.0, 200.0, 300.0, 200.0, 300.0, 180.0, 100.0, 180.0]],
        },
        locator_hash="test_hash_456",
        chunk_id=None,
        note_id=None,
    )
    db_session.add(anchor)
    await db_session.commit()
    await db_session.refresh(anchor)
    return anchor


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
async def test_get_anchor_success(
    test_app, db_session, test_user, test_workspace, test_doc_ready, test_anchor
):
    """Test successful anchor retrieval (happy path)."""
    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_doc_ready.doc_id}/anchors/{test_anchor.anchor_id}?user_id={test_user.user_id}"
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure and content
        assert data["anchor_id"] == test_anchor.anchor_id
        assert data["doc_id"] == test_doc_ready.doc_id
        assert data["page"] == 32
        assert data["quoted_text"] == "this is text"
        assert data["chunk_id"] is None
        assert data["note_id"] is None
        
        # Verify locator is returned as-is
        assert data["locator"]["type"] == "pdf_quadpoints"
        assert data["locator"]["coord_space"] == "pdf_points"
        assert data["locator"]["page"] == 32
        assert len(data["locator"]["quads"]) == 1
        assert data["locator"]["quads"][0] == [72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]
        
        # Verify created_at is present
        assert "created_at" in data


@pytest.mark.asyncio
async def test_get_anchor_workspace_isolation(
    test_app, db_session, test_user, test_workspace, test_doc_ready, test_anchor_2
):
    """Test that anchors from other workspaces return 403 (workspace isolation)."""
    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Try to access anchor from workspace_2 using user from workspace_1
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_doc_ready.doc_id}/anchors/{test_anchor_2.anchor_id}?user_id={test_user.user_id}"
        )

        # Should return 404 (not 403) to not leak existence
        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "ANCHOR_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_anchor_doc_mismatch(
    test_app, db_session, test_user, test_workspace, test_doc_ready, test_anchor, test_doc_2
):
    """Test that anchor from different doc_id returns 404."""
    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Try to access anchor with wrong doc_id
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_doc_2.doc_id}/anchors/{test_anchor.anchor_id}?user_id={test_user.user_id}"
        )

        # Should return 404 even if anchor exists, to prevent enumeration
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_anchor_not_found(
    test_app, db_session, test_user, test_workspace, test_doc_ready
):
    """Test getting non-existent anchor returns 404."""
    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Try to access non-existent anchor
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_doc_ready.doc_id}/anchors/99999?user_id={test_user.user_id}"
        )

        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "ANCHOR_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_anchor_forbidden_workspace(
    test_app, db_session, test_user, test_user_2, test_workspace_2, test_doc_2, test_anchor_2
):
    """Test that accessing anchor without workspace membership returns 403."""
    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # User 1 tries to access workspace 2's anchor
        response = await client.get(
            f"/api/workspaces/{test_workspace_2.workspace_id}/docs/{test_doc_2.doc_id}/anchors/{test_anchor_2.anchor_id}?user_id={test_user.user_id}"
        )

        assert response.status_code == 403
        data = response.json()
        assert data["detail"] == "FORBIDDEN_WORKSPACE"


@pytest.mark.asyncio
async def test_get_anchor_with_dirty_locator(
    test_app, db_session, test_user, test_workspace, test_doc_ready, test_doc_page
):
    """Test locator contract tolerance - missing fields should still return 200."""
    # Create anchor with incomplete locator (missing required fields)
    anchor = AnchorModel(
        doc_id=test_doc_ready.doc_id,
        workspace_id=test_workspace.workspace_id,
        created_by_user_id=test_user.user_id,
        page=32,
        quoted_text="dirty data",
        locator={
            "page": 32,
            # Missing: type, coord_space, quads
        },
        locator_hash="dirty_hash_789",
        chunk_id=None,
        note_id=None,
    )
    db_session.add(anchor)
    await db_session.commit()
    await db_session.refresh(anchor)

    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_doc_ready.doc_id}/anchors/{anchor.anchor_id}?user_id={test_user.user_id}"
        )

        # Should return 200 even with incomplete locator
        assert response.status_code == 200
        data = response.json()
        assert data["anchor_id"] == anchor.anchor_id
        # Locator should be returned as-is (not normalized)
        assert data["locator"]["page"] == 32
        assert "type" not in data["locator"]
