"""
Pydantic schemas for document-related API endpoints.
"""
import math
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


class PageMetadataItem(BaseModel):
    """Schema for a single page metadata."""
    page: int = Field(..., description="Page number (1-based index)", ge=1)
    width_pt: float = Field(..., description="Page width in points (1/72 inch)")
    height_pt: float = Field(..., description="Page height in points (1/72 inch)")
    rotation: int = Field(..., description="Page rotation in degrees (0, 90, 180, or 270)")
    text_layer_available: bool = Field(..., description="Whether the page has extractable text layer")
    
    @field_validator('rotation')
    @classmethod
    def validate_rotation(cls, v: int) -> int:
        """Validate rotation is one of 0, 90, 180, 270."""
        if v not in [0, 90, 180, 270]:
            raise ValueError('Rotation must be one of 0, 90, 180, or 270')
        return v
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "page": 1,
                "width_pt": 595.0,
                "height_pt": 842.0,
                "rotation": 0,
                "text_layer_available": True
            }
        }
    }


class DocPagesMetadataResponse(BaseModel):
    """Response schema for document pages metadata."""
    doc_id: int = Field(..., description="Document ID")
    pages: List[PageMetadataItem] = Field(..., description="List of page metadata")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "doc_id": 123,
                "pages": [
                    {
                        "page": 1,
                        "width_pt": 595.0,
                        "height_pt": 842.0,
                        "rotation": 0,
                        "text_layer_available": True
                    },
                    {
                        "page": 2,
                        "width_pt": 595.0,
                        "height_pt": 842.0,
                        "rotation": 0,
                        "text_layer_available": True
                    }
                ]
            }
        }
    }


class AnchorLocator(BaseModel):
    """Locator schema for anchor positioning."""
    type: str = Field(..., description="Locator type (e.g., 'pdf_quadpoints')")
    coord_space: str = Field(..., description="Coordinate space (e.g., 'pdf_points')")
    page: int = Field(..., description="Page number (1-based index)", ge=1)
    quads: List[List[float]] = Field(..., min_length=1, description="List of quadpoints, each with 8 coordinates")
    
    @field_validator('type')
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Validate locator type."""
        if v != "pdf_quadpoints":
            raise ValueError('Locator type must be "pdf_quadpoints"')
        return v

    @field_validator('coord_space')
    @classmethod
    def validate_coord_space(cls, v: str) -> str:
        """Validate coordinate space."""
        if v != "pdf_points":
            raise ValueError('Coordinate space must be "pdf_points"')
        return v
    
    @field_validator('quads')
    @classmethod
    def validate_quads(cls, v: List[List[float]]) -> List[List[float]]:
        """Validate quadpoints format."""
        for quad in v:
            if len(quad) != 8:
                raise ValueError('Each quad must have exactly 8 numbers')
            for num in quad:
                if not math.isfinite(num):
                    raise ValueError('All quad coordinates must be finite numbers')
        return v
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "type": "pdf_quadpoints",
                "coord_space": "pdf_points",
                "page": 12,
                "quads": [
                    [72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]
                ]
            }
        }
    }


class CreateAnchorRequest(BaseModel):
    """Request schema for creating an anchor."""
    chunk_id: Optional[int] = Field(None, description="Chunk ID (optional, for future use)")
    doc_id: int = Field(..., description="Document ID")
    page: int = Field(..., description="Page number (1-based index)", ge=1)
    quoted_text: str = Field(..., min_length=1, description="Quoted text from the document")
    locator: AnchorLocator = Field(..., description="Locator information for precise positioning")
    
    @field_validator('locator')
    @classmethod
    def validate_page_match(cls, v: AnchorLocator, info) -> AnchorLocator:
        """Validate that locator.page matches body.page."""
        if 'page' in info.data and v.page != info.data['page']:
            raise ValueError('Locator page must match request page')
        return v
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "chunk_id": 456,
                "doc_id": 22222,
                "page": 12,
                "quoted_text": "The model uses scaled dot-product attention.",
                "locator": {
                    "type": "pdf_quadpoints",
                    "coord_space": "pdf_points",
                    "page": 12,
                    "quads": [
                        [72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]
                    ]
                }
            }
        }
    }


class CreateAnchorResponse(BaseModel):
    """Response schema for anchor creation."""
    anchor_id: int = Field(..., description="Anchor ID")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "anchor_id": 789
            }
        }
    }


class GetAnchorResponse(BaseModel):
    """Response schema for getting anchor info."""
    anchor_id: int = Field(..., description="Anchor ID")
    doc_id: int = Field(..., description="Document ID")
    page: int = Field(..., description="Page number (1-based index)", ge=1)
    chunk_id: Optional[int] = Field(None, description="Chunk ID (optional, for future use)")
    note_id: Optional[int] = Field(None, description="Note ID (optional, for future use)")
    quoted_text: str = Field(..., description="Quoted text from the document")
    locator: dict = Field(..., description="Locator information for precise positioning")
    created_at: datetime = Field(..., description="Creation timestamp")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "anchor_id": 123,
                "doc_id": 456,
                "page": 32,
                "chunk_id": 789,
                "note_id": 222,
                "quoted_text": "this is text",
                "locator": {
                    "type": "pdf_quadpoints",
                    "coord_space": "pdf_points",
                    "page": 32,
                    "quads": [
                        [72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]
                    ]
                },
                "created_at": "2026-01-27T23:12:00Z"
            }
        }
    }

