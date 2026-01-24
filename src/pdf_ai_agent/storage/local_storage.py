"""
Local disk storage service for PDF files.

Provides streaming write capabilities to avoid memory issues with large files.
"""

import os
import hashlib
import shutil
import re
from pathlib import Path
from typing import BinaryIO, Tuple, Optional, AsyncIterator
from datetime import datetime


class LocalStorageService:
    """
    Local disk storage service.

    Stores files on local filesystem with streaming support.
    Organizes files by workspace_id and uses doc_id for naming.
    """

    def __init__(self, base_path: str = "tmp/pdf_storage"):
        """
        Initialize local storage service.

        Args:
            base_path: Base directory for storing files
        """
        self.project_dir = Path(__file__).parent.parent.parent.parent.resolve()
        self.base_path = self.project_dir / base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def compute_sha256_streaming(
        self, file_obj: BinaryIO, chunk_size: int = 4 * 1024 * 1024  # 4MB chunks
    ) -> Tuple[str, int]:
        """
        Compute SHA-256 hash of a file while streaming.

        Args:
            file_obj: File object to read from
            chunk_size: Size of chunks to read (default 4MB)

        Returns:
            Tuple of (hex digest, file size in bytes)
        """
        sha256_hash = hashlib.sha256()
        file_size = 0

        # Reset file pointer to beginning
        file_obj.seek(0)

        while True:
            chunk = file_obj.read(chunk_size)
            if not chunk:
                break
            sha256_hash.update(chunk)
            file_size += len(chunk)

        # Reset file pointer for subsequent operations
        file_obj.seek(0)

        return sha256_hash.hexdigest(), file_size

    def save_file_streaming(
        self,
        file_obj: BinaryIO,
        workspace_id: int,
        doc_id: int,
        filename: str,
        chunk_size: int = 4 * 1024 * 1024,  # 4MB chunks
    ) -> str:
        """
        Save a file to local storage using streaming.

        Args:
            file_obj: File object to read from
            workspace_id: Workspace ID
            doc_id: Document ID
            filename: Original filename
            chunk_size: Size of chunks to write (default 4MB)

        Returns:
            storage_uri: URI for accessing the file
        """
        # Create directory structure: base_path/workspace_id/
        workspace_dir = self.base_path / str(workspace_id)
        workspace_dir.mkdir(parents=True, exist_ok=True)

        # Generate file path: workspace_id/doc_id_filename
        file_path = workspace_dir / f"{doc_id}_{filename}"

        # Reset file pointer to beginning
        file_obj.seek(0)

        # Write file in chunks
        with open(file_path, "wb") as dest:
            while True:
                chunk = file_obj.read(chunk_size)
                if not chunk:
                    break
                dest.write(chunk)

        # Generate storage URI (local file path)
        storage_uri = f"local://{file_path.relative_to(self.base_path)}"

        return storage_uri

    def delete_file(self, storage_uri: str) -> bool:
        """
        Delete a file from local storage.

        Args:
            storage_uri: Storage URI of the file to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            # Parse URI: local://workspace_id/doc_id_filename
            if not storage_uri.startswith("local://"):
                return False

            relative_path = storage_uri.replace("local://", "")
            file_path = self.base_path / relative_path

            if file_path.exists():
                file_path.unlink()
                return True
            return False
        except Exception:
            return False

    def get_file_path(self, storage_uri: str) -> Path:
        """
        Get absolute file path from storage URI.

        Args:
            storage_uri: Storage URI

        Returns:
            Absolute file path
        """
        relative_path = storage_uri.replace("local://", "")
        return self.base_path / relative_path

    def get_file_size(self, storage_uri: str) -> int:
        """
        Get file size from storage.

        Args:
            storage_uri: Storage URI

        Returns:
            File size in bytes

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        file_path = self.get_file_path(storage_uri)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {storage_uri}")
        return file_path.stat().st_size

    @staticmethod
    def parse_range_header(
        range_header: str, file_size: int
    ) -> Optional[Tuple[int, int]]:
        """
        Parse HTTP Range header and return (start, end) byte positions.

        Supports:
        - bytes=start-end (inclusive range)
        - bytes=start- (from start to end of file)
        - bytes=-suffix (last suffix bytes)

        Does NOT support:
        - Multiple ranges (returns None)

        Args:
            range_header: Range header value (e.g., "bytes=0-1023")
            file_size: Total file size in bytes

        Returns:
            Tuple of (start, end) inclusive, or None if invalid/unsupported

        Examples:
            >>> parse_range_header("bytes=0-999", 2000)
            (0, 999)
            >>> parse_range_header("bytes=1000-", 2000)
            (1000, 1999)
            >>> parse_range_header("bytes=-500", 2000)
            (1500, 1999)
        """
        if not range_header or not range_header.startswith("bytes="):
            return None

        range_spec = range_header[6:]  # Remove "bytes="

        # Check for multiple ranges (not supported in MVP)
        if "," in range_spec:
            return None

        # Match patterns: start-end, start-, -suffix
        match = re.match(r"^(\d+)?-(\d+)?$", range_spec)
        if not match:
            return None

        start_str, end_str = match.groups()

        # Invalid: both None (bytes=-)
        if start_str is None and end_str is None:
            return None

        # Handle suffix range: bytes=-suffix
        if start_str is None and end_str is not None:
            suffix = int(end_str)
            if suffix == 0:
                return None  # Invalid: bytes=-0
            if suffix >= file_size:
                # Client wants last N bytes but file is smaller
                # Return entire file
                return (0, file_size - 1)
            return (file_size - suffix, file_size - 1)

        # Handle start-end or start-
        start = int(start_str) if start_str else 0

        # Validate start position
        if start < 0 or start >= file_size:
            return None  # Invalid range

        # Handle bytes=start-end
        if end_str is not None:
            end = int(end_str)
            if end < start:
                return None  # Invalid: end before start
            # Clamp end to file size
            end = min(end, file_size - 1)
            return (start, end)

        # Handle bytes=start- (to end of file)
        return (start, file_size - 1)

    async def stream_file_range(
        self,
        storage_uri: str,
        start: int,
        end: int,
        chunk_size: int = 512 * 1024,  # 512KB chunks
    ) -> AsyncIterator[bytes]:
        """
        Stream a range of bytes from a file.

        Args:
            storage_uri: Storage URI
            start: Start byte position (inclusive)
            end: End byte position (inclusive)
            chunk_size: Size of chunks to read (default 512KB)

        Yields:
            Chunks of file data

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        file_path = self.get_file_path(storage_uri)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {storage_uri}")

        # Calculate total bytes to read
        total_bytes = end - start + 1
        bytes_read = 0

        # Read file in chunks
        with open(file_path, "rb") as f:
            # Seek to start position
            f.seek(start)

            while bytes_read < total_bytes:
                # Calculate chunk size for this iteration
                bytes_remaining = total_bytes - bytes_read
                current_chunk_size = min(chunk_size, bytes_remaining)

                # Read chunk
                chunk = f.read(current_chunk_size)
                if not chunk:
                    break

                bytes_read += len(chunk)
                yield chunk


# Global storage service instance
_storage_service: LocalStorageService = None


def get_storage_service() -> LocalStorageService:
    """
    Get or create storage service instance.

    Returns:
        LocalStorageService instance
    """
    global _storage_service
    if _storage_service is None:
        # Get base path from environment or use default
        base_path = os.getenv("STORAGE_BASE_PATH", "/tmp/pdf_storage")
        _storage_service = LocalStorageService(base_path=base_path)
    return _storage_service
