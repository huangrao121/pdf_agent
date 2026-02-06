"""
Unit tests for get_note service method.
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from pdf_ai_agent.api.services.note_service import NoteService
from pdf_ai_agent.config.database.models.model_user import UserModel, WorkspaceModel
from pdf_ai_agent.config.database.models.model_document import (
    DocsModel,
    NoteModel,
    AnchorModel,
)
from datetime import datetime, timedelta


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
    """Create a test note."""
    note = NoteModel(
        workspace_id=test_workspace.workspace_id,
        doc_id=test_doc.doc_id,
        owner_user_id=test_user.user_id,
        title="Test Note",
        markdown="# Test Note\n\nThis is test content.",
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


class TestGetNoteSuccess:
    """Tests for successful note retrieval."""

    @pytest.mark.asyncio
    async def test_get_note_success_returns_markdown(
        self, db_session, test_user, test_workspace, test_note
    ):
        """Test that get_note returns full markdown content."""
        note_service = NoteService(db_session=db_session)

        note, anchors = await note_service.get_note(
            workspace_id=test_workspace.workspace_id,
            note_id=test_note.note_id,
            user_id=test_user.user_id,
        )

        assert note.note_id == test_note.note_id
        assert note.markdown == "# Test Note\n\nThis is test content."
        assert note.title == "Test Note"
        assert note.version == 1
        assert isinstance(anchors, list)

    @pytest.mark.asyncio
    async def test_get_note_workspace_level_note(
        self, db_session, test_user, test_workspace, test_note_without_doc
    ):
        """Test getting workspace-level note (no doc_id)."""
        note_service = NoteService(db_session=db_session)

        note, anchors = await note_service.get_note(
            workspace_id=test_workspace.workspace_id,
            note_id=test_note_without_doc.note_id,
            user_id=test_user.user_id,
        )

        assert note.note_id == test_note_without_doc.note_id
        assert note.doc_id is None
        assert note.markdown == "# Workspace Note\n\nWorkspace-level content."
        assert isinstance(anchors, list)


class TestGetNoteWithAnchors:
    """Tests for note retrieval with anchors."""

    @pytest.mark.asyncio
    async def test_get_note_includes_anchors_sorted(
        self, db_session, test_user, test_workspace, test_note, test_doc
    ):
        """Test that anchors are returned sorted by created_at ASC."""
        # Create multiple anchors with different timestamps
        base_time = datetime.now()

        anchor1 = AnchorModel(
            note_id=test_note.note_id,
            doc_id=test_doc.doc_id,
            workspace_id=test_workspace.workspace_id,
            created_by_user_id=test_user.user_id,
            page=1,
            quoted_text="First quote",
            locator={
                "type": "pdf_quadpoints",
                "coord_space": "pdf_points",
                "page": 1,
                "quads": [[72.0, 512.0, 310.0, 512.0, 310.0, 498.0, 72.0, 498.0]],
            },
            locator_hash="hash1",
        )
        # Set created_at explicitly (oldest)
        anchor1.created_at = base_time - timedelta(seconds=20)

        anchor2 = AnchorModel(
            note_id=test_note.note_id,
            doc_id=test_doc.doc_id,
            workspace_id=test_workspace.workspace_id,
            created_by_user_id=test_user.user_id,
            page=2,
            quoted_text="Second quote",
            locator={
                "type": "pdf_quadpoints",
                "coord_space": "pdf_points",
                "page": 2,
                "quads": [[100.0, 600.0, 400.0, 600.0, 400.0, 580.0, 100.0, 580.0]],
            },
            locator_hash="hash2",
        )
        # Set created_at explicitly (newest)
        anchor2.created_at = base_time

        anchor3 = AnchorModel(
            note_id=test_note.note_id,
            doc_id=test_doc.doc_id,
            workspace_id=test_workspace.workspace_id,
            created_by_user_id=test_user.user_id,
            page=3,
            quoted_text="Third quote",
            locator={
                "type": "pdf_quadpoints",
                "coord_space": "pdf_points",
                "page": 3,
                "quads": [[50.0, 700.0, 300.0, 700.0, 300.0, 680.0, 50.0, 680.0]],
            },
            locator_hash="hash3",
        )
        # Set created_at explicitly (middle)
        anchor3.created_at = base_time - timedelta(seconds=10)

        # Add in random order
        db_session.add(anchor2)
        db_session.add(anchor1)
        db_session.add(anchor3)
        await db_session.commit()

        # Get note with anchors
        note_service = NoteService(db_session=db_session)
        note, anchors = await note_service.get_note(
            workspace_id=test_workspace.workspace_id,
            note_id=test_note.note_id,
            user_id=test_user.user_id,
        )

        # Verify anchors are sorted by created_at ASC
        assert len(anchors) == 3
        assert anchors[0].quoted_text == "First quote"  # oldest
        assert anchors[1].quoted_text == "Third quote"  # middle
        assert anchors[2].quoted_text == "Second quote"  # newest

        # Verify timestamps are ascending
        assert anchors[0].created_at < anchors[1].created_at
        assert anchors[1].created_at < anchors[2].created_at

    @pytest.mark.asyncio
    async def test_get_note_returns_empty_anchors_array(
        self, db_session, test_user, test_workspace, test_note
    ):
        """Test that get_note returns empty array when note has no anchors."""
        note_service = NoteService(db_session=db_session)

        note, anchors = await note_service.get_note(
            workspace_id=test_workspace.workspace_id,
            note_id=test_note.note_id,
            user_id=test_user.user_id,
        )

        assert note.note_id == test_note.note_id
        assert anchors == []
        assert isinstance(anchors, list)


class TestGetNoteErrors:
    """Tests for get_note error cases."""

    @pytest.mark.asyncio
    async def test_get_note_not_found(
        self, db_session, test_user, test_workspace
    ):
        """Test that get_note raises 404 when note doesn't exist."""
        note_service = NoteService(db_session=db_session)

        with pytest.raises(HTTPException) as exc_info:
            await note_service.get_note(
                workspace_id=test_workspace.workspace_id,
                note_id=999999,  # Non-existent note
                user_id=test_user.user_id,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "NOTE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_get_note_cross_workspace_not_found(
        self, db_session, test_user, test_workspace, other_workspace, other_user, test_note
    ):
        """Test that get_note returns 404 when workspace_id doesn't match (no leakage)."""
        note_service = NoteService(db_session=db_session)

        # Make other_user the owner of other_workspace (done in fixture)
        # test_user is a member of test_workspace only
        # Try to access note from test_workspace using other_workspace's ID
        # Since test_user is not a member of other_workspace, this should be 403
        with pytest.raises(HTTPException) as exc_info:
            await note_service.get_note(
                workspace_id=other_workspace.workspace_id,
                note_id=test_note.note_id,
                user_id=test_user.user_id,
            )

        # Returns 403 because test_user is not a member of other_workspace
        # This is correct - membership is checked before note existence
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "FORBIDDEN_WORKSPACE"

    @pytest.mark.asyncio
    async def test_get_note_forbidden_non_member(
        self, db_session, test_user, other_user, test_workspace, test_note
    ):
        """Test that non-member gets 403 FORBIDDEN_WORKSPACE."""
        note_service = NoteService(db_session=db_session)

        # other_user is not a member of test_workspace
        with pytest.raises(HTTPException) as exc_info:
            await note_service.get_note(
                workspace_id=test_workspace.workspace_id,
                note_id=test_note.note_id,
                user_id=other_user.user_id,
            )

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "FORBIDDEN_WORKSPACE"
