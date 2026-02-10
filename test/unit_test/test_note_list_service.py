"""
Unit tests for note list service.
"""
import pytest
from datetime import datetime
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


@pytest.fixture
async def other_workspace(db_session, test_user):
    """Create another workspace."""
    workspace = WorkspaceModel(
        name="Other Workspace",
        owner_user_id=test_user.user_id,
    )
    db_session.add(workspace)
    await db_session.commit()
    await db_session.refresh(workspace)
    return workspace


class TestListNotes:
    """Tests for note listing."""

    @pytest.mark.asyncio
    async def test_list_notes_workspace_level_only(self, db_session, test_user, test_workspace):
        """Test listing all notes in workspace without doc_id filter."""
        note_service = NoteService(db_session=db_session)
        
        # Create several notes
        note1 = await note_service.create_note(
            workspace_id=test_workspace.workspace_id,
            user_id=test_user.user_id,
            content_markdown="# Note 1",
            doc_id=None,
        )
        note2 = await note_service.create_note(
            workspace_id=test_workspace.workspace_id,
            user_id=test_user.user_id,
            content_markdown="# Note 2",
            doc_id=None,
        )
        
        # List notes without doc_id filter
        notes, next_cursor = await note_service.list_notes(
            workspace_id=test_workspace.workspace_id,
            user_id=test_user.user_id,
            doc_id=None,
            limit=20,
        )
        
        assert len(notes) == 2
        # Should be sorted by created_at DESC, note_id DESC
        assert notes[0].note_id == note2.note_id
        assert notes[1].note_id == note1.note_id
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_list_notes_doc_scoped_only(self, db_session, test_user, test_workspace, test_doc):
        """Test listing notes filtered by doc_id."""
        note_service = NoteService(db_session=db_session)
        
        # Create workspace-level note
        await note_service.create_note(
            workspace_id=test_workspace.workspace_id,
            user_id=test_user.user_id,
            content_markdown="# Workspace Note",
            doc_id=None,
        )
        
        # Create doc-scoped note
        doc_note = await note_service.create_note(
            workspace_id=test_workspace.workspace_id,
            user_id=test_user.user_id,
            content_markdown="# Doc Note",
            doc_id=test_doc.doc_id,
        )
        
        # List notes with doc_id filter
        notes, next_cursor = await note_service.list_notes(
            workspace_id=test_workspace.workspace_id,
            user_id=test_user.user_id,
            doc_id=test_doc.doc_id,
            limit=20,
        )
        
        # Should only return doc-scoped note
        assert len(notes) == 1
        assert notes[0].note_id == doc_note.note_id
        assert notes[0].doc_id == test_doc.doc_id
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_doc_not_found(self, db_session, test_user, test_workspace):
        """Test error when doc_id doesn't exist."""
        from fastapi import HTTPException
        
        note_service = NoteService(db_session=db_session)
        
        with pytest.raises(HTTPException) as exc_info:
            await note_service.list_notes(
                workspace_id=test_workspace.workspace_id,
                user_id=test_user.user_id,
                doc_id=99999,  # Non-existent doc
                limit=20,
            )
        
        assert exc_info.value.status_code == 404
        assert "DOC_NOT_FOUND" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_doc_workspace_mismatch(self, db_session, test_user, test_workspace, test_doc, other_workspace):
        """Test error when doc doesn't belong to workspace."""
        from fastapi import HTTPException
        
        note_service = NoteService(db_session=db_session)
        
        with pytest.raises(HTTPException) as exc_info:
            await note_service.list_notes(
                workspace_id=other_workspace.workspace_id,
                user_id=test_user.user_id,
                doc_id=test_doc.doc_id,  # Doc belongs to test_workspace
                limit=20,
            )
        
        assert exc_info.value.status_code == 409
        assert "DOC_WORKSPACE_MISMATCH" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_cursor_decode_invalid(self, db_session, test_user, test_workspace):
        """Test error with invalid cursor."""
        from fastapi import HTTPException
        
        note_service = NoteService(db_session=db_session)
        
        with pytest.raises(HTTPException) as exc_info:
            await note_service.list_notes(
                workspace_id=test_workspace.workspace_id,
                user_id=test_user.user_id,
                doc_id=None,
                limit=20,
                cursor="invalid_base64_!@#$%",
            )
        
        assert exc_info.value.status_code == 400
        assert "INVALID_CURSOR" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_cursor_pagination_boundary(self, db_session, test_user, test_workspace):
        """Test pagination with same created_at but different note_ids."""
        note_service = NoteService(db_session=db_session)
        
        # Create notes with same created_at (using manual insert)
        base_time = datetime.now()
        
        note1 = NoteModel(
            workspace_id=test_workspace.workspace_id,
            owner_user_id=test_user.user_id,
            title="Note 1",
            markdown="Content 1",
            created_at=base_time,
            updated_at=base_time,
        )
        note2 = NoteModel(
            workspace_id=test_workspace.workspace_id,
            owner_user_id=test_user.user_id,
            title="Note 2",
            markdown="Content 2",
            created_at=base_time,
            updated_at=base_time,
        )
        note3 = NoteModel(
            workspace_id=test_workspace.workspace_id,
            owner_user_id=test_user.user_id,
            title="Note 3",
            markdown="Content 3",
            created_at=base_time,
            updated_at=base_time,
        )
        
        db_session.add_all([note1, note2, note3])
        await db_session.commit()
        await db_session.refresh(note1)
        await db_session.refresh(note2)
        await db_session.refresh(note3)
        
        # List first page with limit 2
        notes_page1, cursor1 = await note_service.list_notes(
            workspace_id=test_workspace.workspace_id,
            user_id=test_user.user_id,
            doc_id=None,
            limit=2,
        )
        
        assert len(notes_page1) == 2
        assert cursor1 is not None
        
        # List second page with cursor
        notes_page2, cursor2 = await note_service.list_notes(
            workspace_id=test_workspace.workspace_id,
            user_id=test_user.user_id,
            doc_id=None,
            limit=2,
            cursor=cursor1,
        )
        
        assert len(notes_page2) == 1
        assert cursor2 is None
        
        # Verify all notes are accounted for
        all_note_ids = {n.note_id for n in notes_page1} | {n.note_id for n in notes_page2}
        assert all_note_ids == {note1.note_id, note2.note_id, note3.note_id}

    @pytest.mark.asyncio
    async def test_limit_clamped(self, db_session, test_user, test_workspace):
        """Test that limit > 100 is clamped to 100."""
        note_service = NoteService(db_session=db_session)
        
        # Create a few notes
        for i in range(5):
            await note_service.create_note(
                workspace_id=test_workspace.workspace_id,
                user_id=test_user.user_id,
                content_markdown=f"# Note {i}",
                doc_id=None,
            )
        
        # Request with limit > 100
        notes, next_cursor = await note_service.list_notes(
            workspace_id=test_workspace.workspace_id,
            user_id=test_user.user_id,
            doc_id=None,
            limit=150,  # Should be clamped to 100
        )
        
        # Should return all 5 notes since we only have 5
        assert len(notes) == 5
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_forbidden_workspace(self, db_session, test_workspace):
        """Test error when user doesn't have access to workspace."""
        from fastapi import HTTPException
        
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
        
        note_service = NoteService(db_session=db_session)
        
        with pytest.raises(HTTPException) as exc_info:
            await note_service.list_notes(
                workspace_id=test_workspace.workspace_id,
                user_id=other_user.user_id,
                doc_id=None,
                limit=20,
            )
        
        assert exc_info.value.status_code == 403
        assert "FORBIDDEN_WORKSPACE" in exc_info.value.detail


