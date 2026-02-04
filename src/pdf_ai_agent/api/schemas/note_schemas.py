from pydantic import BaseModel, Field, field_validator
from typing import Optional
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