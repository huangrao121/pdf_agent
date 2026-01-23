"""
Unit tests for document service components.
"""
import io
import pytest
from pdf_ai_agent.storage.local_storage import LocalStorageService
from pdf_ai_agent.jobs.job_queue import JobQueueService

@pytest.fixture
def test_storage_service(tmp_path) -> LocalStorageService:
    """Fixture for LocalStorageService with temporary path."""
    storage = LocalStorageService(base_path=tmp_path)
    return storage

@pytest.fixture
def test_job_queue_service():
    """Fixture for JobQueueService"""
    return JobQueueService()


class TestPDFValidation:
    """Tests for PDF validation."""
    
    def test_pdf_magic_bytes_valid(self, db_session, test_storage_service, test_job_queue_service):
        """Test valid PDF magic bytes."""
        from pdf_ai_agent.api.services.document_service import DocumentService
        
        # Create a mock session (not used for this test)
        doc_service = DocumentService(db_session=db_session, storage_service=test_storage_service, job_queue_service=test_job_queue_service)
        
        # Valid PDF file
        valid_pdf = io.BytesIO(b"%PDF-1.4\n%some content")
        assert doc_service._validate_pdf_magic_bytes(valid_pdf)
    
    def test_pdf_magic_bytes_invalid(self, db_session, test_storage_service, test_job_queue_service):
        """Test invalid PDF magic bytes."""
        from pdf_ai_agent.api.services.document_service import DocumentService
        
        doc_service = DocumentService(db_session=db_session, storage_service=test_storage_service, job_queue_service=test_job_queue_service)
        
        # Invalid file
        invalid_file = io.BytesIO(b"Not a PDF file")
        assert not doc_service._validate_pdf_magic_bytes(invalid_file)
    
    def test_pdf_magic_bytes_empty(self, db_session, test_storage_service, test_job_queue_service):
        """Test empty file."""
        from pdf_ai_agent.api.services.document_service import DocumentService
        
        doc_service = DocumentService(db_session=db_session, storage_service=test_storage_service, job_queue_service=test_job_queue_service)
        
        # Empty file
        empty_file = io.BytesIO(b"")
        assert not doc_service._validate_pdf_magic_bytes(empty_file)


class TestSHA256Streaming:
    """Tests for streaming SHA-256 computation."""
    
    def test_sha256_computation(self):
        """Test SHA-256 hash computation."""
        storage = LocalStorageService(base_path="tmp/test_storage")
        
        # Create test content
        content = b"Test content for hashing"
        file_obj = io.BytesIO(content)
        
        # Compute hash
        sha256, size = storage.compute_sha256_streaming(file_obj)
        
        # Verify
        assert len(sha256) == 64  # SHA-256 is 64 hex characters
        assert size == len(content)
        
        # File pointer should be reset
        assert file_obj.tell() == 0
    
    def test_sha256_different_chunk_sizes(self):
        """Test that different chunk sizes produce same hash."""
        storage = LocalStorageService(base_path="tmp/test_storage")
        
        # Create larger test content
        content = b"X" * (10 * 1024 * 1024)  # 10MB
        
        # Test with different chunk sizes
        file_obj1 = io.BytesIO(content)
        sha1, size1 = storage.compute_sha256_streaming(file_obj1, chunk_size=1024)
        
        file_obj2 = io.BytesIO(content)
        sha2, size2 = storage.compute_sha256_streaming(file_obj2, chunk_size=8*1024*1024)
        
        # Should produce same hash
        assert sha1 == sha2
        assert size1 == size2 == len(content)
    
    def test_sha256_same_content_same_hash(self):
        """Test that same content produces same hash."""
        storage = LocalStorageService(base_path="tmp/test_storage")
        
        content = b"Consistent content"
        
        file_obj1 = io.BytesIO(content)
        sha1, _ = storage.compute_sha256_streaming(file_obj1)
        
        file_obj2 = io.BytesIO(content)
        sha2, _ = storage.compute_sha256_streaming(file_obj2)
        
        assert sha1 == sha2
    
    def test_sha256_different_content_different_hash(self):
        """Test that different content produces different hash."""
        storage = LocalStorageService(base_path="tmp/test_storage")
        
        file_obj1 = io.BytesIO(b"Content A")
        sha1, _ = storage.compute_sha256_streaming(file_obj1)
        
        file_obj2 = io.BytesIO(b"Content B")
        sha2, _ = storage.compute_sha256_streaming(file_obj2)
        
        assert sha1 != sha2


class TestStorageService:
    """Tests for storage service."""
    
    def test_storage_uri_generation(self):
        """Test storage URI generation."""
        storage = LocalStorageService(base_path="tmp/test_storage")
        
        content = b"%PDF-1.4\nTest PDF content"
        file_obj = io.BytesIO(content)
        
        uri = storage.save_file_streaming(
            file_obj=file_obj,
            workspace_id=1,
            doc_id=123,
            filename="test.pdf"
        )
        
        # Should follow pattern: local://workspace_id/doc_id_filename
        assert uri.startswith("local://")
        assert "1/" in uri  # workspace_id
        assert "123_test.pdf" in uri  # doc_id_filename
    
    def test_file_write_and_read(self):
        """Test file write and read."""
        import tempfile
        import shutil
        
        # Create temporary directory
        temp_dir = tempfile.mkdtemp()
        
        try:
            storage = LocalStorageService(base_path=temp_dir)
            
            content = b"%PDF-1.4\nTest PDF content"
            file_obj = io.BytesIO(content)
            
            # Save file
            uri = storage.save_file_streaming(
                file_obj=file_obj,
                workspace_id=1,
                doc_id=123,
                filename="test.pdf"
            )
            
            # Read file
            file_path = storage.get_file_path(uri)
            assert file_path.exists()
            
            with open(file_path, 'rb') as f:
                read_content = f.read()
            
            assert read_content == content
            
        finally:
            # Cleanup
            shutil.rmtree(temp_dir)