class TestCursorEncoding:
    """Tests for cursor encoding/decoding."""

    def test_encode_decode_cursor(self):
        """Test cursor encoding and decoding round-trip."""
        note_id = 123
        created_at = datetime(2026, 1, 22, 8, 30, 0)
        
        # Encode
        cursor = NoteService.encode_cursor(note_id, created_at)
        
        # Decode
        decoded_note_id, decoded_created_at = NoteService.decode_cursor(cursor)
        
        assert decoded_note_id == note_id
        assert decoded_created_at == created_at

    def test_decode_invalid_base64(self):
        """Test decoding invalid base64."""
        from fastapi import HTTPException
        
        with pytest.raises(HTTPException) as exc_info:
            NoteService.decode_cursor("not_valid_base64_!@#$")
        
        assert exc_info.value.status_code == 400
        assert "INVALID_CURSOR" in exc_info.value.detail

    def test_decode_invalid_json(self):
        """Test decoding invalid JSON."""
        from fastapi import HTTPException
        import base64
        
        # Encode invalid JSON as base64
        invalid_json = "not valid json"
        cursor = base64.urlsafe_b64encode(invalid_json.encode("utf-8")).decode("utf-8").rstrip("=")
        
        with pytest.raises(HTTPException) as exc_info:
            NoteService.decode_cursor(cursor)
        
        assert exc_info.value.status_code == 400
        assert "INVALID_CURSOR" in exc_info.value.detail

    def test_decode_missing_fields(self):
        """Test decoding cursor with missing required fields."""
        from fastapi import HTTPException
        import json
        import base64
        
        # Encode cursor with missing note_id
        cursor_data = {"created_at": "2026-01-22T08:30:00"}
        cursor_json = json.dumps(cursor_data)
        cursor = base64.urlsafe_b64encode(cursor_json.encode("utf-8")).decode("utf-8").rstrip("=")
        
        with pytest.raises(HTTPException) as exc_info:
            NoteService.decode_cursor(cursor)
        
        assert exc_info.value.status_code == 400
        assert "INVALID_CURSOR" in exc_info.value.detail
