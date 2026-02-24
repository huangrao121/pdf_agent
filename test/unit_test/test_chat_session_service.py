"""Unit tests for chat session service."""
import pytest
from fastapi import HTTPException

from pdf_ai_agent.api.services.chat_session_service import ChatSessionService
from pdf_ai_agent.config.database.models.model_user import UserModel, WorkspaceModel
from pdf_ai_agent.config.database.models.model_document import DocsModel, NoteModel, AnchorModel


@pytest.fixture
async def test_user(db_session):
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
async def test_note(db_session, test_user, test_workspace):
    note = NoteModel(
        workspace_id=test_workspace.workspace_id,
        doc_id=None,
        owner_user_id=test_user.user_id,
        title="Test Note",
        markdown="Some content",
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)
    return note


@pytest.fixture
async def test_anchor(db_session, test_user, test_workspace, test_doc, test_note):
    anchor = AnchorModel(
        created_by_user_id=test_user.user_id,
        note_id=test_note.note_id,
        doc_id=test_doc.doc_id,
        chunk_id=None,
        workspace_id=test_workspace.workspace_id,
        page=1,
        quoted_text="quote",
        locator={"type": "pdf_quadpoints"},
        locator_hash="hash_anchor_1",
    )
    db_session.add(anchor)
    await db_session.commit()
    await db_session.refresh(anchor)
    return anchor


@pytest.fixture
async def test_doc_anchor(db_session, test_user, test_workspace, test_doc):
    anchor = AnchorModel(
        created_by_user_id=test_user.user_id,
        note_id=None,
        doc_id=test_doc.doc_id,
        chunk_id=None,
        workspace_id=test_workspace.workspace_id,
        page=2,
        quoted_text="doc quote",
        locator={"type": "pdf_quadpoints"},
        locator_hash="hash_anchor_2",
    )
    db_session.add(anchor)
    await db_session.commit()
    await db_session.refresh(anchor)
    return anchor


