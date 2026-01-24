"""
Integration tests for PDF streaming endpoint with Range support.
"""

import pytest
import os
from httpx import ASGITransport, AsyncClient

from fastapi import FastAPI
from contextlib import asynccontextmanager

from pdf_ai_agent.config.database.models.model_user import UserModel, WorkspaceModel
from pdf_ai_agent.config.database.models.model_document import DocsModel, DocStatus
from pdf_ai_agent.api.routes.documents import router as documents_router
from pdf_ai_agent.storage.local_storage import LocalStorageService

# Create test PDF content
TEST_PDF_CONTENT = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >>
endobj
4 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
5 0 obj
<< /Length 44 >>
stream
BT
/F1 12 Tf
100 700 Td
(Test PDF) Tj
ET
endstream
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000262 00000 n 
0000000341 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
433
%%EOF
"""


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
async def storage_service():
    """Create storage service for testing."""
    # Use /tmp for testing
    service = LocalStorageService(base_path="/tmp/pdf_storage_test")
    yield service
    # Cleanup
    import shutil

    if os.path.exists("/tmp/pdf_storage_test"):
        shutil.rmtree("/tmp/pdf_storage_test")


@pytest.fixture
async def test_document(db_session, test_workspace, test_user, storage_service):
    """Create a test document with actual file."""
    # Create document in DB
    doc = DocsModel(
        workspace_id=test_workspace.workspace_id,
        owner_user_id=test_user.user_id,
        filename="test.pdf",
        storage_uri="",  # Will be set after file creation
        file_type="application/pdf",
        file_size=len(TEST_PDF_CONTENT),
        file_sha256="a" * 64,
        title="Test Document",
        status=DocStatus.READY,
        num_pages=1,
    )
    db_session.add(doc)
    await db_session.flush()

    # Save file to storage
    workspace_dir = storage_service.base_path / str(test_workspace.workspace_id)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    file_path = workspace_dir / f"{doc.doc_id}_test.pdf"
    with open(file_path, "wb") as f:
        f.write(TEST_PDF_CONTENT)

    # Update storage URI
    doc.storage_uri = f"local://{test_workspace.workspace_id}/{doc.doc_id}_test.pdf"

    await db_session.commit()
    await db_session.refresh(doc)
    return doc


@pytest.fixture
async def test_document_not_ready(db_session, test_workspace, test_user):
    """Create a test document that is not ready."""
    doc = DocsModel(
        workspace_id=test_workspace.workspace_id,
        owner_user_id=test_user.user_id,
        filename="processing.pdf",
        storage_uri="local://test/processing.pdf",
        file_type="application/pdf",
        file_size=1000,
        file_sha256="b" * 64,
        title="Processing Document",
        status=DocStatus.PROCESSING,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


@pytest.fixture
async def test_app(db_session, storage_service):
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

    # Override dependencies
    from pdf_ai_agent.config.database.init_database import get_db_session
    from pdf_ai_agent.storage.local_storage import get_storage_service

    async def override_get_db_session():
        yield db_session

    def override_get_storage_service():
        return storage_service

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_storage_service] = override_get_storage_service

    return app


class TestDocumentStreamingAPI:
    """Tests for document streaming API with Range support."""

    @pytest.mark.asyncio
    async def test_stream_full_file(
        self, test_app, test_user, test_workspace, test_document
    ):
        """Test streaming full file without Range header."""
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_document.doc_id}/file",
                params={"user_id": test_user.user_id},
            )

        assert response.status_code == 200
        assert response.headers["Content-Type"] == "application/pdf"
        assert response.headers["Accept-Ranges"] == "bytes"
        assert response.headers["Content-Length"] == str(len(TEST_PDF_CONTENT))
        assert "Content-Disposition" in response.headers
        assert "test.pdf" in response.headers["Content-Disposition"]
        assert response.content == TEST_PDF_CONTENT

    @pytest.mark.asyncio
    async def test_stream_range_start_end(
        self, test_app, test_user, test_workspace, test_document
    ):
        """Test streaming with bytes=start-end range."""
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_document.doc_id}/file",
                params={"user_id": test_user.user_id},
                headers={"Range": "bytes=0-99"},
            )

        assert response.status_code == 206
        assert response.headers["Content-Type"] == "application/pdf"
        assert response.headers["Accept-Ranges"] == "bytes"
        assert (
            response.headers["Content-Range"] == f"bytes 0-99/{len(TEST_PDF_CONTENT)}"
        )
        assert response.headers["Content-Length"] == "100"
        assert len(response.content) == 100
        assert response.content == TEST_PDF_CONTENT[0:100]

    @pytest.mark.asyncio
    async def test_stream_range_start_only(
        self, test_app, test_user, test_workspace, test_document
    ):
        """Test streaming with bytes=start- range (to end of file)."""
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_document.doc_id}/file",
                params={"user_id": test_user.user_id},
                headers={"Range": f"bytes=500-"},
            )

        assert response.status_code == 206
        assert (
            response.headers["Content-Range"]
            == f"bytes 500-{len(TEST_PDF_CONTENT)-1}/{len(TEST_PDF_CONTENT)}"
        )
        expected_length = len(TEST_PDF_CONTENT) - 500
        assert response.headers["Content-Length"] == str(expected_length)
        assert len(response.content) == expected_length
        assert response.content == TEST_PDF_CONTENT[500:]

    @pytest.mark.asyncio
    async def test_stream_range_suffix(
        self, test_app, test_user, test_workspace, test_document
    ):
        """Test streaming with bytes=-suffix range (last N bytes)."""
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_document.doc_id}/file",
                params={"user_id": test_user.user_id},
                headers={"Range": "bytes=-100"},
            )

        assert response.status_code == 206
        file_size = len(TEST_PDF_CONTENT)
        start = file_size - 100
        assert (
            response.headers["Content-Range"]
            == f"bytes {start}-{file_size-1}/{file_size}"
        )
        assert response.headers["Content-Length"] == "100"
        assert len(response.content) == 100
        assert response.content == TEST_PDF_CONTENT[-100:]

    @pytest.mark.asyncio
    async def test_stream_range_invalid(
        self, test_app, test_user, test_workspace, test_document
    ):
        """Test that invalid range returns 416."""
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Start beyond file size
            response = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_document.doc_id}/file",
                params={"user_id": test_user.user_id},
                headers={"Range": f"bytes=10000-20000"},
            )

        assert response.status_code == 416
        assert response.headers["Content-Range"] == f"bytes */{len(TEST_PDF_CONTENT)}"
        assert response.headers["Accept-Ranges"] == "bytes"

    @pytest.mark.asyncio
    async def test_stream_range_multiple_not_supported(
        self, test_app, test_user, test_workspace, test_document
    ):
        """Test that multiple ranges return 416."""
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_document.doc_id}/file",
                params={"user_id": test_user.user_id},
                headers={"Range": "bytes=0-99,200-299"},
            )

        assert response.status_code == 416
        assert response.headers["Accept-Ranges"] == "bytes"

    @pytest.mark.asyncio
    async def test_stream_forbidden_workspace(
        self, test_app, test_workspace, test_document
    ):
        """Test that access is denied for non-member users."""
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Use a different user_id that doesn't own the workspace
            response = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_document.doc_id}/file",
                params={"user_id": 9999},
            )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_stream_document_not_found(self, test_app, test_user, test_workspace):
        """Test that non-existent document returns 404."""
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/9999/file",
                params={"user_id": test_user.user_id},
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_stream_document_not_ready(
        self, test_app, test_user, test_workspace, test_document_not_ready
    ):
        """Test that non-ready document returns 409."""
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_document_not_ready.doc_id}/file",
                params={"user_id": test_user.user_id},
            )

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_stream_range_at_boundaries(
        self, test_app, test_user, test_workspace, test_document
    ):
        """Test range requests at file boundaries."""
        transport = ASGITransport(app=test_app)
        file_size = len(TEST_PDF_CONTENT)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Last byte
            response = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_document.doc_id}/file",
                params={"user_id": test_user.user_id},
                headers={"Range": f"bytes={file_size-1}-{file_size-1}"},
            )

        assert response.status_code == 206
        assert len(response.content) == 1
        assert response.content == TEST_PDF_CONTENT[-1:]

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # First byte
            response = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs/{test_document.doc_id}/file",
                params={"user_id": test_user.user_id},
                headers={"Range": "bytes=0-0"},
            )

        assert response.status_code == 206
        assert len(response.content) == 1
        assert response.content == TEST_PDF_CONTENT[0:1]
