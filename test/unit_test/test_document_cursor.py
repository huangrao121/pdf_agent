"""
Unit tests for document cursor encoding/decoding.
"""
import pytest
from datetime import datetime
from fastapi import HTTPException

from pdf_ai_agent.api.services.document_service import DocumentService

class TestDocumentCursor:
    """Tests for DocumentService cursor encoding/decoding."""
    def test_encode_decode_cursor(self):
        """Test cursor encoding and decoding round-trip."""
        doc_id = 12345
        created_at = datetime(2026, 1, 22, 10, 30, 45)
        
        # Encode
        cursor = DocumentService.encode_cursor(doc_id, created_at)
        
        # Should be base64url encoded (no padding)
        assert isinstance(cursor, str)
        assert len(cursor) > 0
        assert '=' not in cursor  # No padding in urlsafe encoding
        
        # Decode
        decoded_doc_id, decoded_created_at = DocumentService.decode_cursor(cursor)
        
        # Should match original
        assert decoded_doc_id == doc_id
        assert decoded_created_at == created_at


    def test_decode_invalid_cursor_base64(self):
        """Test decoding invalid base64 cursor."""
        with pytest.raises(HTTPException) as exc_info:
            DocumentService.decode_cursor("invalid!@#$%")
        
        assert exc_info.value.status_code == 400
        assert "INVALID_CURSOR" in str(exc_info.value.detail)


    def test_decode_invalid_cursor_json(self):
        """Test decoding cursor with invalid JSON."""
        import base64
        
        # Valid base64 but invalid JSON
        invalid_json = base64.urlsafe_b64encode(b"not json").decode('utf-8').rstrip('=')
        
        with pytest.raises(HTTPException) as exc_info:
            DocumentService.decode_cursor(invalid_json)
        
        assert exc_info.value.status_code == 400
        assert "INVALID_CURSOR" in str(exc_info.value.detail)


    def test_decode_cursor_missing_fields(self):
        """Test decoding cursor with missing required fields."""
        import base64
        import json
        
        # Valid JSON but missing required fields
        cursor_data = {"doc_id": 123}  # Missing created_at
        cursor_json = json.dumps(cursor_data)
        cursor = base64.urlsafe_b64encode(cursor_json.encode('utf-8')).decode('utf-8').rstrip('=')
        
        with pytest.raises(HTTPException) as exc_info:
            DocumentService.decode_cursor(cursor)
        
        assert exc_info.value.status_code == 400
        assert "INVALID_CURSOR" in str(exc_info.value.detail)


    def test_decode_cursor_invalid_timestamp(self):
        """Test decoding cursor with invalid timestamp."""
        import base64
        import json
        
        # Valid JSON but invalid timestamp format
        cursor_data = {"doc_id": 123, "created_at": "not-a-timestamp"}
        cursor_json = json.dumps(cursor_data)
        cursor = base64.urlsafe_b64encode(cursor_json.encode('utf-8')).decode('utf-8').rstrip('=')
        
        with pytest.raises(HTTPException) as exc_info:
            DocumentService.decode_cursor(cursor)
        
        assert exc_info.value.status_code == 400
        assert "INVALID_CURSOR" in str(exc_info.value.detail)


    def test_encode_cursor_format(self):
        """Test that encoded cursor is in expected format."""
        doc_id = 123
        created_at = datetime(2026, 1, 22, 0, 0, 0)
        
        cursor = DocumentService.encode_cursor(doc_id, created_at)
        
        # Decode to verify format
        import base64
        import json
        
        # Add padding if needed
        padding = 4 - (len(cursor) % 4)
        if padding != 4:
            cursor_padded = cursor + '=' * padding
        else:
            cursor_padded = cursor
        
        cursor_bytes = base64.urlsafe_b64decode(cursor_padded.encode('utf-8'))
        cursor_json = cursor_bytes.decode('utf-8')
        cursor_data = json.loads(cursor_json)
        
        # Verify structure
        assert "doc_id" in cursor_data
        assert "created_at" in cursor_data
        assert cursor_data["doc_id"] == doc_id
        assert cursor_data["created_at"] == "2026-01-22T00:00:00"


    def test_cursor_with_microseconds(self):
        """Test cursor encoding/decoding with microseconds in timestamp."""
        doc_id = 999
        created_at = datetime(2026, 1, 22, 12, 34, 56, 789012)
        
        cursor = DocumentService.encode_cursor(doc_id, created_at)
        decoded_doc_id, decoded_created_at = DocumentService.decode_cursor(cursor)
        
        assert decoded_doc_id == doc_id
        assert decoded_created_at == created_at
