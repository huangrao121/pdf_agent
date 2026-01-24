"""
Pydantic schemas for document-related API endpoints.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


class DocStatusEnum(str, Enum):
    """Document processing status."""
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class DocUploadResponse(BaseModel):
    """Response schema for document upload."""
    doc_id: int = Field(..., description="Document ID")
    filename: str = Field(..., description="Original filename")
    status: DocStatusEnum = Field(..., description="Document status")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "doc_id": 123,
                "filename": "paper.pdf",
                "status": "UPLOADED"
            }
        }
    }


class ErrorDetail(BaseModel):
    """Error detail schema."""
    error_code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    details: Optional[dict] = Field(None, description="Additional error details")


class DocErrorResponse(BaseModel):
    """Error response schema for document operations."""
    status: str = Field("error", description="Status")
    error: ErrorDetail = Field(..., description="Error details")


class DocListItem(BaseModel):
    """Schema for a document list item."""
    doc_id: int = Field(..., description="Document ID")
    filename: str = Field(..., description="Original filename")
    title: str = Field(..., description="Document title")
    status: str = Field(..., description="Document status (UPLOADED/PROCESSING/READY/FAILED)")
    file_size: int = Field(..., description="File size in bytes")
    num_pages: Optional[int] = Field(None, description="Number of pages")
    created_at: datetime = Field(..., description="Creation timestamp")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "doc_id": 123,
                "filename": "paper.pdf",
                "title": "Some Title",
                "status": "READY",
                "file_size": 2345678,
                "num_pages": 15,
                "created_at": "2026-01-22T00:00:00Z"
            }
        }
    }


class DocListResponse(BaseModel):
    """Response schema for document list."""
    items: List[DocListItem] = Field(..., description="List of documents")
    next_cursor: Optional[str] = Field(None, description="Cursor for next page")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "items": [
                    {
                        "doc_id": 123,
                        "filename": "paper.pdf",
                        "title": "Some Title",
                        "status": "READY",
                        "file_size": 2345678,
                        "num_pages": 15,
                        "created_at": "2026-01-22T00:00:00Z"
                    }
                ],
                "next_cursor": "eyJjcmVhdGVkX2F0IjoiMjAyNi0wMS0yMlQwMDowMDowMFoiLCJkb2NfaWQiOjEyM30="
            }
        }
    }


class DocMetadataResponse(BaseModel):
    """Response schema for document metadata."""
    doc_id: int = Field(..., description="Document ID")
    filename: str = Field(..., description="Original filename")
    file_type: str = Field(..., description="MIME type")
    file_size: int = Field(..., description="File size in bytes")
    file_sha256: str = Field(..., description="SHA256 hash of file content")
    title: Optional[str] = Field(None, description="Document title")
    author: Optional[str] = Field(None, description="Document author")
    description: Optional[str] = Field(None, description="Document description")
    language: Optional[str] = Field(None, description="Language code (e.g., en, zh)")
    status: str = Field(..., description="Document status (UPLOADED/PROCESSING/READY/FAILED)")
    error_message: Optional[str] = Field(None, description="Error message if status is FAILED")
    num_pages: Optional[int] = Field(None, description="Number of pages")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "doc_id": 123,
                "filename": "paper.pdf",
                "file_type": "application/pdf",
                "file_size": 2345678,
                "file_sha256": "a1b2c3d4e5f6...",
                "title": "Some Title",
                "author": None,
                "description": None,
                "language": None,
                "status": "READY",
                "error_message": None,
                "num_pages": 15,
                "created_at": "2026-01-22T00:00:00Z",
                "updated_at": "2026-01-22T00:02:00Z"
            }
        }
    }
