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


class ChatSessionDetail(BaseModel):
    """Session detail payload for get session responses."""
    id: int = Field(..., description="Session ID")
    workspace_id: int = Field(..., description="Workspace ID")
    title: str = Field(..., description="Chat title")
    mode: ChatSessionMode = Field(..., description="Chat mode")
    context: ChatSessionContext = Field(..., description="Chat context")
    defaults: ChatDefaults = Field(..., description="Chat defaults")
    created_by: int = Field(..., description="Creator user ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Update timestamp")
    last_message_at: Optional[datetime] = Field(None, description="Last message timestamp")
    message_count: int = Field(..., description="Total message count")


class MessageContentItem(BaseModel):
    """Content block for a message."""
    type: str = Field(..., description="Content type, e.g., text")
    text: str = Field(..., description="Text content")


class MessageItem(BaseModel):
    """Chat message item."""
    id: int = Field(..., description="Message ID")
    role: str = Field(..., description="Message role")
    content: List[MessageContentItem] = Field(..., description="Message content blocks")
    citations: Optional[List[dict]] = Field(None, description="Citations")
    usage: Optional[dict] = Field(None, description="Token usage metadata")
    created_at: datetime = Field(..., description="Message creation timestamp")


class MessagePage(BaseModel):
    """Message page for pagination."""
    items: List[MessageItem] = Field(..., description="Messages")
    next_cursor: Optional[str] = Field(None, description="Cursor for next page")


class GetChatSessionResponse(BaseModel):
    """Response schema for getting a chat session and messages."""
    session: ChatSessionDetail = Field(..., description="Chat session detail")
    messages: MessagePage = Field(..., description="Messages page")


class ChatContextSummary(BaseModel):
    """Summary of chat context for list responses."""
    doc_id: Optional[int] = Field(None, description="Document ID")
    note_id: Optional[int] = Field(None, description="Note ID")
    anchor_count: int = Field(0, description="Total anchor count")


class ChatSessionListItem(BaseModel):
    """List item for chat sessions."""
    session_id: int = Field(..., description="Session ID")
    workspace_id: int = Field(..., description="Workspace ID")
    title: str = Field(..., description="Chat title")
    mode: ChatSessionMode = Field(..., description="Chat mode")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Update timestamp", serialization_alias="update_at")
    last_message_at: Optional[datetime] = Field(None, description="Last message timestamp")
    message_count: int = Field(..., description="Total message count")
    context_summary: ChatContextSummary = Field(..., description="Context summary")


class ListChatSessionsResponse(BaseModel):
    """Response schema for listing chat sessions."""
    chat_session_items: List[ChatSessionListItem] = Field(..., description="Chat session list")
    next_cursor: Optional[str] = Field(None, description="Cursor for next page")


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


class ChatOverridesRetrieval(BaseModel):
    """Overrides for retrieval settings."""
    enabled: Optional[bool] = Field(None, description="Enable retrieval")
    top_k: Optional[int] = Field(None, description="Number of chunks to retrieve")
    rerank: Optional[bool] = Field(None, description="Enable reranking")


class ChatOverrides(BaseModel):
    """Overrides for a single request."""
    model: Optional[str] = Field(None, description="Override model name")
    temperature: Optional[float] = Field(None, description="Override sampling temperature")
    top_p: Optional[float] = Field(None, description="Override top-p sampling")
    retrieval: Optional[ChatOverridesRetrieval] = Field(None, description="Override retrieval settings")


class AskMessageRequest(BaseModel):
    """Request schema for ask message."""
    client_request_id: str = Field(..., description="Client request ID for idempotency", min_length=1)
    input: List[MessageContentItem] = Field(..., description="Structured input content")
    context: Optional[ChatSessionContext] = Field(None, description="Optional context override")
    overrides: Optional[ChatOverrides] = Field(None, description="Optional overrides for this request")


class AskMessageResponse(BaseModel):
    """Response schema for ask message."""
    user_message: MessageItem = Field(..., description="User message")
    assistant_message: MessageItem = Field(..., description="Assistant message")
