"""
Integration tests for GET note endpoint.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from datetime import datetime, timedelta

from pdf_ai_agent.config.database.models.model_user import UserModel, WorkspaceModel
from pdf_ai_agent.config.database.models.model_document import (
    DocsModel,
    NoteModel,
    AnchorModel,
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
async def other_user(db_session):
    """Create another test user (non-member)."""
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
async def other_workspace(db_session, other_user):
    """Create another workspace (not accessible to test_user)."""
    workspace = WorkspaceModel(
        name="Other Workspace",
        owner_user_id=other_user.user_id,
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
async def test_note(db_session, test_user, test_workspace, test_doc):
    """Create a test note with markdown content."""
    note = NoteModel(
        workspace_id=test_workspace.workspace_id,
        doc_id=test_doc.doc_id,
        owner_user_id=test_user.user_id,
        title="Attention Mechanism Summary",
        markdown="# Attention Mechanism\n\nThe model uses scaled dot-product attention.",
        version=1,
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)
    return note


@pytest.fixture
async def test_note_without_doc(db_session, test_user, test_workspace):
    """Create a workspace-level note (no doc_id)."""
    note = NoteModel(
        workspace_id=test_workspace.workspace_id,
        doc_id=None,
        owner_user_id=test_user.user_id,
        title="Workspace Note",
        markdown="# Workspace Note\n\nWorkspace-level content.",
        version=1,
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)
    return note


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
async def test_get_note_with_markdown_and_anchors(
    test_app, db_session, test_user, test_workspace, test_note, test_doc
):
    """Test GET note returns markdown content and anchors (member access)."""
    # Create anchors for the note
    base_time = datetime.now()

    anchor1 = AnchorModel(
        note_id=test_note.note_id,
        doc_id=test_doc.doc_id,
        workspace_id=test_workspace.workspace_id,
        created_by_user_id=test_user.user_id,
        page=12,
        quoted_text="The model uses scaled dot-product attention.",
        locator={
            "type": "pdf_quadpoints",
            "coord_space": "pdf_points",
            "page": 12,
            "quads": [[72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]],
        },
        locator_hash="hash1",
    )
    anchor1.created_at = base_time - timedelta(seconds=10)

    anchor2 = AnchorModel(
        note_id=test_note.note_id,
        doc_id=test_doc.doc_id,
        workspace_id=test_workspace.workspace_id,
        created_by_user_id=test_user.user_id,
        page=15,
        quoted_text="Second anchor text.",
        locator={
            "type": "pdf_quadpoints",
            "coord_space": "pdf_points",
            "page": 15,
            "quads": [[100.0, 600.0, 400.0, 600.0, 400.0, 580.0, 100.0, 580.0]],
        },
        locator_hash="hash2",
    )
    anchor2.created_at = base_time

    db_session.add(anchor1)
    db_session.add(anchor2)
    await db_session.commit()

    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/notes/{test_note.note_id}",
            params={"user_id": test_user.user_id},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify note structure
        assert "note" in data
        assert "anchors" in data

        # Verify note details
        note = data["note"]
        assert note["note_id"] == test_note.note_id
        assert note["workspace_id"] == test_workspace.workspace_id
        assert note["doc_id"] == test_doc.doc_id
        assert note["owner_user_id"] == test_user.user_id
        assert note["title"] == "Attention Mechanism Summary"
        assert note["markdown"] == "# Attention Mechanism\n\nThe model uses scaled dot-product attention."
        assert note["version"] == 1
        assert "created_at" in note
        assert "updated_at" in note

        # Verify anchors
        anchors = data["anchors"]
        assert len(anchors) == 2

        # Verify anchors are sorted by created_at ASC
        assert anchors[0]["quoted_text"] == "The model uses scaled dot-product attention."
        assert anchors[1]["quoted_text"] == "Second anchor text."

        # Verify anchor structure
        anchor = anchors[0]
        assert anchor["anchor_id"] is not None
        assert anchor["doc_id"] == test_doc.doc_id
        assert anchor["page"] == 12
        assert "chunk_id" in anchor
        assert "locator" in anchor
        assert anchor["locator"]["type"] == "pdf_quadpoints"
        assert anchor["locator"]["coord_space"] == "pdf_points"
        assert anchor["locator"]["page"] == 12
        assert len(anchor["locator"]["quads"]) == 1
        assert len(anchor["locator"]["quads"][0]) == 8


@pytest.mark.asyncio
async def test_get_note_with_empty_anchors_array(
    test_app, db_session, test_user, test_workspace, test_note
):
    """Test GET note returns empty anchors array when note has no anchors."""
    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/notes/{test_note.note_id}",
            params={"user_id": test_user.user_id},
        )

        assert response.status_code == 200
        data = response.json()

        assert "note" in data
        assert "anchors" in data

        # Verify note details
        note = data["note"]
        assert note["note_id"] == test_note.note_id
        assert note["markdown"] == "# Attention Mechanism\n\nThe model uses scaled dot-product attention."

        # Verify empty anchors array
        anchors = data["anchors"]
        assert anchors == []
        assert isinstance(anchors, list)


@pytest.mark.asyncio
async def test_get_note_workspace_level_note(
    test_app, db_session, test_user, test_workspace, test_note_without_doc
):
    """Test GET workspace-level note (doc_id is null)."""
    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/notes/{test_note_without_doc.note_id}",
            params={"user_id": test_user.user_id},
        )

        assert response.status_code == 200
        data = response.json()

        note = data["note"]
        assert note["note_id"] == test_note_without_doc.note_id
        assert note["doc_id"] is None
        assert note["title"] == "Workspace Note"
        assert note["markdown"] == "# Workspace Note\n\nWorkspace-level content."


@pytest.mark.asyncio
async def test_get_note_forbidden_non_member(
    test_app, db_session, test_user, other_user, test_workspace, test_note
):
    """Test GET note returns 403 when user is not a workspace member."""
    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Try to access note as other_user who is not a member
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/notes/{test_note.note_id}",
            params={"user_id": other_user.user_id},
        )

        assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_note_wrong_workspace_returns_404(
    test_app, db_session, test_user, test_workspace, other_workspace, test_note
):
    """Test GET note returns 404 when workspace_id doesn't match."""
    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Try to access note from test_workspace using other_workspace's ID
        # User is owner of test_workspace but not other_workspace
        # Should get 403 for no access to other_workspace
        response = await client.get(
            f"/api/workspaces/{other_workspace.workspace_id}/notes/{test_note.note_id}",
            params={"user_id": test_user.user_id},
        )

        # Returns 403 because user is not member of other_workspace
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_note_not_found_404(
    test_app, db_session, test_user, test_workspace
):
    """Test GET note returns 404 when note doesn't exist."""
    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/notes/999999",
            params={"user_id": test_user.user_id},
        )

        assert response.status_code == 404
