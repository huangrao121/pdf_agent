"""
Unit tests for note service components.
"""
import pytest
from sqlalchemy import select
from pdf_ai_agent.api.services.note_service import NoteService
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


class TestNoteCreation:
    """Tests for note creation."""

    @pytest.mark.asyncio
    async def test_create_workspace_level_note_success(self, db_session, test_user, test_workspace):
        """Test successful creation of workspace-level note."""
        note_service = NoteService(db_session=db_session)
        
        note = await note_service.create_note(
            workspace_id=test_workspace.workspace_id,
            user_id=test_user.user_id,
            content_markdown="# My Note\n\nThis is my note content.",
            doc_id=None,
            title=None,
        )
        
        assert note.note_id is not None
        assert note.workspace_id == test_workspace.workspace_id
        assert note.doc_id is None
        assert note.owner_user_id == test_user.user_id
        assert note.title == "My Note"
        assert note.markdown == "# My Note\n\nThis is my note content."

    @pytest.mark.asyncio
    async def test_create_doc_scoped_note_success(self, db_session, test_user, test_workspace, test_doc):
        """Test successful creation of doc-scoped note."""
        note_service = NoteService(db_session=db_session)
        
        note = await note_service.create_note(
            workspace_id=test_workspace.workspace_id,
            user_id=test_user.user_id,
            content_markdown="This is my doc note.",
            doc_id=test_doc.doc_id,
            title="My Doc Note",
        )
        
        assert note.note_id is not None
        assert note.workspace_id == test_workspace.workspace_id
        assert note.doc_id == test_doc.doc_id
        assert note.owner_user_id == test_user.user_id
        assert note.title == "My Doc Note"
        assert note.markdown == "This is my doc note."

    @pytest.mark.asyncio
    async def test_reject_blank_markdown(self, db_session, test_user, test_workspace):
        """Test rejection of blank markdown content."""
        from fastapi import HTTPException
        
        note_service = NoteService(db_session=db_session)
        
        with pytest.raises(HTTPException) as exc_info:
            await note_service.create_note(
                workspace_id=test_workspace.workspace_id,
                user_id=test_user.user_id,
                content_markdown="   \n  \n  ",
                doc_id=None,
                title=None,
            )
        
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["error"]["code"] == "INVALID_ARGUMENT"

    @pytest.mark.asyncio
    async def test_doc_not_found(self, db_session, test_user, test_workspace):
        """Test error when document not found."""
        from fastapi import HTTPException
        
        note_service = NoteService(db_session=db_session)
        
        with pytest.raises(HTTPException) as exc_info:
            await note_service.create_note(
                workspace_id=test_workspace.workspace_id,
                user_id=test_user.user_id,
                content_markdown="Test content",
                doc_id=99999,  # Non-existent doc
                title=None,
            )
        
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail["error"]["code"] == "DOC_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_doc_workspace_mismatch(self, db_session, test_user, test_workspace, test_doc):
        """Test error when document doesn't belong to workspace."""
        from fastapi import HTTPException
        
        # Create another workspace
        other_workspace = WorkspaceModel(
            name="Other Workspace",
            owner_user_id=test_user.user_id,
        )
        db_session.add(other_workspace)
        await db_session.commit()
        await db_session.refresh(other_workspace)
        
        note_service = NoteService(db_session=db_session)
        
        with pytest.raises(HTTPException) as exc_info:
            await note_service.create_note(
                workspace_id=other_workspace.workspace_id,
                user_id=test_user.user_id,
                content_markdown="Test content",
                doc_id=test_doc.doc_id,  # Doc belongs to test_workspace, not other_workspace
                title=None,
            )
        
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["error"]["code"] == "DOC_WORKSPACE_MISMATCH"

    @pytest.mark.asyncio
    async def test_title_generated_from_heading(self, db_session, test_user, test_workspace):
        """Test title auto-generation from H1 heading."""
        note_service = NoteService(db_session=db_session)
        
        note = await note_service.create_note(
            workspace_id=test_workspace.workspace_id,
            user_id=test_user.user_id,
            content_markdown="# My Generated Title\n\nSome content here.",
            doc_id=None,
            title=None,  # No title provided
        )
        
        assert note.title == "My Generated Title"

    @pytest.mark.asyncio
    async def test_title_fallback_untitled(self, db_session, test_user, test_workspace):
        """Test title fallback to 'Untitled Note' when no H1 heading."""
        note_service = NoteService(db_session=db_session)
        
        note = await note_service.create_note(
            workspace_id=test_workspace.workspace_id,
            user_id=test_user.user_id,
            content_markdown="Just some content without a heading.",
            doc_id=None,
            title=None,  # No title provided
        )
        
        assert note.title == "Untitled Note"


class TestMarkdownCleaning:
    """Tests for markdown content cleaning."""

    def test_trim_whitespace(self):
        """Test that markdown is trimmed."""
        cleaned = NoteService._clean_and_validate_markdown("  \n  Test content  \n  ")
        assert cleaned == "Test content"

    def test_reject_empty_after_trim(self):
        """Test rejection of empty content after trim."""
        with pytest.raises(ValueError):
            NoteService._clean_and_validate_markdown("   \n   \n   ")


class TestTitleGeneration:
    """Tests for title generation from markdown."""

    def test_extract_h1_heading(self):
        """Test extracting title from H1 heading."""
        title = NoteService._generate_title_from_markdown("# My Title\n\nContent")
        assert title == "My Title"

    def test_skip_non_h1_headings(self):
        """Test that non-H1 headings are ignored."""
        title = NoteService._generate_title_from_markdown("## My H2\n\nContent")
        assert title == "Untitled Note"

    def test_fallback_to_untitled(self):
        """Test fallback to 'Untitled Note'."""
        title = NoteService._generate_title_from_markdown("Just plain text")
        assert title == "Untitled Note"

    def test_trim_heading_whitespace(self):
        """Test that heading whitespace is trimmed."""
        title = NoteService._generate_title_from_markdown("#   My Title   \n\nContent")
        assert title == "My Title"

    def test_limit_title_length(self):
        """Test that title is limited to 255 characters."""
        long_heading = "# " + "a" * 300
        title = NoteService._generate_title_from_markdown(long_heading)
        assert len(title) == 255
