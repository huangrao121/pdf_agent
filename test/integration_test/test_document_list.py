"""
Integration tests for document list endpoint.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from datetime import datetime, timedelta, timezone

from pdf_ai_agent.config.database.models.model_user import UserModel, WorkspaceModel
from pdf_ai_agent.config.database.models.model_document import DocsModel, DocStatus


def parse_datetime_field(dt_string: str) -> datetime:
    """Parse datetime string from API response, handling both Z and +00:00 timezones."""
    return datetime.fromisoformat(dt_string.replace('Z', '+00:00'))


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


async def create_test_documents(db_session, workspace_id, owner_user_id, count=30):
    """Create test documents with different timestamps."""
    base_time = datetime(2026, 1, 22, 0, 0, 0)
    documents = []
    
    for i in range(count):
        # Create documents with different timestamps
        # Some documents may have the same timestamp to test tie-breaking
        created_at = base_time - timedelta(minutes=i // 3)  # Group every 3 docs
        
        doc = DocsModel(
            workspace_id=workspace_id,
            owner_user_id=owner_user_id,
            filename=f"test_{i}.pdf",
            storage_uri=f"file:///tmp/test_{i}.pdf",
            file_type="application/pdf",
            file_size=1000 + i,
            file_sha256=f"{'a' * 63}{i}",
            title=f"Test Document {i}",
            status=DocStatus.READY if i % 3 == 0 else DocStatus.UPLOADED,
            num_pages=10 + i,
        )
        # Manually set created_at for testing
        doc.created_at = created_at
        documents.append(doc)
        db_session.add(doc)
    
    await db_session.commit()
    
    # Refresh all documents
    for doc in documents:
        await db_session.refresh(doc)
    
    return documents


@pytest.mark.asyncio
async def test_list_documents_first_page(test_app, db_session, test_user, test_workspace):
    """Test listing first page of documents."""
    # Create 30 documents
    await create_test_documents(db_session, test_workspace.workspace_id, test_user.user_id, 30)
    
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/docs",
            params={"user_id": test_user.user_id, "limit": 10}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check structure
        assert "items" in data
        assert "next_cursor" in data
        
        # Should return 10 items
        assert len(data["items"]) == 10
        
        # Should have next_cursor since there are more items
        assert data["next_cursor"] is not None
        
        # Verify items have correct fields
        item = data["items"][0]
        assert "doc_id" in item
        assert "filename" in item
        assert "title" in item
        assert "status" in item
        assert "file_size" in item
        assert "num_pages" in item
        assert "created_at" in item


@pytest.mark.asyncio
async def test_list_documents_pagination(test_app, db_session, test_user, test_workspace):
    """Test pagination with cursor."""
    # Create 30 documents
    await create_test_documents(db_session, test_workspace.workspace_id, test_user.user_id, 30)
    
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Get first page
        response1 = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/docs",
            params={"user_id": test_user.user_id, "limit": 10}
        )
        
        assert response1.status_code == 200
        data1 = response1.json()
        first_page_ids = {item["doc_id"] for item in data1["items"]}
        assert len(first_page_ids) == 10
        
        # Get second page using cursor
        cursor = data1["next_cursor"]
        assert cursor is not None
        
        response2 = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/docs",
            params={"user_id": test_user.user_id, "limit": 10, "cursor": cursor}
        )
        
        assert response2.status_code == 200
        data2 = response2.json()
        second_page_ids = {item["doc_id"] for item in data2["items"]}
        assert len(second_page_ids) == 10
        
        # Verify no overlap between pages
        assert first_page_ids.isdisjoint(second_page_ids)
        
        # Get third page
        cursor2 = data2["next_cursor"]
        assert cursor2 is not None
        
        response3 = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/docs",
            params={"user_id": test_user.user_id, "limit": 10, "cursor": cursor2}
        )
        
        assert response3.status_code == 200
        data3 = response3.json()
        third_page_ids = {item["doc_id"] for item in data3["items"]}
        assert len(third_page_ids) == 10
        
        # Verify no overlap
        assert first_page_ids.isdisjoint(third_page_ids)
        assert second_page_ids.isdisjoint(third_page_ids)
        
        # Fourth page should be empty or have no next cursor
        cursor3 = data3["next_cursor"]
        if cursor3:
            response4 = await client.get(
                f"/api/workspaces/{test_workspace.workspace_id}/docs",
                params={"user_id": test_user.user_id, "limit": 10, "cursor": cursor3}
            )
            assert response4.status_code == 200
            data4 = response4.json()
            # Should have no next cursor (last page)
            assert data4["next_cursor"] is None


@pytest.mark.asyncio
async def test_list_documents_stable_ordering(test_app, db_session, test_user, test_workspace):
    """Test that ordering is stable (created_at DESC, doc_id DESC)."""
    # Create documents
    docs = await create_test_documents(db_session, test_workspace.workspace_id, test_user.user_id, 30)
    
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/docs",
            params={"user_id": test_user.user_id, "limit": 30}
        )
        
        assert response.status_code == 200
        data = response.json()
        items = data["items"]
        
        # Verify ordering: created_at DESC, then doc_id DESC
        for i in range(len(items) - 1):
            current = items[i]
            next_item = items[i + 1]
            
            current_time = parse_datetime_field(current["created_at"])
            next_time = parse_datetime_field(next_item["created_at"])
            
            # created_at should be descending
            if current_time == next_time:
                # If timestamps are equal, doc_id should be descending
                assert current["doc_id"] > next_item["doc_id"], \
                    f"doc_id ordering violated: {current['doc_id']} <= {next_item['doc_id']}"
            else:
                assert current_time > next_time, \
                    f"created_at ordering violated: {current_time} <= {next_time}"


@pytest.mark.asyncio
async def test_list_documents_no_access(test_app, db_session, test_user):
    """Test listing documents without workspace access."""
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
        # Try to list documents in other user's workspace
        response = await client.get(
            f"/api/workspaces/{other_workspace.workspace_id}/docs",
            params={"user_id": test_user.user_id}
        )
        
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_documents_invalid_limit(test_app, db_session, test_user, test_workspace):
    """Test invalid limit values."""
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Limit too low
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/docs",
            params={"user_id": test_user.user_id, "limit": 0}
        )
        assert response.status_code == 422  # Validation error
        
        # Limit too high
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/docs",
            params={"user_id": test_user.user_id, "limit": 101}
        )
        assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_list_documents_invalid_cursor(test_app, db_session, test_user, test_workspace):
    """Test invalid cursor."""
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Invalid cursor
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/docs",
            params={"user_id": test_user.user_id, "cursor": "invalid-cursor!@#"}
        )
        
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_list_documents_empty_workspace(test_app, db_session, test_user, test_workspace):
    """Test listing documents in empty workspace."""
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/docs",
            params={"user_id": test_user.user_id}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["items"]) == 0
        assert data["next_cursor"] is None


@pytest.mark.asyncio
async def test_list_documents_default_limit(test_app, db_session, test_user, test_workspace):
    """Test default limit is 20."""
    # Create 30 documents
    await create_test_documents(db_session, test_workspace.workspace_id, test_user.user_id, 30)
    
    transport = ASGITransport(app=test_app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Don't specify limit
        response = await client.get(
            f"/api/workspaces/{test_workspace.workspace_id}/docs",
            params={"user_id": test_user.user_id}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return 20 items (default limit)
        assert len(data["items"]) == 20
        assert data["next_cursor"] is not None
