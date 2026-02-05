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
    DOC_NOT_FOUND = "DOC_NOT_FOUND"
    WORKSPACE_NOT_FOUND = "WORKSPACE_NOT_FOUND"
    DOC_WORKSPACE_MISMATCH = "DOC_WORKSPACE_MISMATCH"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"


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