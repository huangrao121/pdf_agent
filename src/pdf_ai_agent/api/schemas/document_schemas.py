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
