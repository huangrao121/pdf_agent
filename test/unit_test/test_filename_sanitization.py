"""
Unit tests for filename sanitization.
"""

from pdf_ai_agent.api.routes.documents import sanitize_filename


class TestFilenameSanitization:
    """Tests for filename sanitization logic."""

    def test_sanitize_normal_filename(self):
        """Test that normal filenames are unchanged."""
        assert sanitize_filename("document.pdf") == "document.pdf"
        assert sanitize_filename("my_file-123.pdf") == "my_file-123.pdf"

    def test_sanitize_removes_newlines(self):
        """Test that newlines and control characters are removed."""
        assert sanitize_filename("doc\r\nument.pdf") == "document.pdf"
        assert sanitize_filename("doc\nument.pdf") == "document.pdf"
        assert sanitize_filename("doc\x00ument.pdf") == "document.pdf"

    def test_sanitize_removes_quotes(self):
        """Test that quotes are removed."""
        assert sanitize_filename('document"test".pdf') == "documenttest.pdf"
        assert sanitize_filename("doc'ument.pdf") == "doc'ument.pdf"  # Single quotes OK

    def test_sanitize_removes_backslashes(self):
        """Test that backslashes are removed."""
        assert sanitize_filename("document\\test.pdf") == "documenttest.pdf"

    def test_sanitize_long_filename(self):
        """Test that long filenames are truncated."""
        long_name = "a" * 250 + ".pdf"
        result = sanitize_filename(long_name)
        assert len(result) <= 200
        assert result.endswith(".pdf")
        assert "..." in result

    def test_sanitize_long_filename_no_extension(self):
        """Test truncation of long filename without extension."""
        long_name = "a" * 250
        result = sanitize_filename(long_name)
        assert len(result) <= 200
        assert result.endswith("...")

    def test_sanitize_unicode_filename(self):
        """Test that Unicode characters are preserved."""
        assert sanitize_filename("文档.pdf") == "文档.pdf"
        assert sanitize_filename("document_日本語.pdf") == "document_日本語.pdf"

    def test_sanitize_spaces_preserved(self):
        """Test that spaces are preserved."""
        assert sanitize_filename("my document.pdf") == "my document.pdf"
        assert sanitize_filename("test file name.pdf") == "test file name.pdf"

    def test_sanitize_empty_filename(self):
        """Test empty filename."""
        assert sanitize_filename("") == ""

    def test_sanitize_multiple_issues(self):
        """Test filename with multiple issues."""
        result = sanitize_filename('doc\r\n"bad"\\file.pdf')
        assert result == "docbadfile.pdf"
