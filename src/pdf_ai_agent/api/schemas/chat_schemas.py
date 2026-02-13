from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class ChatSessionMode(str, Enum):
    """Chat session modes."""
    ASK = "ask"
    ASSIST = "assist"
    AGENT = "agent"


class ChatSessionContext(BaseModel):
    """Context for a chat session."""
    note_id: Optional[int] = Field(None, description="Note ID")
    anchor_ids: Optional[List[int]] = Field(None, description="Anchor IDs for note context")
    doc_id: Optional[int] = Field(None, description="Document ID")
    doc_anchor_ids: Optional[List[int]] = Field(None, description="Anchor IDs for document context")


class RetrievalDefaults(BaseModel):
    """Retrieval defaults."""
    enabled: bool = Field(True, description="Enable retrieval")
    top_k: int = Field(8, description="Number of chunks to retrieve")
    rerank: bool = Field(False, description="Enable reranking")


class ChatDefaults(BaseModel):
    """Default chat settings."""
    model: str = Field("gpt-4.1-mini", description="Model name")
    temperature: float = Field(0.2, description="Sampling temperature")
    top_p: float = Field(1.0, description="Top-p sampling")
    system_prompt: Optional[str] = Field(None, description="System prompt")
    retrieval: RetrievalDefaults = Field(default_factory=RetrievalDefaults)


class CreateChatSessionRequest(BaseModel):
    """Request schema for creating a chat session."""
    title: Optional[str] = Field(None, description="Optional chat title")
    mode: ChatSessionMode = Field(ChatSessionMode.ASK, description="Chat mode")
    context: Optional[ChatSessionContext] = Field(None, description="Chat context")
    defaults: Optional[ChatDefaults] = Field(None, description="Default settings")
    client_request_id: Optional[str] = Field(None, description="Client request ID for idempotency")

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v):
        """Validate that mode is one of the allowed values."""
        allowed_modes = {"ask", "assist", "agent"}
        if isinstance(v, str):
            if v.lower() not in allowed_modes:
                raise ValueError(f"mode must be one of {allowed_modes}, got '{v}'")
        elif isinstance(v, ChatSessionMode):
            # Already validated by enum type
            pass
        else:
            raise ValueError(f"mode must be a string or ChatSessionMode, got {type(v)}")
        return v


class ChatSessionData(BaseModel):
    """Chat session response payload."""
    id: int = Field(..., description="Session ID")
    workspace_id: int = Field(..., description="Workspace ID")
    title: str = Field(..., description="Chat title")
    mode: ChatSessionMode = Field(..., description="Chat mode")
    context: ChatSessionContext = Field(..., description="Chat context")
    defaults: ChatDefaults = Field(..., description="Chat defaults")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Update timestamp")


class CreateChatSessionResponse(BaseModel):
    """Response schema for creating a chat session."""
    session: ChatSessionData = Field(..., description="Chat session data")


class ChatErrorCode(str, Enum):
    """Error codes for chat session operations."""
    FORBIDDEN = "FORBIDDEN"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    WORKSPACE_NOT_FOUND = "WORKSPACE_NOT_FOUND"
    NOTE_NOT_FOUND = "NOTE_NOT_FOUND"
    DOC_NOT_FOUND = "DOC_NOT_FOUND"
    ANCHOR_INVALID = "ANCHOR_INVALID"
    CLIENT_REQUEST_ID_CONFLICT = "CLIENT_REQUEST_ID_CONFLICT"


class ChatErrorDetail(BaseModel):
    """Error detail schema."""
    code: ChatErrorCode = Field(..., description="Error code")
    message: str = Field(..., description="Error message")


class ChatErrorResponse(BaseModel):
    """Error response schema."""
    error: ChatErrorDetail = Field(..., description="Error details")
