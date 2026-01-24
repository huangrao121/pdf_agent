"""
Unit tests for HTTP Range header parsing.
"""

import pytest
from pdf_ai_agent.storage.local_storage import LocalStorageService


class TestRangeHeaderParsing:
    """Tests for Range header parsing logic."""

    def test_parse_range_start_end(self):
        """Test parsing bytes=start-end format."""
        # Valid range within file
        result = LocalStorageService.parse_range_header("bytes=0-999", 2000)
        assert result == (0, 999)

        # Range at end of file
        result = LocalStorageService.parse_range_header("bytes=1000-1999", 2000)
        assert result == (1000, 1999)

        # Single byte
        result = LocalStorageService.parse_range_header("bytes=500-500", 2000)
        assert result == (500, 500)

    def test_parse_range_start_only(self):
        """Test parsing bytes=start- format (to end of file)."""
        result = LocalStorageService.parse_range_header("bytes=1000-", 2000)
        assert result == (1000, 1999)

        # From beginning
        result = LocalStorageService.parse_range_header("bytes=0-", 2000)
        assert result == (0, 1999)

        # Last byte
        result = LocalStorageService.parse_range_header("bytes=1999-", 2000)
        assert result == (1999, 1999)

    def test_parse_range_suffix(self):
        """Test parsing bytes=-suffix format (last N bytes)."""
        # Last 500 bytes
        result = LocalStorageService.parse_range_header("bytes=-500", 2000)
        assert result == (1500, 1999)

        # Last byte
        result = LocalStorageService.parse_range_header("bytes=-1", 2000)
        assert result == (1999, 1999)

        # Suffix larger than file - should return entire file
        result = LocalStorageService.parse_range_header("bytes=-3000", 2000)
        assert result == (0, 1999)

    def test_parse_range_clamping(self):
        """Test that end position is clamped to file size."""
        # End beyond file size
        result = LocalStorageService.parse_range_header("bytes=0-5000", 2000)
        assert result == (0, 1999)

        # Start valid, end beyond
        result = LocalStorageService.parse_range_header("bytes=1500-3000", 2000)
        assert result == (1500, 1999)

    def test_parse_range_invalid(self):
        """Test invalid range formats return None."""
        # Start >= file_size
        result = LocalStorageService.parse_range_header("bytes=2000-2500", 2000)
        assert result is None

        # Start > end
        result = LocalStorageService.parse_range_header("bytes=1000-500", 2000)
        assert result is None

        # Suffix of 0
        result = LocalStorageService.parse_range_header("bytes=-0", 2000)
        assert result is None

        # Missing bytes= prefix
        result = LocalStorageService.parse_range_header("0-999", 2000)
        assert result is None

        # Empty string
        result = LocalStorageService.parse_range_header("", 2000)
        assert result is None

        # None
        result = LocalStorageService.parse_range_header(None, 2000)
        assert result is None

    def test_parse_range_multiple_ranges(self):
        """Test that multiple ranges are not supported (return None)."""
        result = LocalStorageService.parse_range_header("bytes=0-99,200-299", 2000)
        assert result is None

        result = LocalStorageService.parse_range_header(
            "bytes=0-99,200-299,500-599", 2000
        )
        assert result is None

    def test_parse_range_malformed(self):
        """Test malformed range formats return None."""
        # Invalid format
        result = LocalStorageService.parse_range_header("bytes=abc-def", 2000)
        assert result is None

        # Multiple dashes
        result = LocalStorageService.parse_range_header("bytes=0-100-200", 2000)
        assert result is None

        # No dash
        result = LocalStorageService.parse_range_header("bytes=100", 2000)
        assert result is None

        # Spaces
        result = LocalStorageService.parse_range_header("bytes= 0 - 100 ", 2000)
        assert result is None

    def test_parse_range_edge_cases(self):
        """Test edge cases."""
        # Empty file
        result = LocalStorageService.parse_range_header("bytes=0-0", 0)
        assert result is None  # start >= file_size

        # Single byte file
        result = LocalStorageService.parse_range_header("bytes=0-0", 1)
        assert result == (0, 0)

        result = LocalStorageService.parse_range_header("bytes=0-", 1)
        assert result == (0, 0)

        result = LocalStorageService.parse_range_header("bytes=-1", 1)
        assert result == (0, 0)
