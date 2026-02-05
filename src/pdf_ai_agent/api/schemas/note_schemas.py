from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


class CreateNoteRequest(BaseModel):
    """Request schema for creating a note."""
    doc_id: Optional[int] = Field(None, description="Document ID (optional, for doc-scoped notes)")
    title: Optional[str] = Field(None, description="Note title (optional, auto-generated if not provided)")
    content_markdown: str = Field(..., min_length=1, description="Markdown content (required, validated to be non-blank after trim)")
    
    @field_validator('content_markdown')
    @classmethod
    def validate_content_markdown(cls, v: str) -> str:
        """Validate markdown content is not blank after trim."""
        trimmed = v.strip()
        if not trimmed:
            raise ValueError('content_markdown cannot be blank after trimming')
        return trimmed
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "doc_id": 123,
                "title": "My Note Title",
                "content_markdown": "# Summary\n\nThis is my note content."
            }
        }
    }


class CreateNoteResponse(BaseModel):
    """Response schema for note creation."""
    note_id: int = Field(..., description="Note ID")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "note_id": 123123
            }
        }
    }


class NoteErrorCode(str, Enum):
    """Error codes for note operations."""
    FORBIDDEN = "FORBIDDEN"
    FORBIDDEN_WORKSPACE = "FORBIDDEN_WORKSPACE"
    DOC_NOT_FOUND = "DOC_NOT_FOUND"
    WORKSPACE_NOT_FOUND = "WORKSPACE_NOT_FOUND"
    NOTE_NOT_FOUND = "NOTE_NOT_FOUND"
    DOC_WORKSPACE_MISMATCH = "DOC_WORKSPACE_MISMATCH"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    DB_QUERY_FAILED = "DB_QUERY_FAILED"


class NoteErrorDetail(BaseModel):
    """Error detail schema for note operations."""
    code: NoteErrorCode = Field(..., description="Error code")
    message: str = Field(..., description="Error message")


class NoteErrorResponse(BaseModel):
    """Error response schema for note operations."""
    error: NoteErrorDetail = Field(..., description="Error details")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "error": {
                    "code": "DOC_NOT_FOUND",
                    "message": "Document not found"
                }
            }
        }
    }


class NoteListItem(BaseModel):
    """Schema for a note in the list response."""
    note_id: int = Field(..., description="Note ID")
    workspace_id: int = Field(..., description="Workspace ID")
    doc_id: Optional[int] = Field(None, description="Document ID (null for workspace-level notes)")
    title: str = Field(..., description="Note title")
    version: int = Field(..., description="Note version")
    owner_user_id: int = Field(..., description="Owner user ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "note_id": 987,
                "workspace_id": 1,
                "doc_id": 123,
                "title": "Attention mechanism summary",
                "version": 1,
                "owner_user_id": 42,
                "created_at": "2026-01-22T08:30:00Z",
                "updated_at": "2026-01-22T08:30:00Z"
            }
        }
    }


class ListNotesResponse(BaseModel):
    """Response schema for listing notes."""
    notes: List[NoteListItem] = Field(..., description="List of notes")
    next_cursor: Optional[str] = Field(None, description="Cursor for next page (null if at end)")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "notes": [
                    {
                        "note_id": 987,
                        "workspace_id": 1,
                        "doc_id": 123,
                        "title": "Attention mechanism summary",
                        "version": 1,
                        "owner_user_id": 42,
                        "created_at": "2026-01-22T08:30:00Z",
                        "updated_at": "2026-01-22T08:30:00Z"
                    }
                ],
                "next_cursor": "eyJjcmVhdGVkX2F0Ijoi..."
            }
        }
    }


class AnchorLocatorDetail(BaseModel):
    """Locator schema for anchor positioning in note response."""
    type: str = Field(..., description="Locator type (e.g., 'pdf_quadpoints')")
    coord_space: str = Field(..., description="Coordinate space (e.g., 'pdf_points')")
    page: int = Field(..., description="Page number (1-based index)", ge=1)
    quads: List[List[float]] = Field(..., description="List of quadpoints, each with 8 coordinates")
    
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


class AnchorDetail(BaseModel):
    """Schema for anchor detail in note response."""
    anchor_id: int = Field(..., description="Anchor ID")
    doc_id: int = Field(..., description="Document ID")
    chunk_id: Optional[int] = Field(None, description="Chunk ID")
    page: int = Field(..., description="Page number (1-based index)", ge=1)
    quoted_text: str = Field(..., description="Quoted text from the document")
    locator: AnchorLocatorDetail = Field(..., description="Locator information for precise positioning")
    created_at: datetime = Field(..., description="Creation timestamp")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "anchor_id": 789,
                "doc_id": 123,
                "chunk_id": 456,
                "page": 12,
                "quoted_text": "The model uses scaled dot-product attention.",
                "locator": {
                    "type": "pdf_quadpoints",
                    "coord_space": "pdf_points",
                    "page": 12,
                    "quads": [
                        [72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]
                    ]
                },
                "created_at": "2026-01-22T08:31:00Z"
            }
        }
    }


class NoteDetail(BaseModel):
    """Schema for detailed note information."""
    note_id: int = Field(..., description="Note ID")
    workspace_id: int = Field(..., description="Workspace ID")
    doc_id: Optional[int] = Field(None, description="Document ID (null for workspace-level notes)")
    owner_user_id: int = Field(..., description="Owner user ID")
    title: str = Field(..., description="Note title")
    markdown: str = Field(..., description="Full markdown content")
    version: int = Field(..., description="Note version")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "note_id": 111,
                "workspace_id": 1,
                "doc_id": 123,
                "owner_user_id": 42,
                "title": "Attention mechanism summary",
                "markdown": "# Attention Mechanism\n\nThe model uses scaled dot-product attention.",
                "version": 1,
                "created_at": "2026-01-22T08:30:00Z",
                "updated_at": "2026-01-22T08:30:00Z"
            }
        }
    }


class GetNoteResponse(BaseModel):
    """Response schema for getting note with anchors."""
    note: NoteDetail = Field(..., description="Note details")
    anchors: List[AnchorDetail] = Field(..., description="List of anchors associated with the note")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "note": {
                    "note_id": 111,
                    "workspace_id": 1,
                    "doc_id": 123,
                    "owner_user_id": 42,
                    "title": "Attention mechanism summary",
                    "markdown": "# Attention Mechanism\n\nThe model uses scaled dot-product attention.",
                    "version": 1,
                    "created_at": "2026-01-22T08:30:00Z",
                    "updated_at": "2026-01-22T08:30:00Z"
                },
                "anchors": [
                    {
                        "anchor_id": 789,
                        "doc_id": 123,
                        "chunk_id": 456,
                        "page": 12,
                        "quoted_text": "The model uses scaled dot-product attention.",
                        "locator": {
                            "type": "pdf_quadpoints",
                            "coord_space": "pdf_points",
                            "page": 12,
                            "quads": [
                                [72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]
                            ]
                        },
                        "created_at": "2026-01-22T08:31:00Z"
                    }
                ]
            }
        }
    }