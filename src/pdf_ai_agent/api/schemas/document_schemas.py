"""
Pydantic schemas for document-related API endpoints.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional
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