class TestChatSessionService:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("mode", ["ask", "assist", "agent"])
    async def test_create_session_valid_modes(self, db_session, test_user, test_workspace, mode):
        service = ChatSessionService(db_session=db_session)

        session = await service.create_session(
            workspace_id=test_workspace.workspace_id,
            user_id=test_user.user_id,
            title=None,
            mode=mode,
            context=None,
            defaults=None,
            client_request_id=None,
        )

        assert session.mode.value == mode

    @pytest.mark.asyncio
    async def test_create_session_success_defaults(self, db_session, test_user, test_workspace):
        service = ChatSessionService(db_session=db_session)

        session = await service.create_session(
            workspace_id=test_workspace.workspace_id,
            user_id=test_user.user_id,
            title=None,
            mode=None,
            context=None,
            defaults=None,
            client_request_id=None,
        )

        assert session.session_id is not None
        assert session.title == "New chat"
        assert session.mode.value == "ask"
        assert session.defaults_json["model"] == "gpt-4.1-mini"
        assert session.defaults_json["temperature"] == 0.2
        assert session.defaults_json["top_p"] == 1.0
        assert session.context_json["note_id"] is None

    @pytest.mark.asyncio
    async def test_create_session_invalid_mode(self, db_session, test_user, test_workspace):
        service = ChatSessionService(db_session=db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_session(
                workspace_id=test_workspace.workspace_id,
                user_id=test_user.user_id,
                title=None,
                mode="invalid",
                context=None,
                defaults=None,
                client_request_id=None,
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_create_session_invalid_defaults(self, db_session, test_user, test_workspace):
        service = ChatSessionService(db_session=db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_session(
                workspace_id=test_workspace.workspace_id,
                user_id=test_user.user_id,
                title=None,
                mode="ask",
                context=None,
                defaults={"temperature": -0.1},
                client_request_id=None,
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_create_session_defaults_boundary(self, db_session, test_user, test_workspace):
        service = ChatSessionService(db_session=db_session)

        session = await service.create_session(
            workspace_id=test_workspace.workspace_id,
            user_id=test_user.user_id,
            title=None,
            mode="ask",
            context=None,
            defaults={"temperature": 0.0, "top_p": 1.0, "retrieval": {"top_k": 1}},
            client_request_id=None,
        )

        assert session.defaults_json["temperature"] == 0.0
        assert session.defaults_json["top_p"] == 1.0
        assert session.defaults_json["retrieval"]["top_k"] == 1

    @pytest.mark.asyncio
    async def test_create_session_defaults_top_p_zero_invalid(self, db_session, test_user, test_workspace):
        service = ChatSessionService(db_session=db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_session(
                workspace_id=test_workspace.workspace_id,
                user_id=test_user.user_id,
                title=None,
                mode="ask",
                context=None,
                defaults={"top_p": 0.0},
                client_request_id=None,
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_create_session_context_anchor_validation(
        self,
        db_session,
        test_user,
        test_workspace,
        test_doc,
        test_note,
        test_anchor,
    ):
        service = ChatSessionService(db_session=db_session)

        session = await service.create_session(
            workspace_id=test_workspace.workspace_id,
            user_id=test_user.user_id,
            title="Session",
            mode="assist",
            context={
                "note_id": test_note.note_id,
                "anchor_ids": [test_anchor.anchor_id],
                "doc_id": test_doc.doc_id,
            },
            defaults=None,
            client_request_id=None,
        )

        assert session.context_json["note_id"] == test_note.note_id
        assert session.context_json["anchor_ids"] == [test_anchor.anchor_id]

    @pytest.mark.asyncio
    async def test_create_session_context_anchor_wrong_workspace(
        self,
        db_session,
        test_user,
        test_workspace,
        test_doc,
    ):
        other_workspace = WorkspaceModel(
            name="Other Workspace",
            owner_user_id=test_user.user_id,
        )
        db_session.add(other_workspace)
        await db_session.commit()
        await db_session.refresh(other_workspace)

        other_anchor = AnchorModel(
            created_by_user_id=test_user.user_id,
            note_id=None,
            doc_id=test_doc.doc_id,
            chunk_id=None,
            workspace_id=other_workspace.workspace_id,
            page=1,
            quoted_text="quote",
            locator={"type": "pdf_quadpoints"},
            locator_hash="hash_anchor_other",
        )
        db_session.add(other_anchor)
        await db_session.commit()
        await db_session.refresh(other_anchor)

        service = ChatSessionService(db_session=db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_session(
                workspace_id=test_workspace.workspace_id,
                user_id=test_user.user_id,
                title="Session",
                mode="assist",
                context={
                    "doc_id": test_doc.doc_id,
                    "doc_anchor_ids": [other_anchor.anchor_id],
                },
                defaults=None,
                client_request_id=None,
            )

        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_create_session_context_anchor_note_mismatch(
        self,
        db_session,
        test_user,
        test_workspace,
        test_doc,
        test_note,
    ):
        other_note = NoteModel(
            workspace_id=test_workspace.workspace_id,
            doc_id=None,
            owner_user_id=test_user.user_id,
            title="Other Note",
            markdown="Other content",
        )
        db_session.add(other_note)
        await db_session.commit()
        await db_session.refresh(other_note)

        anchor = AnchorModel(
            created_by_user_id=test_user.user_id,
            note_id=other_note.note_id,
            doc_id=test_doc.doc_id,
            chunk_id=None,
            workspace_id=test_workspace.workspace_id,
            page=1,
            quoted_text="quote",
            locator={"type": "pdf_quadpoints"},
            locator_hash="hash_anchor_note_mismatch",
        )
        db_session.add(anchor)
        await db_session.commit()
        await db_session.refresh(anchor)

        service = ChatSessionService(db_session=db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_session(
                workspace_id=test_workspace.workspace_id,
                user_id=test_user.user_id,
                title="Session",
                mode="assist",
                context={
                    "note_id": test_note.note_id,
                    "anchor_ids": [anchor.anchor_id],
                    "doc_id": test_doc.doc_id,
                },
                defaults=None,
                client_request_id=None,
            )

        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_create_session_idempotency(
        self,
        db_session,
        test_user,
        test_workspace,
    ):
        service = ChatSessionService(db_session=db_session)

        first = await service.create_session(
            workspace_id=test_workspace.workspace_id,
            user_id=test_user.user_id,
            title=None,
            mode="ask",
            context=None,
            defaults=None,
            client_request_id="req-123",
        )
        second = await service.create_session(
            workspace_id=test_workspace.workspace_id,
            user_id=test_user.user_id,
            title="Another",
            mode="assist",
            context=None,
            defaults=None,
            client_request_id="req-123",
        )

        assert first.session_id == second.session_id
