"""
Local disk storage service for PDF files.

Provides streaming write capabilities to avoid memory issues with large files.
"""
import os
import hashlib
import shutil
from pathlib import Path
from typing import BinaryIO, Tuple
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
        self, 
        file_obj: BinaryIO, 
        chunk_size: int = 4 * 1024 * 1024  # 4MB chunks
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
        chunk_size: int = 4 * 1024 * 1024  # 4MB chunks
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
        with open(file_path, 'wb') as dest:
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
